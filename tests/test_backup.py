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


def database(name="app1", database_name="app1_db"):
    return DatabaseConfig(
        name=name,
        host="100.64.0.1",
        port=5432,
        database=database_name,
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

    assert results == [BackupResult(database="app1", success=True, object_key="caprover/app1/20260601/app1-20260601-030000.dump", error="")]
    assert fake_client.uploads[0][1:] == ("postgres-backups", "caprover/app1/20260601/app1-20260601-030000.dump")
    assert list(tmp_path.iterdir()) == []


def test_run_backup_cycle_continues_after_pg_dump_failure(tmp_path, monkeypatch):
    fake_client = FakeS3Client()
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    def fake_run(command, env, capture_output, text, check):
        if command[command.index("--dbname") + 1] == "failed_db":
            raise subprocess.CalledProcessError(1, command, stderr="connection failed")
        output_index = command.index("--file") + 1
        Path(command[output_index]).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    results = run_backup_cycle(
        databases=[database("failed", database_name="failed_db"), database("ok")],
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

    assert captured["command"][:9] == ["/usr/lib/postgresql/18/bin/pg_dump", "-Fc", "--host", "100.64.0.1", "--port", "5432", "--username", "postgres", "--dbname"]
    assert "app1_db" in captured["command"]
    assert captured["env"]["PGPASSWORD"] == "secret"


def test_unsafe_database_name_cannot_escape_temp_dir(tmp_path, monkeypatch):
    fake_client = FakeS3Client()
    captured = {}

    def fake_run(command, env, capture_output, text, check):
        file_arg = command[command.index("--file") + 1]
        captured["file_arg"] = file_arg
        Path(file_arg).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_backup_cycle(
        databases=[database("../evil")],
        s3=s3_config(),
        s3_client=fake_client,
        timestamp=datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc),
        temp_dir=tmp_path,
    )

    assert Path(captured["file_arg"]).resolve().is_relative_to(tmp_path.resolve())


def test_repeated_backups_use_distinct_local_temp_files(tmp_path, monkeypatch):
    fake_client = FakeS3Client()
    file_args = []

    def fake_run(command, env, capture_output, text, check):
        file_arg = command[command.index("--file") + 1]
        file_args.append(file_arg)
        Path(file_arg).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_backup_cycle(
        databases=[database(), database()],
        s3=s3_config(),
        s3_client=fake_client,
        timestamp=datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc),
        temp_dir=tmp_path,
    )

    assert len(file_args) == 2
    assert file_args[0] != file_args[1]


def test_upload_failure_removes_local_temp_file(tmp_path, monkeypatch):
    class FailingS3Client:
        def upload_file(self, filename, bucket, key):
            raise RuntimeError("upload failed")

    file_args = []

    def fake_run(command, env, capture_output, text, check):
        file_arg = command[command.index("--file") + 1]
        file_args.append(file_arg)
        Path(file_arg).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    results = run_backup_cycle(
        databases=[database()],
        s3=s3_config(),
        s3_client=FailingS3Client(),
        timestamp=datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc),
        temp_dir=tmp_path,
    )

    assert results[0].success is False
    assert "upload failed" in results[0].error
    assert not Path(file_args[0]).exists()
