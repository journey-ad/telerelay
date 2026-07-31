"""Application version and GitHub update-check helpers."""

import json
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

from backend import __version__

REPOSITORY = "journey-ad/telerelay"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
VERSION_INFO_URL = "https://journey-ad.github.io/telerelay/version.json"
VERSION_ENV = "TELERELAY_VERSION"
VERSION_FILE = Path(__file__).resolve().parent / ".version"
COMMIT_ENV = "TELERELAY_COMMIT"
COMMIT_FILE = Path(__file__).resolve().parent / ".commit"


def current_version() -> str:
    value = os.getenv(VERSION_ENV, "").strip()
    if value:
        return value
    if VERSION_FILE.is_file():
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return __version__


def _short_hash(value: str) -> str:
    value = value.strip()
    return value[:7] if len(value) > 7 else value


@lru_cache(maxsize=None)
def current_commit() -> str | None:
    value = os.getenv(COMMIT_ENV, "").strip()
    if value:
        return _short_hash(value)
    if COMMIT_FILE.is_file():
        value = COMMIT_FILE.read_text(encoding="utf-8").strip()
        if value:
            return _short_hash(value)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return _short_hash(result.stdout) if result.stdout.strip() else None


def _version_tuple(value: str) -> tuple[int, ...]:
    clean = value.strip().lstrip("vV")
    parts = []
    for part in clean.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


@dataclass
class UpdateInfo:
    current_version: str
    latest_tag: str | None = None
    latest_version: str | None = None
    update_available: bool = False
    release_url: str | None = None
    published_at: str | None = None
    homepage: str | None = None
    repository: str | None = None
    image: str | None = None
    commit: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "current_version": self.current_version,
            "latest_tag": self.latest_tag,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "release_url": self.release_url,
            "published_at": self.published_at,
            "homepage": self.homepage,
            "repository": self.repository,
            "image": self.image,
            "commit": self.commit,
            "error": self.error,
        }


def check_update(timeout: float = 8.0) -> UpdateInfo:
    current = current_version()
    info = UpdateInfo(current_version=current)
    try:
        request = url_request.Request(VERSION_INFO_URL, headers={"User-Agent": "telerelay"})
        with url_request.urlopen(request, timeout=timeout) as response:
            release = json.load(response)
    except url_error.HTTPError as exc:
        info.error = f"HTTP {exc.code}"
        return info
    except (url_error.URLError, TimeoutError, OSError, ValueError) as exc:
        info.error = str(exc)
        return info

    latest_tag = release.get("tag_name")
    latest_version = _version_tuple(latest_tag) if latest_tag else ()
    if not latest_version:
        info.error = "version info has no tag_name"
        return info
    info.latest_tag = latest_tag
    info.latest_version = ".".join(str(part) for part in latest_version)
    info.release_url = release.get("url")
    info.published_at = release.get("date") or release.get("published_at")
    info.homepage = release.get("homepage")
    info.repository = release.get("repository")
    info.image = release.get("image")
    info.commit = release.get("commit")
    info.update_available = latest_version > _version_tuple(current)
    return info
