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
# Helm's default --timeout is 5m. 25m matches the Recreate workers'
# progressDeadlineSeconds of 1500, which covers a 600s drain.
helm upgrade --install "${release}" deploy/helm/curioed \
  --namespace "${namespace}" \
  --create-namespace \
  -f deploy/helm/curioed/values-prod.yaml \
  --set "api.image.tag=${sha}" \
  --set "web.image.tag=${sha}" \
  --wait \
  --timeout 25m

# --wait does not wait for a plain Job. Check this revision's seed before
# recording the SHA. A failure is printed and exits non-zero. There is no
# helm rollback. The next upgrade removes the previous revision's Job.
seed_timeout="${SEED_WAIT_TIMEOUT:-15m}"
if ! release_json="$(helm status "${release}" --namespace "${namespace}" -o json)"; then
  echo "SEED FAILED: helm status did not return the release revision" >&2
  exit 1
fi
if ! revision="$(printf '%s' "${release_json}" | python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
version = doc.get("version")
if not isinstance(version, int) or version < 1:
    sys.exit(1)
print(version)
')"; then
  echo "SEED FAILED: helm status did not include a revision" >&2
  exit 1
fi
seed_job="${release}-seed-r${revision}"
echo "Waiting for job/${seed_job} (timeout ${seed_timeout})"
# Close the lock fd. A child that inherited it would keep the flock after exit.
kubectl wait --namespace "${namespace}" --for=condition=complete "job/${seed_job}" --timeout="${seed_timeout}" >/dev/null 2>&1 9>&- &
complete_pid=$!
kubectl wait --namespace "${namespace}" --for=condition=failed "job/${seed_job}" --timeout="${seed_timeout}" >/dev/null 2>&1 9>&- &
failed_pid=$!
complete_rc=""
failed_rc=""
seed_outcome="timeout"
while [[ -z "${complete_rc}" || -z "${failed_rc}" ]]; do
  if [[ -z "${failed_rc}" ]] && ! kill -0 "${failed_pid}" 2>/dev/null; then
    failed_rc=0
    wait "${failed_pid}" || failed_rc=$?
    if [[ "${failed_rc}" -eq 0 ]]; then
      seed_outcome="failed"
      break
    fi
  fi
  if [[ -z "${complete_rc}" ]] && ! kill -0 "${complete_pid}" 2>/dev/null; then
    complete_rc=0
    wait "${complete_pid}" || complete_rc=$?
    if [[ "${complete_rc}" -eq 0 ]]; then
      seed_outcome="complete"
      break
    fi
  fi
  if [[ -n "${complete_rc}" && -n "${failed_rc}" ]]; then
    seed_outcome="timeout"
    break
  fi
  sleep 0.2
done
if kill -0 "${complete_pid}" 2>/dev/null; then
  kill "${complete_pid}" 2>/dev/null || true
  wait "${complete_pid}" 2>/dev/null || true
fi
if kill -0 "${failed_pid}" 2>/dev/null; then
  kill "${failed_pid}" 2>/dev/null || true
  wait "${failed_pid}" 2>/dev/null || true
fi
if [[ "${seed_outcome}" != "complete" ]]; then
  echo "SEED FAILED: job/${seed_job} ${seed_outcome}" >&2
  kubectl logs --namespace "${namespace}" --all-containers "job/${seed_job}" >&2 || true
  exit 1
fi

printf '%s\n' "${sha}" > "${state_file}"
echo "Deploy finished ${sha}. Check the API /health/ready"
