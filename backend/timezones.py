"""Supported timezone catalog and system default resolution."""

import os
from datetime import datetime
from pathlib import Path


TIMEZONE_OPTIONS = (
    (-11, "Pacific/Pago_Pago"),
    (-10, "Pacific/Honolulu"),
    (-9, "Pacific/Gambier"),
    (-8, "Pacific/Pitcairn"),
    (-8, "America/Los_Angeles"),
    (-7, "America/Phoenix"),
    (-7, "America/Denver"),
    (-6, "America/Guatemala"),
    (-6, "America/Chicago"),
    (-5, "America/Bogota"),
    (-5, "America/New_York"),
    (-4, "America/Caracas"),
    (-3, "America/Argentina/Buenos_Aires"),
    (-2, "America/Noronha"),
    (-1, "Atlantic/Cape_Verde"),
    (0, "Etc/UTC"),
    (0, "Europe/London"),
    (1, "Africa/Lagos"),
    (1, "Europe/Paris"),
    (1, "Europe/Berlin"),
    (2, "Africa/Johannesburg"),
    (3, "Africa/Nairobi"),
    (4, "Asia/Dubai"),
    (5, "Asia/Karachi"),
    (6, "Asia/Dhaka"),
    (7, "Asia/Bangkok"),
    (8, "Asia/Kuala_Lumpur"),
    (8, "Asia/Shanghai"),
    (8, "Asia/Hong_Kong"),
    (8, "Asia/Taipei"),
    (8, "Asia/Singapore"),
    (9, "Pacific/Palau"),
    (9, "Asia/Tokyo"),
    (9, "Asia/Seoul"),
    (10, "Australia/Brisbane"),
    (10, "Australia/Sydney"),
    (11, "Pacific/Noumea"),
    (12, "Pacific/Tarawa"),
    (13, "Pacific/Fakaofo"),
    (14, "Pacific/Kiritimati"),
)
TIMEZONE_NAMES = tuple(name for _, name in TIMEZONE_OPTIONS)
TIMEZONE_NAME_SET = frozenset(TIMEZONE_NAMES)


def timezone_label(offset: int, name: str) -> str:
    return f"(GMT{offset:+03d}:00) {name}"


def system_timezone() -> str:
    configured = os.getenv("TZ")
    if configured in TIMEZONE_NAME_SET:
        return configured

    local = datetime.now().astimezone()
    local_name = getattr(local.tzinfo, "key", None)
    if local_name in TIMEZONE_NAME_SET:
        return local_name

    localtime = str(Path("/etc/localtime").resolve())
    if "/zoneinfo/" in localtime:
        local_name = localtime.split("/zoneinfo/", 1)[1]
        if local_name in TIMEZONE_NAME_SET:
            return local_name

    offset = local.utcoffset()
    offset_hours = int(offset.total_seconds() // 3600) if offset else 0
    return next(
        (name for hours, name in TIMEZONE_OPTIONS if hours == offset_hours),
        "Etc/UTC",
    )
