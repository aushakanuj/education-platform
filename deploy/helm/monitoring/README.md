# Monitoring values

Values for a separate monitoring install on the single-node k3s box. These files are not part of the CurioEd chart. CI renders the CurioEd chart only. Nothing here is applied automatically.

Install the CloudNativePG operator and the Barman Cloud plugin yourself if you also enable `cnpg.backup.enabled`. This directory does not install them.

## Memory

Limits are the budget. Requests are what the scheduler reserves. The sum of the limits is **2496Mi (2.4375Gi)**. The 2.5Gi target leaves 64Mi unused.

| Component | Values key | CPU request | Memory request | CPU limit | Memory limit |
| --- | --- | --- | --- | --- | --- |
| Prometheus | `prometheus.prometheusSpec.resources` | 100m | 768Mi | 500m | 1536Mi |
| Alertmanager | `alertmanager.alertmanagerSpec.resources` | 10m | 32Mi | 100m | 64Mi |
| Grafana | `grafana.resources` | 20m | 64Mi | 200m | 128Mi |
| Grafana sidecars | `grafana.sidecar.resources` | 10m | 32Mi | 100m | 64Mi |
| Prometheus Operator | `prometheusOperator.resources` | 10m | 32Mi | 200m | 64Mi |
| kube-state-metrics | `kube-state-metrics.resources` | 10m | 48Mi | 100m | 96Mi |
| node-exporter | `prometheus-node-exporter.resources` | 10m | 16Mi | 50m | 32Mi |
| Loki | `singleBinary.resources` | 50m | 128Mi | 300m | 384Mi |
| Alloy | `alloy.resources` | 10m | 32Mi | 100m | 64Mi |
| Alloy config reloader | `configReloader.resources` | 10m | 32Mi | 100m | 64Mi |
| **Sum** | | **240m** | **1184Mi (1.156Gi)** | | **2496Mi (2.4375Gi)** |

Disk, separate from that RAM budget: Prometheus 8Gi (retention 7 days or 2GiB, whichever comes first), Alertmanager 1Gi, Loki 10Gi. `storageClassName` is `local-path`, the k3s default. The Barman sidecar on the Postgres pod is sized in the CurioEd chart (`cnpg.backup.sidecar`) and is not part of this table.

Grafana's chart creates its own admin Secret. Rotate that password outside git. These files contain no credentials.

## Install

```sh
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 92.10.1 \
  --namespace monitoring --create-namespace \
  -f deploy/helm/monitoring/kube-prometheus-stack-values.yaml

helm upgrade --install loki grafana/loki \
  --version 7.3.0 \
  --namespace monitoring \
  -f deploy/helm/monitoring/loki-values.yaml

helm upgrade --install alloy grafana/alloy \
  --version 1.14.0 \
  --namespace monitoring \
  -f deploy/helm/monitoring/alloy-values.yaml
```

The Prometheus release name `kube-prometheus-stack` matches `monitoring.prometheusRelease` in the CurioEd chart. The values turn off the Helm-release selector so Prometheus also scrapes the PodMonitor that CloudNativePG creates in the application namespace. k3s control-plane jobs (`kubeEtcd`, `kubeControllerManager`, `kubeScheduler`, `kubeProxy`) are disabled because k3s does not publish them at the chart's default addresses.

Loki 7.3.0 runs as one binary on the local disk. MinIO, the canary DaemonSet, and the rules sidecar are disabled. Alloy 1.14.0 tails pod logs and pushes them to `http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`. Promtail is the older shipper; this install uses Alloy.

Alertmanager's default route is a receiver named `null`, so alerts are accepted and not delivered. Commented email and webhook examples live in `kube-prometheus-stack-values.yaml`. Pick one at cutover and keep the password or URL out of git.

## CurioEd scrape and alerts

In the CurioEd chart, `monitoring.enabled` defaults to false. Turning it on renders:

- a ServiceMonitor for the API Service, path `/metrics`, job label `curioed-api`
- a PrometheusRule with four alerts: API 5xx rate above 2% for 5 minutes, API p95 latency above 2 seconds for 5 minutes, more than 3 container restarts in 15 minutes, and no Ready Postgres pod for 5 minutes
- `monitoring.enablePodMonitor: true` on the CNPG Cluster

The API process does not serve `/metrics` today. A search of `backend/` finds no Prometheus client and no metrics route. This chart does not add that route. With the flag on, the ServiceMonitor target will be down and the two HTTP alerts will not fire. The restart alert and the Postgres-down alert use kube-state-metrics, so those work once this stack is installed. Adding `/metrics` is a follow-up after #188.

Smallest change that makes the HTTP alerts real, without editing the Coder-owned modules (`modules/assistant`, `modules/text_to_sql`, `modules/guard`, `ai_platform`, `judge/`, `generation/worker.py`, `config.py`):

1. Add `prometheus-fastapi-instrumentator` with `uv` from `backend/`.
2. In `backend/src/education_platform/main.py`, after the FastAPI app exists, call `Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)`.
3. Leave `/metrics` off the public Traefik routes. The ServiceMonitor scrapes the ClusterIP Service.
4. Keep the default instrumentator names. The rules already use `http_requests_total` and `http_request_duration_seconds_bucket`.

That edit is not in this change.
