"""Simple status webserver for bond-blinds."""

from __future__ import annotations

import datetime
import logging
import string
import threading
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


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = _render_page().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.debug("web: %s", format % args)


def start_server(port: int) -> HTTPServer:
    """Start the status web server on a daemon thread. Returns the server instance."""
    server = HTTPServer(("", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Status web server listening on port %d", port)
    return server
