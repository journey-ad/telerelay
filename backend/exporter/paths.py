"""Filesystem safety helpers for export output."""

import re
from pathlib import Path
from typing import Tuple


class ExportPathError(ValueError):
    """Raised when an export path escapes the configured root."""


# Writers stage `<final>.part` and the HTML archive keeps its record spool in
# `<final>.part.records`; both are renamed or deleted when a run finishes.
PARTIAL_FILE_SUFFIXES = (".part", ".part.records")


def purge_partial_files(root: Path) -> Tuple[int, int]:
    """Remove staged export files and report `(removed, bytes)`.

    A writer publishes its file only in `finalize()`, so a killed process
    leaves the staged copy behind. Call this when no export can be running.
    """
    removed = 0
    freed = 0
    if not root.is_dir():
        return 0, 0
    for path in root.rglob("*"):
        # Directories are never staged files, and a symlink is unlinked rather
        # than followed, so nothing outside the root can be touched.
        if path.is_dir() or not path.name.endswith(PARTIAL_FILE_SUFFIXES):
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        removed += 1
        freed += size
    return removed, freed


def resolve_export_directory(root: Path, subdirectory: str) -> Path:
    """Resolve a user-provided subdirectory while keeping it under root."""
    resolved_root = root.expanduser().resolve()
    requested = Path((subdirectory or "").strip() or ".")
    if requested.is_absolute() or ".." in requested.parts:
        raise ExportPathError("The export directory must be a relative path without '..'.")

    resolved_directory = (resolved_root / requested).resolve()
    try:
        resolved_directory.relative_to(resolved_root)
    except ValueError as exc:
        raise ExportPathError("The export directory is outside the configured root.") from exc

    resolved_directory.mkdir(parents=True, exist_ok=True)
    # Re-resolve to catch symlinks in existing parents.
    final_directory = resolved_directory.resolve()
    try:
        final_directory.relative_to(resolved_root)
    except ValueError as exc:
        raise ExportPathError("The export directory resolves outside the configured root.") from exc
    return final_directory


def safe_filename(value: str, fallback: str = "export", max_length: int = 80) -> str:
    """Convert Telegram titles and task names into portable filenames."""
    cleaned = re.sub(r"[^\w.-]+", "_", (value or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip(" ._")[:max_length].rstrip(" ._")
    return cleaned or fallback
