# CapRover PostgreSQL S3 Backup

Python backup service for CapRover. It backs up one or more PostgreSQL databases with `pg_dump -Fc` and uploads the `.dump` files to S3-compatible storage such as MinIO.

## Network Model

Install and run Tailscale on the CapRover host, not inside this container. Use Tailscale IPs or MagicDNS names in `DATABASES_JSON` and `S3_ENDPOINT` when the PostgreSQL server or NAS is reachable through the tailnet.

## Required ENV

See `.env.example` for a complete sample.

- `BACKUP_CRON`: cron expression, such as `0 3 * * *`.
- `TZ`: timezone, such as `Asia/Taipei`.
- `RUN_ON_START`: `true` to run one backup cycle at container startup.
- `LOG_LEVEL`: log level, such as `INFO`.
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
