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
