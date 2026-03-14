"""YAML config loading, validation, and typed dataclasses."""

from __future__ import annotations

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class BondConfig:
    token: str
    host: Optional[str]  # None = auto-discover via Zeroconf


@dataclass(frozen=True)
class LocationConfig:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ScheduleEntry:
    reference: str  # "dawn" or "dusk"
    offset_minutes: int


@dataclass(frozen=True)
class ScheduleConfig:
    open: ScheduleEntry
    close: ScheduleEntry


@dataclass(frozen=True)
class CommandConfig:
    retry_count: int
    retry_delay_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    file: str
    level: str


@dataclass(frozen=True)
class Config:
    bond: BondConfig
    location: LocationConfig
    schedule: ScheduleConfig
    commands: CommandConfig
    devices: list[str]
    logging: LoggingConfig


_VALID_REFERENCES = {"dawn", "dusk"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def _require(value, name: str):
    if value is None:
        raise ValueError(f"{name} is required")
    return value


def _parse_schedule_entry(data: dict, path: str) -> ScheduleEntry:
    ref = data.get("reference")
    if ref not in _VALID_REFERENCES:
        raise ValueError(
            f"{path}.reference must be 'dawn' or 'dusk', got {ref!r}"
        )
    offset = data.get("offset_minutes", 0)
    if not isinstance(offset, int):
        raise ValueError(f"{path}.offset_minutes must be an integer")
    return ScheduleEntry(reference=ref, offset_minutes=offset)


def load_config(path: str | Path) -> Config:
    """Load and validate config from a YAML file. Raises ValueError on invalid config."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Config file must be a YAML mapping")

    # bond
    bond_raw = raw.get("bond", {})
    token = _require(bond_raw.get("token"), "bond.token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("bond.token must be a non-empty string")
    bond = BondConfig(token=token, host=bond_raw.get("host"))

    # location
    loc_raw = raw.get("location", {})
    lat = _require(loc_raw.get("latitude"), "location.latitude")
    lon = _require(loc_raw.get("longitude"), "location.longitude")
    if not isinstance(lat, (int, float)):
        raise ValueError("location.latitude must be a number")
    if not isinstance(lon, (int, float)):
        raise ValueError("location.longitude must be a number")
    location = LocationConfig(latitude=float(lat), longitude=float(lon))

    # schedule
    sched_raw = raw.get("schedule", {})
    open_raw = sched_raw.get("open", {})
    close_raw = sched_raw.get("close", {})
    schedule = ScheduleConfig(
        open=_parse_schedule_entry(open_raw, "schedule.open"),
        close=_parse_schedule_entry(close_raw, "schedule.close"),
    )

    # commands
    cmd_raw = raw.get("commands", {})
    retry_count = cmd_raw.get("retry_count", 3)
    retry_delay = cmd_raw.get("retry_delay_seconds", 5)
    if not isinstance(retry_count, int) or retry_count < 1:
        raise ValueError("commands.retry_count must be a positive integer")
    if not isinstance(retry_delay, int) or retry_delay < 0:
        raise ValueError("commands.retry_delay_seconds must be a non-negative integer")
    commands = CommandConfig(retry_count=retry_count, retry_delay_seconds=retry_delay)

    # devices
    devices_raw = raw.get("devices", [])
    if not isinstance(devices_raw, list):
        raise ValueError("devices must be a list")
    devices = [str(d) for d in devices_raw]

    # logging
    log_raw = raw.get("logging", {})
    log_file = log_raw.get("file", "./bond-blinds.log")
    log_level = log_raw.get("level", "INFO").upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"logging.level must be one of {sorted(_VALID_LOG_LEVELS)}, got {log_level!r}"
        )
    logging_cfg = LoggingConfig(file=log_file, level=log_level)

    return Config(
        bond=bond,
        location=location,
        schedule=schedule,
        commands=commands,
        devices=devices,
        logging=logging_cfg,
    )
