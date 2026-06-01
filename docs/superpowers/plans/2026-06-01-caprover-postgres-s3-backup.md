# CapRover PostgreSQL S3 Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CapRover-deployable Python service that backs up multiple PostgreSQL databases with `pg_dump -Fc` and uploads the dumps to S3-compatible storage on a cron schedule.

**Architecture:** The service has small Python modules for configuration, S3 key generation, backup execution, and scheduling. PostgreSQL dumping stays outside Python via `pg_dump`, while Python validates ENV, runs commands, uploads successful files to S3, logs results, and cleans temporary files.

**Tech Stack:** Python 3.12, boto3, APScheduler, pytest, Docker, PostgreSQL client tools, CapRover Dockerfile deployment.

---

## File Structure

- Create `requirements.txt`: runtime dependencies.
- Create `requirements-dev.txt`: test dependencies.
- Create `src/backup_service/__init__.py`: package marker.
- Create `src/backup_service/config.py`: parse and validate ENV.
- Create `src/backup_service/s3_paths.py`: generate deterministic S3 object keys.
- Create `src/backup_service/backup.py`: run `pg_dump`, upload to S3, clean temporary files.
- Create `src/backup_service/main.py`: configure logging, run startup backup, start cron scheduler.
- Create `tests/test_config.py`: config parsing and validation tests.
- Create `tests/test_s3_paths.py`: S3 object key tests.
- Create `tests/test_backup.py`: backup flow tests with mocked subprocess and S3 client.
- Create `Dockerfile`: CapRover-ready image with PostgreSQL client installed.
- Create `captain-definition`: CapRover Dockerfile deployment config.
- Create `.env.example`: documented ENV sample.
- Create `.gitignore`: ignore Python caches, venvs, local env files, and temporary outputs.
- Create `README.md`: deployment, configuration, Tailscale host guidance, restore instructions.

---

### Task 1: Project Scaffold And Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `src/backup_service/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create dependency files**

Create `requirements.txt`:

```text
boto3==1.34.162
APScheduler==3.10.4
```

Create `requirements-dev.txt`:

```text
-r requirements.txt
pytest==8.3.2
```

- [ ] **Step 2: Create package marker**

Create `src/backup_service/__init__.py`:

```python
"""CapRover PostgreSQL S3 backup service."""
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
.pytest_cache/
*.pyc
*.pyo
*.dump
dist/
build/
```

- [ ] **Step 4: Install dependencies locally**

Run: `python -m pip install -r requirements-dev.txt`

Expected: command exits 0 and installs boto3, APScheduler, and pytest.

- [ ] **Step 5: Run initial test command**

Run: `python -m pytest -q`

Expected: exits 5 with `no tests ran`, because tests have not been created yet.

- [ ] **Step 6: Commit scaffold**

```bash
git add .gitignore requirements.txt requirements-dev.txt src/backup_service/__init__.py
git commit -m "chore: scaffold backup service"
```

---

### Task 2: Configuration Loader

**Files:**
- Create: `tests/test_config.py`
- Create: `src/backup_service/config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
import pytest

from backup_service.config import ConfigError, load_config


def base_env():
    return {
        "BACKUP_CRON": "0 3 * * *",
        "TZ": "Asia/Taipei",
        "RUN_ON_START": "true",
        "S3_ENDPOINT": "http://nas.tailnet.ts.net:9000",
        "S3_ACCESS_KEY": "access",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "postgres-backups",
        "S3_REGION": "us-east-1",
        "S3_PREFIX": "caprover",
        "S3_FORCE_PATH_STYLE": "true",
        "S3_SECURE": "false",
        "DATABASES_JSON": '[{"name":"app1","host":"100.64.0.1","port":5432,"database":"app1_db","username":"postgres","password":"secret"}]',
    }


def test_load_config_parses_env():
    config = load_config(base_env())

    assert config.backup_cron == "0 3 * * *"
    assert config.timezone == "Asia/Taipei"
    assert config.run_on_start is True
    assert config.s3.endpoint == "http://nas.tailnet.ts.net:9000"
    assert config.s3.force_path_style is True
    assert config.s3.secure is False
    assert config.databases[0].name == "app1"
    assert config.databases[0].port == 5432


def test_empty_s3_prefix_is_allowed():
    env = base_env()
    env["S3_PREFIX"] = ""

    config = load_config(env)

    assert config.s3.prefix == ""


def test_missing_required_env_raises_config_error():
    env = base_env()
    del env["S3_BUCKET"]

    with pytest.raises(ConfigError, match="S3_BUCKET"):
        load_config(env)


def test_invalid_databases_json_raises_config_error():
    env = base_env()
    env["DATABASES_JSON"] = "not-json"

    with pytest.raises(ConfigError, match="DATABASES_JSON"):
        load_config(env)


def test_database_requires_name():
    env = base_env()
    env["DATABASES_JSON"] = '[{"host":"100.64.0.1","port":5432,"database":"app1_db","username":"postgres","password":"secret"}]'

    with pytest.raises(ConfigError, match="name"):
        load_config(env)


def test_database_port_must_be_integer():
    env = base_env()
    env["DATABASES_JSON"] = '[{"name":"app1","host":"100.64.0.1","port":"bad","database":"app1_db","username":"postgres","password":"secret"}]'

    with pytest.raises(ConfigError, match="port"):
        load_config(env)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL with `ModuleNotFoundError` or import errors because `config.py` does not exist yet.

- [ ] **Step 3: Implement config loader**

Create `src/backup_service/config.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    name: str
    host: str
    port: int
    database: str
    username: str
    password: str


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    prefix: str
    force_path_style: bool
    secure: bool


@dataclass(frozen=True)
class AppConfig:
    backup_cron: str
    timezone: str
    run_on_start: bool
    s3: S3Config
    databases: list[DatabaseConfig]


def load_config(env: Mapping[str, str]) -> AppConfig:
    backup_cron = _required(env, "BACKUP_CRON")
    timezone = env.get("TZ", "UTC")
    run_on_start = _parse_bool(env.get("RUN_ON_START", "false"), "RUN_ON_START")

    s3 = S3Config(
        endpoint=_required(env, "S3_ENDPOINT"),
        access_key=_required(env, "S3_ACCESS_KEY"),
        secret_key=_required(env, "S3_SECRET_KEY"),
        bucket=_required(env, "S3_BUCKET"),
        region=env.get("S3_REGION", "us-east-1"),
        prefix=env.get("S3_PREFIX", ""),
        force_path_style=_parse_bool(env.get("S3_FORCE_PATH_STYLE", "true"), "S3_FORCE_PATH_STYLE"),
        secure=_parse_bool(env.get("S3_SECURE", "true"), "S3_SECURE"),
    )

    return AppConfig(
        backup_cron=backup_cron,
        timezone=timezone,
        run_on_start=run_on_start,
        s3=s3,
        databases=_parse_databases(_required(env, "DATABASES_JSON")),
    )


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if value is None or value == "":
        raise ConfigError(f"Missing required environment variable: {key}")
    return value


def _parse_bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be true or false")


def _parse_databases(raw: str) -> list[DatabaseConfig]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"DATABASES_JSON is invalid JSON: {exc.msg}") from exc

    if not isinstance(data, list) or not data:
        raise ConfigError("DATABASES_JSON must be a non-empty array")

    return [_parse_database(item, index) for index, item in enumerate(data)]


def _parse_database(item: object, index: int) -> DatabaseConfig:
    if not isinstance(item, dict):
        raise ConfigError(f"DATABASES_JSON[{index}] must be an object")

    name = _string_field(item, "name", index)
    host = _string_field(item, "host", index)
    database = _string_field(item, "database", index)
    username = _string_field(item, "username", index)
    password = _string_field(item, "password", index)
    port = item.get("port")

    if not isinstance(port, int):
        raise ConfigError(f"DATABASES_JSON[{index}].port must be an integer")

    return DatabaseConfig(
        name=name,
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
    )


def _string_field(item: dict[str, object], key: str, index: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or value == "":
        raise ConfigError(f"DATABASES_JSON[{index}].{key} must be a non-empty string")
    return value
```

- [ ] **Step 4: Run config tests**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_config.py -q`

Expected: PASS, 6 tests pass.

- [ ] **Step 5: Commit config loader**

```bash
git add src/backup_service/config.py tests/test_config.py
git commit -m "feat: load backup configuration from env"
```

---

### Task 3: S3 Object Key Generation

**Files:**
- Create: `tests/test_s3_paths.py`
- Create: `src/backup_service/s3_paths.py`

- [ ] **Step 1: Write failing S3 path tests**

Create `tests/test_s3_paths.py`:

```python
from datetime import datetime, timezone

from backup_service.s3_paths import build_backup_key


def test_build_backup_key_with_prefix():
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    key = build_backup_key("caprover", "app1", timestamp)

    assert key == "caprover/app1/2026/06/01/app1-20260601-030000.dump"


def test_build_backup_key_without_prefix():
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    key = build_backup_key("", "app1", timestamp)

    assert key == "app1/2026/06/01/app1-20260601-030000.dump"


def test_build_backup_key_strips_prefix_slashes():
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    key = build_backup_key("/caprover/", "app1", timestamp)

    assert key == "caprover/app1/2026/06/01/app1-20260601-030000.dump"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_s3_paths.py -q`

Expected: FAIL because `s3_paths.py` does not exist yet.

- [ ] **Step 3: Implement S3 path helper**

Create `src/backup_service/s3_paths.py`:

```python
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
```

- [ ] **Step 4: Run S3 path tests**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_s3_paths.py -q`

Expected: PASS, 3 tests pass.

- [ ] **Step 5: Commit S3 path helper**

```bash
git add src/backup_service/s3_paths.py tests/test_s3_paths.py
git commit -m "feat: generate s3 backup keys"
```

---

### Task 4: Backup Runner

**Files:**
- Create: `tests/test_backup.py`
- Create: `src/backup_service/backup.py`

- [ ] **Step 1: Write failing backup runner tests**

Create `tests/test_backup.py`:

```python
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backup_service.backup import BackupResult, run_backup_cycle
from backup_service.config import DatabaseConfig, S3Config


class FakeS3Client:
    def __init__(self):
        self.uploads = []

    def upload_file(self, filename, bucket, key):
        self.uploads.append((filename, bucket, key))


def s3_config():
    return S3Config(
        endpoint="http://nas.tailnet.ts.net:9000",
        access_key="access",
        secret_key="secret",
        bucket="postgres-backups",
        region="us-east-1",
        prefix="caprover",
        force_path_style=True,
        secure=False,
    )


def database(name="app1"):
    return DatabaseConfig(
        name=name,
        host="100.64.0.1",
        port=5432,
        database="app1_db",
        username="postgres",
        password="secret",
    )


def test_run_backup_cycle_uploads_successful_dump(tmp_path, monkeypatch):
    fake_client = FakeS3Client()
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    def fake_run(command, env, capture_output, text, check):
        output_index = command.index("--file") + 1
        Path(command[output_index]).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    results = run_backup_cycle(
        databases=[database()],
        s3=s3_config(),
        s3_client=fake_client,
        timestamp=timestamp,
        temp_dir=tmp_path,
    )

    assert results == [BackupResult(database="app1", success=True, object_key="caprover/app1/2026/06/01/app1-20260601-030000.dump", error="")]
    assert fake_client.uploads[0][1:] == ("postgres-backups", "caprover/app1/2026/06/01/app1-20260601-030000.dump")
    assert list(tmp_path.iterdir()) == []


def test_run_backup_cycle_continues_after_pg_dump_failure(tmp_path, monkeypatch):
    fake_client = FakeS3Client()
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    def fake_run(command, env, capture_output, text, check):
        if any("failed" in arg for arg in command):
            raise subprocess.CalledProcessError(1, command, stderr="connection failed")
        output_index = command.index("--file") + 1
        Path(command[output_index]).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    results = run_backup_cycle(
        databases=[database("failed"), database("ok")],
        s3=s3_config(),
        s3_client=fake_client,
        timestamp=timestamp,
        temp_dir=tmp_path,
    )

    assert results[0].success is False
    assert "connection failed" in results[0].error
    assert results[1].success is True
    assert len(fake_client.uploads) == 1
    assert list(tmp_path.iterdir()) == []


def test_pg_dump_command_uses_database_connection_fields(tmp_path, monkeypatch):
    fake_client = FakeS3Client()
    captured = {}

    def fake_run(command, env, capture_output, text, check):
        captured["command"] = command
        captured["env"] = env
        output_index = command.index("--file") + 1
        Path(command[output_index]).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_backup_cycle(
        databases=[database()],
        s3=s3_config(),
        s3_client=fake_client,
        timestamp=datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc),
        temp_dir=tmp_path,
    )

    assert captured["command"][:9] == ["pg_dump", "-Fc", "--host", "100.64.0.1", "--port", "5432", "--username", "postgres", "--dbname"]
    assert "app1_db" in captured["command"]
    assert captured["env"]["PGPASSWORD"] == "secret"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_backup.py -q`

Expected: FAIL because `backup.py` does not exist yet.

- [ ] **Step 3: Implement backup runner**

Create `src/backup_service/backup.py`:

```python
from __future__ import annotations

import logging
import os
import subprocess
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
        temp_file = temp_dir / f"{db.name}-{timestamp.strftime('%Y%m%d-%H%M%S')}.dump"
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
```

- [ ] **Step 4: Run backup tests**

Run: `$env:PYTHONPATH="src"; python -m pytest tests/test_backup.py -q`

Expected: PASS, 3 tests pass.

- [ ] **Step 5: Commit backup runner**

```bash
git add src/backup_service/backup.py tests/test_backup.py
git commit -m "feat: run postgres backups and upload to s3"
```

---

### Task 5: Main Entrypoint And Scheduler

**Files:**
- Create: `src/backup_service/main.py`

- [ ] **Step 1: Implement application entrypoint**

Create `src/backup_service/main.py`:

```python
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from botocore.client import Config as BotoConfig

from backup_service.backup import run_backup_cycle
from backup_service.config import AppConfig, load_config

LOGGER = logging.getLogger(__name__)


def create_s3_client(config: AppConfig):
    return boto3.client(
        "s3",
        endpoint_url=config.s3.endpoint,
        aws_access_key_id=config.s3.access_key,
        aws_secret_access_key=config.s3.secret_key,
        region_name=config.s3.region,
        use_ssl=config.s3.secure,
        config=BotoConfig(s3={"addressing_style": "path" if config.s3.force_path_style else "auto"}),
    )


def run_once(config: AppConfig, s3_client) -> None:
    timestamp = datetime.now(ZoneInfo(config.timezone))
    results = run_backup_cycle(
        databases=config.databases,
        s3=config.s3,
        s3_client=s3_client,
        timestamp=timestamp,
        temp_dir=Path("/tmp"),
    )
    succeeded = sum(1 for result in results if result.success)
    failed = len(results) - succeeded
    LOGGER.info("Backup cycle complete: %s succeeded, %s failed", succeeded, failed)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = load_config(os.environ)
    s3_client = create_s3_client(config)

    if config.run_on_start:
        run_once(config, s3_client)

    scheduler = BackgroundScheduler(timezone=config.timezone)
    scheduler.add_job(
        lambda: run_once(config, s3_client),
        CronTrigger.from_crontab(config.backup_cron, timezone=ZoneInfo(config.timezone)),
        id="postgres-backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    LOGGER.info("Backup scheduler started with cron '%s'", config.backup_cron)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        LOGGER.info("Shutting down backup scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all Python tests**

Run: `$env:PYTHONPATH="src"; python -m pytest -q`

Expected: PASS, all existing tests pass.

- [ ] **Step 3: Commit entrypoint**

```bash
git add src/backup_service/main.py
git commit -m "feat: add scheduled backup entrypoint"
```

---

### Task 6: Docker And CapRover Deployment Files

**Files:**
- Create: `Dockerfile`
- Create: `captain-definition`

- [ ] **Step 1: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

CMD ["python", "-m", "backup_service.main"]
```

- [ ] **Step 2: Create CapRover definition**

Create `captain-definition`:

```json
{
  "schemaVersion": 2,
  "dockerfilePath": "./Dockerfile"
}
```

- [ ] **Step 3: Build Docker image**

Run: `docker build -t caprover-postgres-s3-backup .`

Expected: image builds successfully and installs `postgresql-client`.

- [ ] **Step 4: Commit deployment files**

```bash
git add Dockerfile captain-definition
git commit -m "chore: add caprover docker deployment"
```

---

### Task 7: Documentation And Example ENV

**Files:**
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Create `.env.example`**

```env
BACKUP_CRON=0 3 * * *
TZ=Asia/Taipei
RUN_ON_START=true
LOG_LEVEL=INFO

S3_ENDPOINT=http://nas-name.tailnet-name.ts.net:9000
S3_ACCESS_KEY=change-me
S3_SECRET_KEY=change-me
S3_BUCKET=postgres-backups
S3_REGION=us-east-1
S3_PREFIX=caprover
S3_FORCE_PATH_STYLE=true
S3_SECURE=false

DATABASES_JSON=[{"name":"app1","host":"100.x.x.x","port":5432,"database":"app1_db","username":"postgres","password":"change-me"}]
```

- [ ] **Step 2: Create `README.md`**

```markdown
# CapRover PostgreSQL S3 Backup

Python backup service for CapRover. It backs up one or more PostgreSQL databases with `pg_dump -Fc` and uploads the `.dump` files to S3-compatible storage such as MinIO.

## Network Model

Install and run Tailscale on the CapRover host, not inside this container. Use Tailscale IPs or MagicDNS names in `DATABASES_JSON` and `S3_ENDPOINT` when the PostgreSQL server or NAS is reachable through the tailnet.

## Required ENV

See `.env.example` for a complete sample.

- `BACKUP_CRON`: cron expression, such as `0 3 * * *`.
- `TZ`: timezone, such as `Asia/Taipei`.
- `RUN_ON_START`: `true` to run one backup cycle at container startup.
- `S3_ENDPOINT`: S3-compatible endpoint URL.
- `S3_ACCESS_KEY`: S3 access key.
- `S3_SECRET_KEY`: S3 secret key.
- `S3_BUCKET`: target bucket.
- `S3_REGION`: S3 region, usually `us-east-1` for MinIO.
- `S3_PREFIX`: object key prefix, such as `caprover`.
- `S3_FORCE_PATH_STYLE`: use `true` for MinIO.
- `S3_SECURE`: use `false` for plain HTTP endpoints and `true` for HTTPS endpoints.
- `DATABASES_JSON`: JSON array of database connection objects.

## DATABASES_JSON

```json
[
  {
    "name": "app1",
    "host": "100.x.x.x",
    "port": 5432,
    "database": "app1_db",
    "username": "postgres",
    "password": "change-me"
  }
]
```

## Backup Layout

Backups are uploaded to:

```text
s3://{S3_BUCKET}/{S3_PREFIX}/{db_name}/{yyyy}/{mm}/{dd}/{db_name}-{timestamp}.dump
```

## Restore

Download a `.dump` file and restore it with:

```bash
pg_restore -h <host> -U <user> -d <database> backup.dump
```

## CapRover Deployment

Deploy this repository to CapRover using the included `captain-definition` and `Dockerfile`. Configure ENV values in the CapRover app settings. Persistent volumes are not required because dump files are temporary and uploaded to S3.
```

- [ ] **Step 3: Commit docs**

```bash
git add .env.example README.md
git commit -m "docs: document caprover backup service"
```

---

### Task 8: Final Verification

**Files:**
- Modify only if verification exposes a defect in files created by earlier tasks.

- [ ] **Step 1: Run full test suite**

Run: `$env:PYTHONPATH="src"; python -m pytest -q`

Expected: PASS, all tests pass.

- [ ] **Step 2: Build Docker image**

Run: `docker build -t caprover-postgres-s3-backup .`

Expected: PASS, Docker image builds successfully.

- [ ] **Step 3: Inspect git status**

Run: `git status --short`

Expected: no output, because all intended files are committed.

---

## Self-Review

- Spec coverage: The plan covers ENV config, Python service, `pg_dump -Fc`, S3-compatible upload, cron scheduling, startup run, multiple DB handling, Tailscale on host, no retention deletion, Docker, CapRover deployment, README, example ENV, and verification.
- Placeholder scan: The plan contains concrete file paths, concrete commands, and complete code snippets for every implementation step.
- Type consistency: `AppConfig`, `S3Config`, `DatabaseConfig`, `BackupResult`, `build_backup_key`, `run_backup_cycle`, and `run_once` signatures are consistent across tasks.
