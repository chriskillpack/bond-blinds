"""Simple status webserver for bond-blinds."""

from __future__ import annotations

import datetime
import logging
import string
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).parent
_CSS = (_PKG_DIR / "static" / "style.css").read_text()
_PAGE_TEMPLATE = string.Template((_PKG_DIR / "templates" / "index.html").read_text())
_SCHEDULE_TEMPLATE = string.Template(
    (_PKG_DIR / "templates" / "schedule.html").read_text()
)


class _ScheduleState:
    """Thread-safe container for the current day's schedule data."""

    def __init__(self):
        self._lock = threading.Lock()
        self._date: datetime.date | None = None
        self._sunrise: datetime.datetime | None = None
        self._sunset: datetime.datetime | None = None
        self._open_time: datetime.datetime | None = None
        self._close_time: datetime.datetime | None = None

    def update(
        self,
        date: datetime.date,
        sunrise: datetime.datetime,
        sunset: datetime.datetime,
        open_time: datetime.datetime,
        close_time: datetime.datetime,
    ) -> None:
        with self._lock:
            self._date = date
            self._sunrise = sunrise
            self._sunset = sunset
            self._open_time = open_time
            self._close_time = close_time

    def snapshot(
        self,
    ) -> tuple[
        datetime.date | None,
        datetime.datetime | None,
        datetime.datetime | None,
        datetime.datetime | None,
        datetime.datetime | None,
    ]:
        with self._lock:
            return (
                self._date,
                self._sunrise,
                self._sunset,
                self._open_time,
                self._close_time,
            )


# Module-level state shared between the daemon and the web handler.
schedule_state = _ScheduleState()

# Set by the daemon after resolving the client and devices.
_client = None
_devices = None
_config = None


def set_client(client, devices, config) -> None:
    """Store references for the web handler to send commands."""
    global _client, _devices, _config
    _client = client
    _devices = devices
    _config = config


def _render_page() -> str:
    date, sunrise, sunset, open_time, close_time = schedule_state.snapshot()

    if date is None:
        content = '<p class="waiting">Waiting for schedule&hellip;</p>'
    else:
        tfmt = "%-I:%M %p"
        content = _SCHEDULE_TEMPLATE.substitute(
            date=date.strftime("%A, %B %-d, %Y"),
            open_time=open_time.strftime(tfmt),
            close_time=close_time.strftime(tfmt),
            sunrise=sunrise.strftime(tfmt),
            sunset=sunset.strftime(tfmt),
        )

    return _PAGE_TEMPLATE.substitute(css=_CSS, content=content)


def _send_command(action: str) -> None:
    """Send a single round of commands to all devices."""
    if _client is None or _devices is None:
        logger.warning("web: command requested but client not ready")
        return
    logger.info("web: sending %s to all devices", action)
    for device in _devices:
        status = _client.execute_action(device.id, action)
        if status in (200, 204):
            logger.debug("web: %s %s -> %d OK", device.name, action, status)
        else:
            logger.warning(
                "web: %s %s -> %s",
                device.name, action,
                status if status != 0 else "error",
            )


class _Handler(BaseHTTPRequestHandler):
    timeout = 10

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            logger.debug("web: client disconnected or timed out")

    def _send_html(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        self._send_html(_render_page().encode())

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        valid_actions = {"Open", "Close"}
        # Expected path: /action/Open or /action/Close
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "action" and parts[1] in valid_actions:
            action = parts[1]
            _send_command(action)
        self._redirect("/")

    def log_message(self, format, *args):
        logger.debug("web: %s", format % args)


def start_server(port: int) -> HTTPServer:
    """Start the status web server on a daemon thread. Returns the server instance."""
    server = HTTPServer(("", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Status web server listening on port %d", port)
    return server
