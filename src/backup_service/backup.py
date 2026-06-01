from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backup_service.config import DatabaseConfig, S3Config
from backup_service.s3_paths import build_backup_key

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupResult:
    database: str
    success: bool
    object_key: str
    error: str


def run_backup_cycle(
    databases: list[DatabaseConfig],
    s3: S3Config,
    s3_client,
    timestamp: datetime,
    temp_dir: Path,
) -> list[BackupResult]:
    results = []

    for db in databases:
        object_key = build_backup_key(s3.prefix, db.name, timestamp)
        with tempfile.NamedTemporaryFile(delete=False, dir=temp_dir, prefix="pg-backup-", suffix=".dump") as handle:
            temp_file = Path(handle.name)
        LOGGER.info("Starting backup for %s", db.name)

        try:
            _run_pg_dump(db, temp_file)
            s3_client.upload_file(str(temp_file), s3.bucket, object_key)
            LOGGER.info("Backup uploaded for %s to s3://%s/%s", db.name, s3.bucket, object_key)
            results.append(BackupResult(database=db.name, success=True, object_key=object_key, error=""))
        except subprocess.CalledProcessError as exc:
            error = exc.stderr or str(exc)
            LOGGER.error("Backup failed for %s: %s", db.name, error)
            results.append(BackupResult(database=db.name, success=False, object_key=object_key, error=error))
        except Exception as exc:
            error = str(exc)
            LOGGER.error("Backup failed for %s: %s", db.name, error)
            results.append(BackupResult(database=db.name, success=False, object_key=object_key, error=error))
        finally:
            temp_file.unlink(missing_ok=True)

    return results


def _run_pg_dump(db: DatabaseConfig, output_file: Path) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = db.password
    command = [
        "pg_dump",
        "-Fc",
        "--host",
        db.host,
        "--port",
        str(db.port),
        "--username",
        db.username,
        "--dbname",
        db.database,
        "--file",
        str(output_file),
    ]
    subprocess.run(command, env=env, capture_output=True, text=True, check=True)
