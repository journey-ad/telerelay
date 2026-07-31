"""Filesystem safety helpers for export output."""

import re
from pathlib import Path


class ExportPathError(ValueError):
    """Raised when an export path escapes the configured root."""


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
