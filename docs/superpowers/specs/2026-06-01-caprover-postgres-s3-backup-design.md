# CapRover PostgreSQL S3 Backup Design

## Goal

Build a CapRover-deployable backup service that periodically backs up multiple PostgreSQL databases and uploads the backup files to an S3-compatible endpoint. The target storage is a NAS-hosted MinIO service, but configuration names should use generic `S3_` prefixes.

## Deployment Model

The backup service runs as a long-lived Python application inside a Docker container deployed by CapRover.

Tailscale is installed and managed on the CapRover host, not inside the backup container. Database hosts and the S3 endpoint may use Tailscale IPs or MagicDNS names, but the container does not run `tailscaled` and does not require privileged mode, `/dev/net/tun`, or extra network capabilities.

## Runtime Behavior

On startup, the service runs one backup cycle immediately when `RUN_ON_START=true`. After startup, it runs backup cycles according to the cron expression in `BACKUP_CRON`.

Each backup cycle reads the database list from `DATABASES_JSON`, backs up each database independently, uploads successful dumps to S3, removes local temporary files, and logs a summary.

A failure for one database does not stop backups for the remaining databases in the same cycle.

## Backup Format

The service uses PostgreSQL's `pg_dump` command with the custom format:

```bash
pg_dump -Fc
```

This produces `.dump` files that can be restored with `pg_restore`.

The Docker image must include the PostgreSQL client package so `pg_dump` is available at runtime.

## Configuration

All runtime settings are provided through environment variables.

```env
BACKUP_CRON=0 3 * * *
TZ=Asia/Taipei
RUN_ON_START=true

S3_ENDPOINT=http://nas-name.tailnet-name.ts.net:9000
S3_ACCESS_KEY=xxx
S3_SECRET_KEY=xxx
S3_BUCKET=postgres-backups
S3_REGION=us-east-1
S3_PREFIX=caprover
S3_FORCE_PATH_STYLE=true
S3_SECURE=false

DATABASES_JSON=[
  {
    "name": "app1",
    "host": "100.x.x.x",
    "port": 5432,
    "database": "app1_db",
    "username": "postgres",
    "password": "secret"
  }
]
```

`DATABASES_JSON` is an array of database definitions. Each item must include:

- `name`: logical backup name used in object paths and logs
- `host`: PostgreSQL host, which may be a CapRover service name, Tailscale IP, or MagicDNS name
- `port`: PostgreSQL TCP port
- `database`: database name passed to `pg_dump`
- `username`: PostgreSQL username
- `password`: PostgreSQL password

## S3 Object Layout

Backup files are uploaded to:

```text
s3://{S3_BUCKET}/{S3_PREFIX}/{db_name}/{yyyy}/{mm}/{dd}/{db_name}-{timestamp}.dump
```

Example:

```text
s3://postgres-backups/caprover/app1/2026/06/01/app1-20260601-030000.dump
```

If `S3_PREFIX` is empty, the path starts with `{db_name}/...`.

## Error Handling

The service validates required environment variables during startup. Invalid global configuration prevents the service from starting.

For each database backup:

- Create a temporary dump file under `/tmp`.
- Run `pg_dump` with the database password passed through the `PGPASSWORD` environment variable.
- Upload only after `pg_dump` exits successfully.
- Delete the temporary file after success or failure.
- Log the database name, destination object key, duration, and success or failure status.

The service does not upload partial or failed dumps.

## Retention

The service does not delete old backups. Retention is managed outside the app through NAS, MinIO, or S3 lifecycle policy.

## Restore

Backups are restored with `pg_restore`:

```bash
pg_restore -h <host> -U <user> -d <database> backup.dump
```

## Non-Goals

- Running Tailscale inside the backup container.
- Managing S3 lifecycle or deleting old backups.
- Backing up PostgreSQL roles or cluster-level globals with `pg_dumpall`.
- Providing a web UI.

## Implementation Components

The implementation should include:

- Python application entrypoint.
- Configuration loader and validator.
- Backup runner that invokes `pg_dump`.
- S3 uploader using S3-compatible settings.
- Cron scheduler.
- Dockerfile suitable for CapRover deployment.
- README with CapRover deployment notes and ENV examples.
- Example ENV file with placeholder values.

## Verification

Verification should cover:

- Valid and invalid `DATABASES_JSON` parsing.
- Required ENV validation.
- S3 object key generation.
- `pg_dump` command construction.
- Behavior when one database backup fails and another succeeds.
- Docker image build.
