# CapRover PostgreSQL S3 備份服務

這是一個可部署在 CapRover 的 Python 備份服務。它會定時使用 `pg_dump -Fc` 備份一個或多個 PostgreSQL database，並把 `.dump` 檔上傳到 S3-compatible storage，例如 NAS 上的 MinIO。

## 網路架構

備份容器需要能連到 PostgreSQL 和 S3-compatible endpoint。請在 `DATABASES_JSON` 的 `host` 填入容器可連線的 PostgreSQL host，並在 `S3_ENDPOINT` 填入容器可連線的 S3 endpoint。

## CapRover ENV 範例

以下可以直接複製到 CapRover App Configs 的 Environment Variables，再把 placeholder 改成你的實際值：

```env
BACKUP_CRON=0 3 * * *
TZ=Asia/Taipei
RUN_ON_START=true
LOG_LEVEL=INFO

S3_ENDPOINT=http://s3.example.local:9000
S3_ACCESS_KEY=change-me
S3_SECRET_KEY=change-me
S3_BUCKET=postgres-backups
S3_REGION=us-east-1
S3_PREFIX=caprover
S3_FORCE_PATH_STYLE=true
S3_SECURE=false

DATABASES_JSON=[{"name":"app1","host":"postgres-1.example.local","port":5432,"database":"app1_db","username":"postgres","password":"change-me"},{"name":"app2","host":"postgres-2.example.local","port":5432,"database":"app2_db","username":"postgres","password":"change-me"}]
```

## ENV 說明

- `BACKUP_CRON`: 備份排程，使用 cron 表達式，例如 `0 3 * * *` 代表每天凌晨 3 點。
- `TZ`: 時區，例如 `Asia/Taipei`。
- `RUN_ON_START`: 設為 `true` 時，容器啟動後會先立即跑一次備份。
- `LOG_LEVEL`: log 等級，例如 `INFO`。
- `S3_ENDPOINT`: S3-compatible endpoint，例如 NAS MinIO 的 URL。
- `S3_ACCESS_KEY`: S3 access key。
- `S3_SECRET_KEY`: S3 secret key。
- `S3_BUCKET`: 備份要上傳到的 bucket。
- `S3_REGION`: S3 region；MinIO 通常可用 `us-east-1`。
- `S3_PREFIX`: S3 object key 前綴，例如 `caprover`。
- `S3_FORCE_PATH_STYLE`: MinIO 建議設為 `true`。
- `S3_SECURE`: endpoint 使用 HTTP 時設為 `false`，HTTPS 時設為 `true`。
- `DATABASES_JSON`: PostgreSQL database 清單，JSON array 格式。

## DATABASES_JSON 格式

```json
[
  {
    "name": "app1",
    "host": "postgres-1.example.local",
    "port": 5432,
    "database": "app1_db",
    "username": "postgres",
    "password": "change-me"
  }
]
```

欄位說明：

- `name`: 備份識別名稱，會用在 log 和 S3 路徑。
- `host`: PostgreSQL host，可填 CapRover service name、內網 IP、DNS 名稱或任何容器可連線的位址。
- `port`: PostgreSQL port，通常是 `5432`。
- `database`: 要備份的 database 名稱。
- `username`: PostgreSQL 使用者。
- `password`: PostgreSQL 密碼。

## 備份路徑

備份檔會上傳到：

```text
s3://{S3_BUCKET}/{S3_PREFIX}/{db_name}/{yyyymmdd}/{db_name}-{timestamp}.dump
```

範例：

```text
s3://postgres-backups/caprover/app1/20260601/app1-20260601-030000.dump
```

## 還原方式

先從 S3/MinIO 下載 `.dump` 檔，再用 `pg_restore` 還原：

```bash
pg_restore -h <host> -U <user> -d <database> backup.dump
```

## CapRover 部署

此 repo 已包含 `captain-definition` 和 `Dockerfile`，可直接部署到 CapRover。

部署後在 CapRover app 的 Environment Variables 填入上方 ENV。此服務不需要 persistent volume，因為備份檔只會暫存在容器 `/tmp`，上傳完成或失敗後都會清除。

## 注意事項

- 備份容器本身只負責排程、`pg_dump` 和 S3 上傳；網路連線能力由部署環境提供。
- ENV 使用通用 `S3_` 命名。
- 服務不會刪除舊備份；保留策略請在 NAS、MinIO 或 S3 lifecycle 設定。
- 單一 database 備份失敗不會中斷其他 database 的備份。
