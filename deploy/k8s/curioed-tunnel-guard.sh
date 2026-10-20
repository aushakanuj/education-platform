#!/usr/bin/env bash
# Stop Compose cloudflared only when the k8s tunnel has a Ready pod.
# Never starts or scales anything.
# Exit 0 when nothing was stopped.
# Exit 2 when one or more Compose cloudflared containers were stopped.
# Exit 1 when kubectl or docker fails.
set -euo pipefail
set +x

namespace="${NAMESPACE:-curioed}"
deployment="${DEPLOYMENT:-curioed-cloudflared}"
prefix="${COMPOSE_CONTAINER_PREFIX:-education-platform-prod-cloudflared}"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --namespace)
      namespace="$2"
      shift 2
      ;;
    --deployment)
      deployment="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  printf '%s %s\n' "$(date -Is)" "$*"
}

kube() {
  if [[ -n "${KUBECONFIG:-}" ]]; then
    kubectl --kubeconfig "${KUBECONFIG}" "$@"
    return
  fi
  if [[ -r /etc/rancher/k3s/k3s.yaml ]]; then
    kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml "$@"
    return
  fi
  if command -v k3s >/dev/null 2>&1; then
    sudo k3s kubectl "$@"
    return
  fi
  kubectl "$@"
}

if ! deploy_json="$(kube get deploy "${deployment}" --namespace "${namespace}" -o json)"; then
  log "kubectl failed; compose was not touched"
  exit 1
fi

parsed="$(
  printf '%s' "${deploy_json}" | python3 -c '
import json, sys
doc = json.load(sys.stdin)
spec = doc.get("spec") or {}
status = doc.get("status") or {}
print(int(spec.get("replicas") or 0))
print(int(status.get("readyReplicas") or 0))
'
)"
desired="${parsed%%$'\n'*}"
ready="${parsed#*$'\n'}"
log "k8s ${namespace}/${deployment} desired=${desired} ready=${ready}"

if [[ "${ready}" -lt 1 ]]; then
  log "WARNING: k8s cloudflared is not Ready (ready=${ready}); compose was not touched"
  exit 0
fi

if ! names="$(docker ps --filter status=running --format '{{.Names}}')"; then
  log "docker ps failed; no stop was issued"
  exit 1
fi

stopped=0
while IFS= read -r name; do
  [[ -z "${name}" ]] && continue
  case "${name}" in
    "${prefix}"*)
      log "compose running ${name}"
      if [[ "${dry_run}" -eq 1 ]]; then
        log "dry-run would docker stop ${name}"
      else
        if ! docker stop "${name}" >/dev/null; then
          log "docker stop failed for ${name}"
          exit 1
        fi
        log "stopped ${name}"
        stopped=1
      fi
      ;;
  esac
done <<< "${names}"

log "compose containers matching ${prefix}:"
if ! docker ps -a --filter "name=^/${prefix}" --format '{{.Names}} {{.Status}}'; then
  log "docker ps failed"
  exit 1
fi
if [[ "${stopped}" -eq 1 ]]; then
  exit 2
fi
