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

    if type(port) is not int or not 1 <= port <= 65535:
        raise ConfigError(f"DATABASES_JSON[{index}].port must be an integer from 1 to 65535")

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
