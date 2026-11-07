from __future__ import annotations

from pathlib import Path


class FolderListError(RuntimeError):
    """Raised when a folder-list file is missing, unreadable, or empty."""


def read_folder_list(path: Path) -> list[Path]:
    """Read component folder paths from a UTF-8 text file, one per line.

    Blank lines are ignored and surrounding whitespace is stripped. Relative paths are kept as
    written, so they resolve from the current working directory like folders given on the CLI.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        reason = getattr(exc, "strerror", None) or str(exc)
        raise FolderListError(f"Cannot read folder list {path}: {reason}") from exc
    folders = [Path(line.strip()).expanduser() for line in text.splitlines() if line.strip()]
    if not folders:
        raise FolderListError(f"Folder list {path} contains no folder paths")
    return folders
