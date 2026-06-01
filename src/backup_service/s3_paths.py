from __future__ import annotations

from datetime import datetime


def build_backup_key(prefix: str, db_name: str, timestamp: datetime) -> str:
    date_path = timestamp.strftime("%Y/%m/%d")
    file_name = f"{db_name}-{timestamp.strftime('%Y%m%d-%H%M%S')}.dump"
    prefix_part = prefix.strip("/")

    parts = [db_name, date_path, file_name]
    if prefix_part:
        parts.insert(0, prefix_part)

    return "/".join(parts)
