"""Dawn/dusk calculation using astral."""

from __future__ import annotations

import datetime

from astral import LocationInfo
from astral.sun import sun


def get_solar_times(
    date: datetime.date,
    latitude: float,
    longitude: float,
) -> tuple[datetime.datetime, datetime.datetime]:
    """Return (sunrise, sunset) as timezone-aware datetimes for the given date and location.

    "dawn" in config maps to sunrise (sun at horizon) and "dusk" maps to sunset,
    as that matches common usage. Times are returned in the local system timezone.
    """
    location = LocationInfo(latitude=latitude, longitude=longitude)
    local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
    s = sun(location.observer, date=date, tzinfo=local_tz)
    return s["sunrise"], s["sunset"]
