from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from son_core.config import get_settings


def archive_raw(provider_id: str, filename: str, content: bytes | str) -> Path:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    directory = (
        Path(settings.raw_storage_path)
        / f"{now.year:04d}"
        / f"{now.month:02d}"
        / f"{now.day:02d}"
        / provider_id.lower()
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path
