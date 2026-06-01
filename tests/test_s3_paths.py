from datetime import datetime, timezone

from backup_service.s3_paths import build_backup_key


def test_build_backup_key_with_prefix():
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    key = build_backup_key("caprover", "app1", timestamp)

    assert key == "caprover/app1/20260601/app1-20260601-030000.dump"


def test_build_backup_key_without_prefix():
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    key = build_backup_key("", "app1", timestamp)

    assert key == "app1/20260601/app1-20260601-030000.dump"


def test_build_backup_key_strips_prefix_slashes():
    timestamp = datetime(2026, 6, 1, 3, 0, 0, tzinfo=timezone.utc)

    key = build_backup_key("/caprover/", "app1", timestamp)

    assert key == "caprover/app1/20260601/app1-20260601-030000.dump"
