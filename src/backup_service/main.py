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
