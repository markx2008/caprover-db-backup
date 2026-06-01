from pathlib import Path

from backup_service.config import AppConfig, DatabaseConfig, S3Config
from backup_service import main as main_module


def build_config(run_on_start=False):
    return AppConfig(
        backup_cron="15 2 * * *",
        timezone="Asia/Taipei",
        run_on_start=run_on_start,
        s3=S3Config(
            endpoint="http://s3.example.test",
            access_key="access",
            secret_key="secret",
            bucket="backups",
            region="us-east-1",
            prefix="caprover",
            force_path_style=True,
            secure=False,
        ),
        databases=[
            DatabaseConfig(
                name="app",
                host="postgres.example.test",
                port=5432,
                database="app_db",
                username="postgres",
                password="secret",
            )
        ],
    )


def test_run_once_uses_configured_timezone_and_tmp(monkeypatch):
    calls = []

    def fake_run_backup_cycle(**kwargs):
        calls.append(kwargs)
        return []

    config = build_config()
    s3_client = object()
    monkeypatch.setattr(main_module, "run_backup_cycle", fake_run_backup_cycle)

    main_module.run_once(config, s3_client)

    assert calls[0]["databases"] == config.databases
    assert calls[0]["s3"] == config.s3
    assert calls[0]["s3_client"] is s3_client
    assert calls[0]["temp_dir"] == Path("/tmp")
    assert calls[0]["timestamp"].tzinfo is not None
    assert calls[0]["timestamp"].tzinfo.key == "Asia/Taipei"


def test_main_configures_scheduler_and_shuts_down_when_stop_event_is_set(monkeypatch):
    config = build_config()
    s3_client = object()
    scheduler_instances = []
    cron_calls = []
    run_once_calls = []
    event_instances = []

    class FakeScheduler:
        def __init__(self, timezone):
            self.timezone = timezone
            self.jobs = []
            self.started = False
            self.shutdown_called = False
            scheduler_instances.append(self)

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

        def start(self):
            self.started = True

        def shutdown(self):
            self.shutdown_called = True

    class FakeCronTrigger:
        @staticmethod
        def from_crontab(cron, timezone):
            cron_calls.append((cron, timezone))
            return "cron-trigger"

    class FakeEvent:
        def __init__(self):
            self.wait_called = False
            self.set_called = False
            event_instances.append(self)

        def wait(self):
            self.wait_called = True

        def set(self):
            self.set_called = True

    monkeypatch.setattr(main_module, "load_config", lambda env: config)
    monkeypatch.setattr(main_module, "create_s3_client", lambda loaded_config: s3_client)
    monkeypatch.setattr(main_module, "run_once", lambda loaded_config, client: run_once_calls.append((loaded_config, client)))
    monkeypatch.setattr(main_module, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(main_module, "CronTrigger", FakeCronTrigger)
    monkeypatch.setattr(main_module.threading, "Event", FakeEvent)

    main_module.main()

    scheduler = scheduler_instances[0]
    assert scheduler.timezone == "Asia/Taipei"
    assert scheduler.jobs == [
        (
            scheduler.jobs[0][0],
            "cron-trigger",
            {
                "id": "postgres-backup",
                "replace_existing": True,
                "max_instances": 1,
                "coalesce": True,
            },
        )
    ]
    assert cron_calls[0][0] == "15 2 * * *"
    assert cron_calls[0][1].key == "Asia/Taipei"
    assert scheduler.started is True
    assert event_instances[0].wait_called is True
    assert scheduler.shutdown_called is True
    assert run_once_calls == []


def test_main_registers_sigterm_and_sigint_handlers(monkeypatch):
    config = build_config()
    registered_handlers = {}

    class FakeScheduler:
        def __init__(self, timezone):
            pass

        def add_job(self, func, trigger, **kwargs):
            pass

        def start(self):
            pass

        def shutdown(self):
            pass

    class FakeCronTrigger:
        @staticmethod
        def from_crontab(cron, timezone):
            return "cron-trigger"

    class FakeEvent:
        def wait(self):
            pass

        def set(self):
            pass

    def fake_signal(signum, handler):
        registered_handlers[signum] = handler

    monkeypatch.setattr(main_module, "load_config", lambda env: config)
    monkeypatch.setattr(main_module, "create_s3_client", lambda loaded_config: object())
    monkeypatch.setattr(main_module, "run_once", lambda loaded_config, client: None)
    monkeypatch.setattr(main_module, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(main_module, "CronTrigger", FakeCronTrigger)
    monkeypatch.setattr(main_module.threading, "Event", FakeEvent)
    monkeypatch.setattr(main_module.signal, "signal", fake_signal)

    main_module.main()

    assert main_module.signal.SIGTERM in registered_handlers
    assert main_module.signal.SIGINT in registered_handlers
