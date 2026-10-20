#!/usr/bin/env bash
# Build images from a separate clone and helm-upgrade prod. Never --atomic.
set -euo pipefail

clone="${CLONE:-${HOME}/curioed-k8s-clone}"
state_file="${STATE_FILE:-${HOME}/.local/state/curioed-k8s-sha}"
lock_file="${LOCK_FILE:-${HOME}/.local/state/curioed-k8s.lock}"
namespace="${NAMESPACE:-curioed}"
release="${RELEASE:-curioed}"
forbidden="/home/aushakanuj/Documents/work/education-platform"

mkdir -p "$(dirname "${state_file}")" "$(dirname "${lock_file}")"
exec 9>"${lock_file}"
if ! flock -n 9; then
  echo "another autodeploy holds the lock" >&2
  exit 1
fi

if [[ ! -d "${clone}" ]]; then
  echo "clone does not exist: ${clone}" >&2
  exit 1
fi
clone="$(cd "${clone}" && pwd -P)"
if [[ "${clone}" == "${forbidden}" ]]; then
  echo "refusing to build ${forbidden}" >&2
  exit 1
fi

cd "${clone}"
echo "Fetching origin/main in ${clone}"
GIT_TERMINAL_PROMPT=0 git fetch origin main
sha="$(git rev-parse origin/main)"

# checkout --force would discard this work, so refuse first.
# The script creates no files inside the clone, so every porcelain
# line is relevant: tracked changes and untracked files.
if ! dirty="$(git status --porcelain)"; then
  echo "git status failed in ${clone}" >&2
  exit 1
fi
if [[ -n "${dirty}" ]]; then
  echo "refusing to deploy: ${clone} has local changes" >&2
  printf '%s\n' "${dirty}" >&2
  exit 1
fi

if [[ -f "${state_file}" && "$(cat "${state_file}")" == "${sha}" ]]; then
  echo "Already deployed ${sha}"
  exit 0
fi

# First install is manual. Autodeploy only upgrades a cluster that is already healthy.
echo "Checking CNPG in ${namespace}"
if ! cluster_json="$(kubectl get cluster.postgresql.cnpg.io -n "${namespace}" -o json)"; then
  echo "CNPG in ${namespace} is not Ready. First install is manual, in this order: CNPG, then restore, then helm install." >&2
  exit 1
fi
if ! python3 -c '
import json, sys
doc = json.loads(sys.argv[1])
items = doc.get("items")
if items is None:
    items = [doc]
if not items:
    sys.exit(1)
for item in items:
    status = item.get("status") or {}
    phase = str(status.get("phase") or "")
    instances = status.get("instances")
    if instances is None:
        instances = (item.get("spec") or {}).get("instances")
    ready = status.get("readyInstances")
    if "healthy" not in phase.lower() or ready != instances:
        sys.exit(1)
' "${cluster_json}"; then
  echo "CNPG in ${namespace} is not Ready (status must be healthy, with readyInstances equal to instances). First install is manual, in this order: CNPG, then restore, then helm install." >&2
  exit 1
fi

echo "Checking out ${sha}"
git checkout --force --detach "${sha}"
head_sha="$(git rev-parse HEAD)"
if [[ "${head_sha}" != "${sha}" ]]; then
  echo "checkout of origin/main (${sha}) left HEAD at ${head_sha}" >&2
  exit 1
fi

echo "Building api and web ${sha}"
export DOCKER_BUILDKIT=1
docker build -f deploy/Dockerfile.api -t "curioed-api:${sha}" .
docker build -f deploy/Dockerfile.web -t "curioed-web:${sha}" --build-arg VITE_API_BASE_URL= .
echo "Importing images into k3s"
docker save "curioed-api:${sha}" "curioed-web:${sha}" | sudo k3s ctr images import -

echo "Helm upgrade ${release} in ${namespace}"
# Helm's default --timeout is 5m. 15m covers the docling worker's 600s drain.
helm upgrade --install "${release}" deploy/helm/curioed \
  --namespace "${namespace}" \
  --create-namespace \
  -f deploy/helm/curioed/values-prod.yaml \
  --set "api.image.tag=${sha}" \
  --set "web.image.tag=${sha}" \
  --wait \
  --timeout 15m

printf '%s\n' "${sha}" > "${state_file}"
echo "Deploy finished ${sha}. Check the API /health/ready"
