"""Main scheduling loop for bond-blinds."""

from __future__ import annotations

import datetime
import json
import logging
import logging.handlers
import os
import signal
import time

from .client import BondClient, DeviceInfo
from .config import Config
from .discovery import DiscoveryError, discover_bridge
from .solar import get_solar_times
from .web import schedule_state, set_client, start_server

logger = logging.getLogger(__name__)

_running = True


def _setup_logging(cfg: Config) -> None:
    level = getattr(logging, cfg.logging.level)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)

    file_handler = logging.FileHandler(cfg.logging.file)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    # httpx logs every request at INFO; keep it quiet unless debugging
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _handle_signal(signum, frame) -> None:
    global _running
    logger.info("Received signal %s, shutting down", signal.Signals(signum).name)
    _running = False


def _resolve_host(cfg: Config) -> str:
    if cfg.bond.host:
        logger.info("Using configured Bond Bridge host: %s", cfg.bond.host)
        return cfg.bond.host
    if cfg.bond.name:
        logger.info("Discovering Bond Bridge with name %r via Zeroconf...", cfg.bond.name)
    else:
        logger.info("Discovering Bond Bridge via Zeroconf...")
    try:
        host = discover_bridge(name=cfg.bond.name)
        logger.info("Discovered Bond Bridge at %s", host)
        return host
    except DiscoveryError as exc:
        logger.error("%s", exc)
        raise SystemExit(1)


def _resolve_devices(client: BondClient, cfg: Config) -> list[DeviceInfo]:
    if cfg.devices:
        devices = []
        for device_id in cfg.devices:
            try:
                info = client.get_device(device_id)
                devices.append(info)
                logger.info(
                    "Configured device: %s (%s) actions=%s",
                    info.name,
                    info.id,
                    info.actions,
                )
            except Exception as exc:
                logger.error(
                    "Device %s not found on bridge, skipping: %s", device_id, exc
                )
        return devices
    else:
        logger.info("Auto-discovering MS devices on bridge...")
        all_ids = client.list_devices()
        devices = []
        for device_id in all_ids:
            try:
                info = client.get_device(device_id)
            except Exception as exc:
                logger.warning("Could not fetch device %s: %s", device_id, exc)
                continue
            if info.type == "MS":
                devices.append(info)
                logger.info(
                    "Found device: %s (%s) actions=%s", info.name, info.id, info.actions
                )
            else:
                logger.debug(
                    "Skipping device %s (%s): type=%s", info.name, info.id, info.type
                )
        return devices


def _compute_schedule(
    cfg: Config,
    date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime, datetime.datetime, datetime.datetime]:
    """Return (sunrise, sunset, open_time, close_time) for the given date."""
    sunrise, sunset = get_solar_times(
        date, cfg.location.latitude, cfg.location.longitude
    )
    logger.info(
        "Solar times for %s: sunrise=%s, sunset=%s",
        date,
        sunrise.strftime("%H:%M %Z"),
        sunset.strftime("%H:%M %Z"),
    )

    ref_open = sunrise if cfg.schedule.open.reference == "dawn" else sunset
    ref_close = sunrise if cfg.schedule.close.reference == "dawn" else sunset

    open_time = ref_open + datetime.timedelta(minutes=cfg.schedule.open.offset_minutes)
    close_time = ref_close + datetime.timedelta(
        minutes=cfg.schedule.close.offset_minutes
    )
    return sunrise, sunset, open_time, close_time


HISTORY_FILE = "solar_history.jsonl"
_MAX_HISTORY_DAYS = 365 * 3


def _write_solar_record(
    date: datetime.date,
    sunrise: datetime.datetime,
    sunset: datetime.datetime,
    open_time: datetime.datetime,
    close_time: datetime.datetime,
) -> None:
    """Append today's solar/schedule record to the history file, pruning entries older than 3 years."""
    fmt = "%H:%M %Z"
    record = {
        "date": date.isoformat(),
        "sunrise": sunrise.strftime(fmt),
        "sunset": sunset.strftime(fmt),
        "open": open_time.strftime(fmt),
        "close": close_time.strftime(fmt),
    }

    # Read existing entries, drop any for today (in case of restart) and old entries
    cutoff = date - datetime.timedelta(days=_MAX_HISTORY_DAYS)
    entries: list[dict] = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_date = datetime.date.fromisoformat(entry["date"])
                    if entry_date >= cutoff and entry_date != date:
                        entries.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    entries.append(record)

    with open(HISTORY_FILE, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    logger.debug("Wrote solar record for %s to %s", date, HISTORY_FILE)


def _execute_event(
    client: BondClient,
    devices: list[DeviceInfo],
    action: str,
    cfg: Config,
    dry_run: bool,
) -> None:
    retry_count = cfg.commands.retry_count
    retry_delay = cfg.commands.retry_delay_seconds
    logger.info(
        "%sing blinds (%d round(s), %ds delay)", action, retry_count, retry_delay
    )

    for round_num in range(1, retry_count + 1):
        successes = 0
        for device in devices:
            if dry_run:
                logger.debug(
                    "[%d/%d] %s: %s -> (dry run)",
                    round_num, retry_count, device.name, action,
                )
                successes += 1
                continue
            status = client.execute_action(device.id, action)
            if status == 200 or status == 204:
                logger.debug(
                    "[%d/%d] %s: %s -> %d OK",
                    round_num, retry_count, device.name, action, status,
                )
                successes += 1
            else:
                logger.warning(
                    "[%d/%d] %s: %s -> %s",
                    round_num, retry_count, device.name, action,
                    status if status != 0 else "error",
                )
        label = "dry run" if dry_run else f"{successes}/{len(devices)} blind{'s' if len(devices) != 1 else ''}"
        logger.info("Round %d/%d: %s %s", round_num, retry_count, action, label)
        if round_num < retry_count:
            logger.debug("Waiting %ds before round %d", retry_delay, round_num + 1)
            time.sleep(retry_delay)


def _sleep_until(target: datetime.datetime) -> None:
    """Sleep until target time, waking every second to check _running."""
    while _running:
        remaining = (target - _now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 1.0))


def _now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def send_command_now(cfg: Config, action: str) -> None:
    """Resolve devices and send a single action to all of them, then exit."""
    _setup_logging(cfg)
    host = _resolve_host(cfg)
    with BondClient(host, cfg.bond.token) as client:
        try:
            client.get_version()
        except Exception as exc:
            logger.error("Cannot reach Bond Bridge at %s: %s", host, exc)
            raise SystemExit(1)
        devices = _resolve_devices(client, cfg)
        if not devices:
            logger.error("No controllable devices found. Exiting.")
            raise SystemExit(1)
        successes = 0
        for device in devices:
            status = client.execute_action(device.id, action)
            if status in (200, 204):
                logger.debug("%s: %s -> %d OK", device.name, action, status)
                successes += 1
            else:
                logger.warning(
                    "%s: %s -> %s",
                    device.name, action,
                    status if status != 0 else "error",
                )
        logger.info("%s sent to %d/%d blind%s", action, successes, len(devices), "s" if len(devices) != 1 else "")


def run(cfg: Config, dry_run: bool = False) -> None:
    _setup_logging(cfg)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if dry_run:
        logger.info("Dry-run mode enabled — no commands will be sent")

    web_server = start_server(cfg.web.port)

    host = _resolve_host(cfg)

    with BondClient(host, cfg.bond.token) as client:
        try:
            version = client.get_version()
            logger.info(
                "Connected to Bond Bridge (firmware: %s, model: %s)",
                version.get("fw_ver", "?"),
                version.get("model", "?"),
            )
        except Exception as exc:
            logger.error("Cannot reach Bond Bridge at %s: %s", host, exc)
            raise SystemExit(1)

        devices = _resolve_devices(client, cfg)
        if not devices:
            logger.error("No controllable devices found. Exiting.")
            raise SystemExit(1)

        set_client(client, devices, cfg)

        today: datetime.date | None = None
        sunrise: datetime.datetime | None = None
        sunset: datetime.datetime | None = None
        open_time: datetime.datetime | None = None
        close_time: datetime.datetime | None = None

        while _running:
            now = _now()

            if now.date() != today:
                today = now.date()
                sunrise, sunset, open_time, close_time = _compute_schedule(cfg, today)
                schedule_state.update(today, sunrise, sunset, open_time, close_time)
                logger.info(
                    "Today's schedule: dawn=sunrise, dusk=sunset. "
                    "Open at %s, Close at %s",
                    open_time.strftime("%H:%M %Z"),
                    close_time.strftime("%H:%M %Z"),
                )

            # Build list of (time, action) events still in the future
            events = []
            if open_time > now:
                events.append((open_time, "Open"))
            if close_time > now:
                events.append((close_time, "Close"))

            if not events:
                # Record the day's solar/schedule data
                _write_solar_record(today, sunrise, sunset, open_time, close_time)

                # Both events have passed — sleep until just after midnight
                midnight = datetime.datetime.combine(
                    today + datetime.timedelta(days=1),
                    datetime.time(0, 1),
                ).astimezone()
                logger.info(
                    "All events done for today. Sleeping until %s",
                    midnight.strftime("%Y-%m-%d %H:%M %Z"),
                )
                _sleep_until(midnight)
                continue

            next_time, next_action = min(events, key=lambda e: e[0])
            logger.info(
                "Next event: %s at %s", next_action, next_time.strftime("%H:%M %Z")
            )
            _sleep_until(next_time)

            if not _running:
                break

            _execute_event(client, devices, next_action, cfg, dry_run)

    web_server.shutdown()
    logger.info("bond-blinds stopped")
