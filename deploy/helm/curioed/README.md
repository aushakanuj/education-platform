# CurioEd Helm chart

Manifests for k3s. Rendering this chart does not deploy it. Compose production files are unchanged.

CloudNativePG and k3s Traefik are cluster prerequisites. This chart does not install them.

Image tags are `api.image.tag` and `web.image.tag`. Helm `required` rejects an empty tag. Never `latest`. Chart defaults leave both tags empty, so lint, unittests, and the default CI render pass `--set api.image.tag=ci --set web.image.tag=ci`. `ci` is not a published image. Prod and load-test values default to the images already imported on the PC: `curioed-api:6b7553c` and `curioed-web:6b7553c`, `pullPolicy: IfNotPresent`. `k8s-autodeploy.sh` overrides the prod tags with `--set`.

## Profiles

| File | Namespace | What it is |
| --- | --- | --- |
| `values.yaml` | chosen at install | Hardened defaults. API HPA 1–4 at 65% CPU. Web fixed at 2 replicas, HPA off. Docling on. LLM worker off. |
| `values-prod.yaml` | `curioed` | Compose replacement. API HPA 1–4 and web HPA 1–6 at 60%. Docling on. LLM worker off until `WORKER_QUEUES` exists. Curriculum seed on (PR #197). Real OpenRouter. Tunnel replicas 0 until cutover. |
| `values-loadtest.yaml` | `curioed-loadtest` | Same HPA shape, no workers, llm-mock, demo-data Job, k6 Job. |

## Pod security

The chart does not create a Namespace. Label the namespace before install:

```sh
kubectl label namespace curioed \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted \
  --overwrite
```

`enforce=baseline` is required. Restricted enforce does not fit the current images or CloudNativePG.

`runAsNonRoot`, `runAsUser`, `runAsGroup`, and `fsGroup` are set per workload. Null user, group, and fsGroup are omitted. `readOnlyRootFilesystem` defaults to false on each of api, web, workers, migrate, seed, llm-mock, and demo-data. Setting one of those to true mounts an emptyDir on `/tmp`. Web also mounts emptyDirs on `/var/cache/nginx` and `/var/run`. The defaults stay false until the images run as non-root.

| Workload | runAsNonRoot | runAsUser | Why |
| --- | --- | --- | --- |
| api, docling, llm worker, migrate, curriculum seed, demo-data | false | unset | `deploy/Dockerfile.api` has no `USER`. `python:3.12-slim-bookworm` image config User is empty. **TODO:** add a `USER` line in `Dockerfile.api` (aushak's OK) before turning this on. |
| web | false | unset | `nginx:1.31.7-alpine-slim` has no `USER` and listens on port 80. `CHOWN`, `SETUID`, `SETGID`, and `NET_BIND_SERVICE` are added back. |
| llm-mock | false | unset | `python:3.12.15-slim-bookworm` image config User is empty. |
| cloudflared | true | 65532 | `cloudflare/cloudflared:2026.10.2` image config User is `65532:65532`. |
| k6 | true | 12345 | `grafana/k6:2.3.0` image config User is 12345. |
| CNPG | not set by this chart | 26 via the operator | Image config User is 26. The operator sets `runAsNonRoot` and `runAsUser`. The chart does not override that. |

Other defaults: `allowPrivilegeEscalation: false`, capabilities `drop: [ALL]`, `seccompProfile: RuntimeDefault`. `readOnlyRootFilesystem` stays false. The API Hugging Face cache, uploads, and inductor cache are already volumes. Nginx still writes under `/var` when the flag is on, via the emptyDirs above.

The curriculum seed Job is off in the chart default and on in prod, because #197 merges first. The command is `python -m education_platform.modules.materials.seed`. It is not a hook. The name is `<fullname>-seed-r<revision>`. The prefix is shortened so `-r<revision>` still fits in 63 characters. `backoffLimit` is 1 and `ttlSecondsAfterFinished` is 86400. Autodeploy waits on that Job immediately after `helm upgrade`, so the TTL is not what makes a failure visible. The next upgrade's Helm cleanup removes the previous revision's Job. A failed seed does not roll the release back. It requests 100m CPU and 256Mi, with limits of 1 CPU and 1Gi. Migrate and the seed both start with a `wait-for-db` initContainer that loops `pg_isready` against the CNPG rw service for 120s, using `ghcr.io/cloudnative-pg/postgresql:16.15-standard-trixie`. That initContainer uses the same container securityContext as the Job it waits for. `databaseWait.image.tag` must be a pinned tag. `latest` and an empty tag fail the render. On a first install, disable the migrate hook with `--set migrate.enabled=false` until the CNPG Cluster exists.

The CNPG Cluster and every PVC (uploads, hf-cache, inductor, backups) carry `helm.sh/resource-policy: keep`.

## API

CPU HPA is on by default (65%, min 1, max 4, scale-up window 0, scale-down 300). Raise `minReplicas` to 2 once the database is warm. Prod and load-test values use 1–4 at 60% until the deployed image includes PR #200, and a 1 CPU / 1Gi limit. Requests stay 250m / 512Mi.

`uvicorn --limit-concurrency` defaults to 200. SSE streams count toward that cap.

The image entrypoint execs these args and skips its own JWT-length check and directory create. `JWT_SECRET` is still injected and checked by the application.

Probes: startup and liveness `GET /health/live` (startup about 60s: period 5, failure threshold 12). Readiness `GET /health/ready` with `timeoutSeconds: 2`. `/health/live` does not touch Postgres. MiniLM loads on first embed, not at process start.

A PodDisruptionBudget with `maxUnavailable: 1` is rendered only when the replica floor is at least 2. The default API floor is 1, so there is no API PDB. Web and cloudflared have one at their default of 2 replicas. Prod web HPA min is 1, so that profile does not render a web PDB.

## Workers

No liveness and no readiness. A database ping would kill a parse, and neither worker has a Service. A heartbeat file is still a TODO; this chart does not change application code to add one.

`terminationGracePeriodSeconds` is 600 for docling and 40 for the LLM worker. Docling sets `WORKER_SHUTDOWN_GRACE_SECONDS` to 570. The LLM worker sets it to 25. CD deploys on every merge, so the all-queue docling worker keeps the long grace. A 25s grace would requeue a long ingest on every deploy. Once Coder's worker image is deployed, the process releases its lease on SIGTERM. Until that image is what the cluster runs, Python is PID 1 and ignores SIGTERM.

Both worker Deployments use `strategy: Recreate` and `progressDeadlineSeconds: 1500`. Recreate keeps the old and new pods from overlapping. On one node, two docling pods would be 3Gi each. 1500 seconds is the docling grace plus 900, and it is the same 25 minutes as `k8s-autodeploy.sh`. The Kubernetes default progress deadline is 600s, which is the docling grace itself.

Compose (`deploy/docker-compose.prod.yml` service `worker`) is one container: image `education-platform-api`, command `python -m education_platform.workers`, the same env and uploads/HF/inductor volumes as the API, `stop_grace_period: 30s`, and a `db_ping.py` healthcheck. Prod runs that process as `worker-docling` at 1 replica, 3Gi request and limit, 2 CPU request and limit. `workers.llm` stays off in prod. Both templates still drain every queue until `WORKER_QUEUES` exists. KEDA stays off for that reason.

Docling memory: keep 3Gi if the largest PDF's peak RSS is under 2.5Gi. Otherwise use a 3Gi request and a 5Gi limit.

## Database pool

Set on the API and both workers. Text-to-SQL pool env is API only. Workers do not open that pool.

| Variable | App default after #200 | Chart value |
| --- | --- | --- |
| `DB_POOL_SIZE` | 5 | API 5, workers 2 |
| `DB_MAX_OVERFLOW` | 10 | API 5, workers 2 |
| `DB_POOL_TIMEOUT_SECONDS` | 30 | 30 |
| `DB_POOL_RECYCLE_SECONDS` | off | 1800 |
| `TEXT_TO_SQL_DB_POOL_SIZE` | 5 | API 2 |
| `TEXT_TO_SQL_DB_MAX_OVERFLOW` | 10 | API 3 |
| `WORKER_SHUTDOWN_GRACE_SECONDS` | 25 | docling 570, llm worker 25 |

PR #200 puts the app defaults back to main: overflow 10, recycle off, and text-to-SQL overflow 10. Prod and load-test set every variable in the table so a pod does not inherit those. Worst case with the chart numbers is about 30 connections per API pod, so 180 at HPA max 6, plus the workers and one SSE `LISTEN` connection per stream. That fits under `max_connections` 300. There is no PgBouncer, because `LISTEN` needs a direct connection. Worker `terminationGracePeriodSeconds` is 600 for docling and 40 for the llm worker. The imported image still uses the old pools, so prod and load-test keep the API max at 4 until that image includes #200.

`config.extraEnv` stays an empty map for later names. `config.extraSecretEnv` is a list of `secretKeyRef` entries. No secret values belong in git.

## Platform environment

Non-secret `AI_GATEWAY_*`, `JEV_*`, and `GUARD_*` values render into the platform ConfigMap from `config.platformEnv`. Names and defaults match `backend/src/education_platform/core/config.py`. Empty `JEV_JUDGE_MODE` and `JEV_MODE` match the unset default: the judge treats a blank string as unset.

`AI_GATEWAY_FEATURES`, `AI_GATEWAY_POLICY_CHAT`, `AI_GATEWAY_TEXT_TO_SQL`, `AI_GATEWAY_GENERATION`, `AI_GATEWAY_FEEDBACK`, `AI_GATEWAY_REVIEW_CHAT`, `AI_GATEWAY_AUTHORING`, `AI_GATEWAY_TIMEOUT_CHAT_ANSWER_SECONDS`, `AI_GATEWAY_TIMEOUT_SQL_GENERATE_SECONDS`, `AI_GATEWAY_TIMEOUT_GUARD_SECONDS`, `AI_GATEWAY_TIMEOUT_GENERATION_SECONDS`, `AI_GATEWAY_TIMEOUT_FEEDBACK_SECONDS`, `AI_GATEWAY_MAX_RETRIES`, `AI_GATEWAY_RETRY_BASE_SECONDS`, `AI_GATEWAY_RETRY_MAX_SECONDS`, `AI_GATEWAY_CIRCUIT_FAILURE_THRESHOLD`, `AI_GATEWAY_CIRCUIT_COOLDOWN_SECONDS`, `AI_GATEWAY_CONCURRENCY_INTERACTIVE`, `AI_GATEWAY_CONCURRENCY_GUARD`, `AI_GATEWAY_CONCURRENCY_GENERATION`, `AI_GATEWAY_CONCURRENCY_BATCH`, `JEV_DECISIONS_URL`, `JEV_GUARD_TIMEOUT_SECONDS`, `JEV_MODEL`, `JEV_TIMEOUT_SECONDS`, `JEV_MAX_RETRIES`, `JEV_JUDGE_MODE`, `JEV_MODE`, `JEV_NOUL_ACCEPT`, `JEV_NOUL_REJECT`, `JEV_CONFIDENCE_ACCEPT`, `JEV_CONFIDENCE_REJECT`, `JEV_COVERAGE_ACCEPT_SCORE`, `JEV_COVERAGE_REJECT_SCORE`, `GUARD_JEV_BLOCK_THRESHOLD`, `GUARD_JEV_MODEL`, `GUARD_AUDIT_STORE_PREVIEW`.

`OPENROUTER_API_KEY` stays a `secretKeyRef`.

## Secrets

The chart only stores names. Placeholders below are not real values.

```sh
kubectl create secret generic curioed-app -n curioed \
  --from-literal=JWT_SECRET='REPLACE_ME' \
  --from-literal=TEXT_TO_SQL_DB_PASSWORD='REPLACE_ME' \
  --from-literal=OPENROUTER_API_KEY='REPLACE_ME'

kubectl create secret generic curioed-postgres-app -n curioed \
  --type=kubernetes.io/basic-auth \
  --from-literal=username='REPLACE_ME' \
  --from-literal=password='REPLACE_ME'

kubectl create secret generic curioed-postgres-reader -n curioed \
  --type=kubernetes.io/basic-auth \
  --from-literal=username='REPLACE_ME' \
  --from-literal=password='REPLACE_ME'

kubectl create secret generic curioed-cloudflared -n curioed \
  --from-literal=TUNNEL_TOKEN='REPLACE_ME'
```

`curioed-postgres-reader` password must equal `TEXT_TO_SQL_DB_PASSWORD`. The chart does not copy one Secret into the other. `deploy/k8s/secrets-from-env.sh` creates the same four Secrets from `deploy/.env` without putting values on the process command line.

## Postgres

Default parameters fit a 2Gi limit: `shared_buffers` 512MB, `effective_cache_size` 1GB, `max_connections` 150. Prod raises `max_connections` to 300 and uses `ghcr.io/cloudnative-pg/postgresql:16.15-standard-trixie`. Bootstrap owner is `education`. The managed role is `text_to_sql_reader`.

`cnpg.backup.enabled` defaults to false. Turning it on fails the render. Off-site Barman is not wired. The migrate hook's `pg_dump` is the backup that runs before Alembic.

## Migrate and first install

The migrate Job is a `pre-install,pre-upgrade` hook. On a first install the Cluster does not exist yet, so install in two steps:

Helm's default `--timeout` is 5 minutes. The upgrade below waits 25 minutes, the same as `k8s-autodeploy.sh`, so a docling pod can spend its 600s grace and the new pod still has 900s inside the 1500s progress deadline. The first install does not wait: the CloudNativePG cluster does not exist yet.

```sh
helm install curioed deploy/helm/curioed -n curioed --create-namespace \
  -f deploy/helm/curioed/values-prod.yaml \
  --set api.image.tag=REPLACE_SHA \
  --set web.image.tag=REPLACE_SHA \
  --set migrate.enabled=false
# wait until the CloudNativePG cluster is ready
helm upgrade curioed deploy/helm/curioed -n curioed \
  -f deploy/helm/curioed/values-prod.yaml \
  --set api.image.tag=REPLACE_SHA \
  --set web.image.tag=REPLACE_SHA \
  --wait \
  --timeout 25m
```

The load-test profile turns that hook off. Its demo-data Job waits for Postgres, runs `alembic upgrade head`, the curriculum seed, then `DEMO_SEED=1 python /app/backend/scripts/seed_demo.py`.

## KEDA

Off by default, and it must stay off until `WORKER_QUEUES` exists. Today every worker drains every queue.

The LLM query counts `generation_jobs` and `feedback_summary_jobs` in `queued` or `running`. Status values are the varchar values from `db/types.py` `str_enum`, not native enums. `curriculum_generation_jobs` is excluded because `run_forever()` never passes a curriculum runner (`workers/runner.py`). The docling query matches `workers/lease.py`: queued, or running with a null or expired `locked_until`.

`targetQueryValue` is `"1"`. LLM min 1, max 4, cooldown 600. Docling max 1. TriggerAuthentication reads the existing `curioed-postgres-app` Secret. A dedicated read-only role needs an Alembic `GRANT`, which is out of scope. No migration is added here.

When the API Prometheus trigger is enabled, the CPU HPA is not rendered.

## Caddy alias

The existing tunnel route is `curioed.online` to `http://caddy:80`. Prod renders a Service named exactly `caddy`, port 80, `type: ExternalName`, `externalName: traefik.kube-system.svc.cluster.local`.

ExternalName is a CNAME, not a proxy. The client connects to port 80 on the address that name resolves to. k3s Traefik's Service `traefik` in `kube-system` exposes port 80 named `web`, which is the HTTP entrypoint the IngressRoute uses. That is why the alias port is 80 and not a translated target. IngressRoutes match `Host(curioed.online)` from `domain`.

## LAN NodePort

A chart Service cannot select Traefik pods in `kube-system`. Selectors do not cross namespaces. `deploy/k8s/traefik-nodeport.yaml` is a k3s `HelmChartConfig` that sets `ports.web.nodePort: 30080` on the Traefik chart. It is not applied by this Helm release. Copy it to `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml` only when you want `http://<pc-lan-ip>:30080`. Send `Host: curioed.online` if you are hitting the IngressRoute.

## Tunnel switch and rollback

Compose and k8s share one tunnel token. If both cloudflared processes connect, Cloudflare splits requests across two databases.

Prod keeps `cloudflared.replicas` at 0. The Deployment is a rolling update (`maxUnavailable: 0`, `maxSurge: 1`) with `--metrics 0.0.0.0:2000`, a `/ready` probe on that port, and `terminationGracePeriodSeconds: 40` (cloudflared's grace default is 30s). The image tag is `2026.10.2`. A PDB of `maxUnavailable: 1` appears only when replicas are at least 2. With network policy enabled, kubelet probes are allowed to port 2000 and nothing else is opened; cloudflared egress to Traefik in `kube-system` is already allowed. No extra Traefik middleware is added for SSE.

`deploy/k8s/curioed-tunnel-guard.sh` reads the k8s Deployment. When at least one pod is Ready, it `docker stop`s running containers named `education-platform-prod-cloudflared*`. It does not remove them and it does not start or scale anything. Exit 0 when nothing was stopped, including a tunnel that is not Ready and a `--dry-run`. Exit 2 when it stopped Compose cloudflared. Exit 1 when kubectl or docker fails; a kubectl failure does not touch Docker. The sample oneshot unit is `curioed-tunnel-guard.service` (`SuccessExitStatus=2`, `After=` and `Wants=` `docker.service` and `k3s.service`). `curioed-tunnel-guard.timer` is optional.

Switch:

1. Keep k8s replicas at 0 and confirm `docker ps` shows the Compose connector.
2. Scale k8s to 2: `helm upgrade ... --set cloudflared.replicas=2`.
3. Run the guard (or let the timer run it). It stops the Compose containers.
4. Confirm Compose has 0 running connectors and k8s ready replicas are 2.

Rollback:

1. Scale k8s cloudflared back to 0 and wait until ready is 0.
2. `docker start` the Compose container yourself. The guard will not start it.
3. Confirm one Compose connector and zero k8s replicas.

## Load test

`deploy/loadtest/k6-api.js` ramps 2 minutes each at 10, 50, 100, 200, 300, and 400 requests per second, then idles 6 minutes. Thresholds `p95 < 800ms` and error rate under 1% are reported, not abort conditions.

Mix: 60% authenticated reads, 25% `/health/ready` plus the web index and `/favicon.png`, 15% `POST /api/v1/chats/{id}/messages`. `setup()` logs in demo users. The password is `demo1234`.

Laptop, after the NodePort manifest:

```sh
API_URL=http://192.0.2.10:30080 WEB_URL=http://192.0.2.10:30080 HOST=curioed.online \
  k6 run deploy/loadtest/k6-api.js
```

In cluster, `values-loadtest.yaml` runs the same script from a ConfigMap in a Job capped at 2 CPU and 1Gi, image `grafana/k6:2.3.0`. `API_URL` and `WEB_URL` are the in-cluster Service URLs.

`deploy/loadtest/collect.sh` appends a CSV every 5 seconds: HPA current and desired replicas, `kubectl top`, MemAvailable from `/proc/meminfo`, `pg_stat_activity` counts by state, and p50/p95/p99 from the k6 summary when the Job has printed one. Below 3 GiB MemAvailable, or if `PROD_HEALTH_URL` fails, it deletes the k6 Job and exits non-zero.

## Images on the PC

Build from a separate clone, never `/home/aushakanuj/Documents/work/education-platform`.

```sh
docker build -f deploy/Dockerfile.api -t curioed-api:demo .
docker build -f deploy/Dockerfile.web -t curioed-web:demo --build-arg VITE_API_BASE_URL= .
docker save curioed-api:demo curioed-web:demo | sudo k3s ctr images import -
```

`deploy/k8s/k8s-autodeploy.sh` refuses that working-tree path, takes a `flock`, fetches `origin/main`, and exits when the SHA matches the state file. A dirty clone, tracked or untracked, exits 1 before checkout. A clean clone is then `git checkout --force --detach` of that SHA, and the script aborts if `HEAD` is not that SHA. Before it builds, the CNPG Cluster in namespace `curioed` must be healthy, with `readyInstances` equal to `instances` (`kubectl get cluster.postgresql.cnpg.io -n curioed`). Otherwise it exits 1 and does not build. First install is manual, in this order: CNPG, then restore, then `helm install`. The upgrade is `helm upgrade --install` with `--wait --timeout 25m` and no `--atomic` and no `--wait-for-jobs`. Helm's own default wait is 5 minutes. 25 minutes matches the workers' 1500s progress deadline. After the upgrade succeeds, the script waits on `job/<release>-seed-r<revision>` and exits non-zero with `SEED FAILED` if that Job fails or times out. It does not roll the release back, and it writes the state file only after the seed Job completes.

## Restore checks

`deploy/k8s/restore.sh --dump FILE --counts FILE` runs `pg_restore -Fc` into the CNPG primary, then fails the process if any of these mismatch:

- extension `vector` exists
- roles `education` and `text_to_sql_reader` exist
- `text_to_sql_reader` can `SELECT` `institutions` and `user_roles`
- it cannot `SELECT` `users.password_hash` or `question_answer_keys`
- `alembic_version` equals `b3c4d5e6f7a8` (override with `--revision`)
- each `table,count` row in the counts file matches `count(*)`

## Quota

`limits.cpu` is omitted unless set. The chart default is memory requests 8Gi and limits 14Gi. Steady state with the API at its minimum fits. The API at max 4 plus one surge pod does not fit that 14Gi limit, and the chart default is not raised to hide it.

Prod sets CPU requests 6 and limits 16, memory requests 9Gi and limits 16Gi. Load-test sets CPU requests 5 and limits 14, memory requests 6Gi and limits 12Gi. Those limits overcommit on purpose. `collect.sh` aborting below 3Gi `MemAvailable` is the real guard, and prod and load-test never run at the same time because the load-test namespace is deleted before prod comes up. `render-check.sh` sums CPU and memory for the API at `maxReplicas` plus one surge pod, plus the migrate hook when that Job is rendered. Both profiles fit that peak. LimitRange defaults keep a container that forgot resources from being rejected. The numbers printed by `render-check.sh` are the ones to trust after a values change.

Load-test sets `JEV_JUDGE_MODE=off`. Prod leaves that value unset, which the app treats as shadow. The hardcoded decisions URL in `judge/client.py` is a Coder follow-up.

## Check

```sh
deploy/helm/curioed/render-check.sh
```
