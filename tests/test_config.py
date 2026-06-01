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


def test_database_port_rejects_boolean():
    env = base_env()
    env["DATABASES_JSON"] = '[{"name":"app1","host":"100.64.0.1","port":true,"database":"app1_db","username":"postgres","password":"secret"}]'

    with pytest.raises(ConfigError, match="port"):
        load_config(env)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_database_port_must_be_valid_tcp_port(port):
    env = base_env()
    env["DATABASES_JSON"] = (
        '[{"name":"app1","host":"100.64.0.1","port":'
        f"{port}"
        ',"database":"app1_db","username":"postgres","password":"secret"}]'
    )

    with pytest.raises(ConfigError, match="port"):
        load_config(env)
