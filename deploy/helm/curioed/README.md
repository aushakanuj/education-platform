# CurioEd Helm chart

Manifests for a k3s install. Nothing in this chart, and nothing in `.github/workflows/images.yml`, deploys CurioEd. Docker Compose production (`deploy/docker-compose.prod.yml`, `deploy/selfhost.sh`, `.github/workflows/deploy.yml`) is unchanged.

The CloudNativePG operator and k3s Traefik are cluster prerequisites. This chart does not install them.

## What it runs

| Piece | Object | Notes |
| --- | --- | --- |
| api | Deployment + Service + HPA | CPU target 65%, min 2, max 4. The Deployment starts at 2 replicas. Probes: `/health/live`, `/health/ready` on port 8000. |
| web | Deployment + Service | nginx image, 2 replicas. |
| worker-docling | Deployment | 1 replica, memory limit 6Gi, Recreate. This is the only worker by default. |
| worker-llm | Deployment | Off unless `workers.llm.enabled=true`. Same process as docling until the app can select queues. |
| migrate | pre-install, pre-upgrade Job | Hook weight 5. Waits for Postgres, then `deploy/migrate.sh` (pg_dump, then Alembic, then promotion). |
| curriculum seed | pre-install, pre-upgrade Job | Hook weight 10, after migrate. `python -m education_platform.modules.materials.seed`. |
| edge | Traefik IngressRoute | `/api` body limit 32MiB, 300s timeouts, SSE flush. `/sw.js` cache headers. |
| cloudflared | Deployment | 2 replicas, pinned tag, token from a Secret. |
| Postgres | CNPG Cluster | `16.15-standard-bookworm` (pgvector is in the standard image). `CREATE EXTENSION vector` at bootstrap. |
| off-site backup | ObjectStore + ScheduledBackup | Off unless `cnpg.backup.enabled=true`. See [Backups](#backups) and [RESTORE.md](RESTORE.md). |
| metrics | ServiceMonitor + PrometheusRule | Off unless `monitoring.enabled=true`. The API does not serve `/metrics` yet. |

Uploads, the Hugging Face cache, and the inductor cache are ReadWriteOnce volumes. The API and the Docling worker share them and must land on the same node. The LLM worker, when enabled, joins that set.

A later `helm upgrade` writes the API replica count back to the HPA minimum. The HPA scales it up again from there.

## Secrets

The chart only stores Secret **names**. Create these yourself:

| Secret | Type | Keys |
| --- | --- | --- |
| `secrets.app.existingSecret` (`curioed-app`) | Opaque | `JWT_SECRET`, `TEXT_TO_SQL_DB_PASSWORD`, `OPENROUTER_API_KEY` (empty string is allowed; the key must exist) |
| `secrets.database.existingSecret` (`curioed-postgres-app`) | `kubernetes.io/basic-auth` | `username` = `education`, `password` URL-safe (letters, digits, hyphen) |
| `secrets.textToSql.existingSecret` (`curioed-postgres-reader`) | `kubernetes.io/basic-auth` | `username` = `text_to_sql_reader`. `password` must be set by hand to the same value as `TEXT_TO_SQL_DB_PASSWORD` in the app Secret. The chart does not copy one Secret into the other. |
| `secrets.tunnel.existingSecret` (`curioed-cloudflared`) | Opaque | `TUNNEL_TOKEN` |
| `cnpg.backup.existingSecret` (`curioed-backup-s3`) | Opaque | `ACCESS_KEY_ID`, `ACCESS_SECRET_KEY`. Create this only when backups are enabled. |

In the Cloudflare dashboard, send the public hostname to `http://traefik.kube-system.svc.cluster.local:80`. Set `api.image.tag` and `web.image.tag` to the commit SHA published by the Images workflow. There is no `latest` tag.

## First install

Helm runs `pre-install` hooks before it creates the Cluster or the backup PVC. A migrate hook in this same release cannot see the database on a first install, so install in two steps:

```sh
helm install curioed deploy/helm/curioed -n curioed --create-namespace \
  --set migrate.enabled=false \
  --set curriculumSeed.enabled=false
# wait until the CloudNativePG cluster is ready
helm upgrade curioed deploy/helm/curioed -n curioed
```

The upgrade turns both hooks back on. Migrate (weight 5) pg_dumps to the backups PVC, then runs Alembic, while the previous pods keep serving. The curriculum seed (weight 10) runs only after that Job succeeds. Migrate's `backoffLimit` is 0 and its deadline is 1800s. The seed deadline is 600s.

Bootstrap `postInitApplicationSQL` runs as the Postgres superuser in the application database and creates the `vector` extension. The `education` role stays a normal owner. Alembic's `CREATE EXTENSION IF NOT EXISTS vector` then finds the extension and does nothing.

## Text-to-SQL password

CNPG creates `text_to_sql_reader` from `secrets.textToSql.existingSecret`. Alembic skips `CREATE ROLE` when that role already exists, and it does not change the password. The API reads `TEXT_TO_SQL_DB_PASSWORD` from the app Secret. Set those two passwords to the same value yourself before the first upgrade. If they differ, text-to-SQL cannot log in.

## Backups

Two copies, with different jobs:

- Every upgrade still runs the migrate hook's `pg_dump` onto the backups PVC. That dump sits on the same disk as the database and is the safety copy for a bad Alembic migration.
- `cnpg.backup.enabled=true` adds an off-site Barman copy. The chart renders an `ObjectStore` (`barmancloud.cnpg.io/v1`) and a `ScheduledBackup`, and it sets the Cluster's WAL archiver plugin to `barman-cloud.cloudnative-pg.io`. You install that plugin in the operator namespace yourself. The chart does not install it.

`endpointURL` and `bucket` are empty by default. Enabling backups without both of them fails the render. Set them to the S3-compatible API you choose. `path` is a prefix inside the bucket (default `curioed/postgres`). The destination is `s3://<bucket>/<path>`. No provider is named in the chart.

```sh
helm upgrade curioed deploy/helm/curioed -n curioed \
  --set cnpg.backup.enabled=true \
  --set cnpg.backup.endpointURL=https://s3.example.invalid \
  --set cnpg.backup.bucket=example-bucket
```

Create Secret `curioed-backup-s3` first, with keys `ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`. Retention defaults to `30d`. The schedule is `0 0 2 * * *` (six fields, seconds first): a base backup at 02:00 UTC. WAL archiving runs continuously. The Barman sidecar on the Postgres pod requests 128Mi and is limited to 256Mi.

Point-in-time recovery into a new Cluster, and the checks to run before serving traffic, are in [RESTORE.md](RESTORE.md).

## Monitoring

`monitoring.enabled` defaults to false. Values and install commands for kube-prometheus-stack, Loki, and Alloy live in [`../monitoring/README.md`](../monitoring/README.md). That stack is sized to 2432Mi (2.375Gi) of memory limits.

Turning the flag on renders a ServiceMonitor for `/metrics` and a PrometheusRule (API 5xx, API p95, pod restarts, Postgres not Ready). The API does not expose Prometheus metrics yet, so the HTTP alerts have nothing to scrape until `prometheus-fastapi-instrumentator` is added in `main.py`. The restart and Postgres alerts use kube-state-metrics and do not need that endpoint. The flag also sets `monitoring.enablePodMonitor` on the CNPG Cluster.

## Check

```sh
deploy/helm/curioed/render-check.sh
```
