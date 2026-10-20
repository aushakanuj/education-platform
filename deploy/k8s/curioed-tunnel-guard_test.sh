#!/usr/bin/env bash
# Stub kubectl and docker. The guard must not touch a real cluster or daemon.
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
guard="${root}/deploy/k8s/curioed-tunnel-guard.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

mkdir -p "${tmp}/bin"
touch "${tmp}/kubeconfig"

cat > "${tmp}/bin/kubectl" << 'EOF'
#!/usr/bin/env bash
printf 'kubectl %s\n' "$*" >> "${STUB_LOG}"
if [[ "${KUBECTL_FAIL:-0}" == 1 ]]; then
  echo "kubectl failed" >&2
  exit 1
fi
if [[ -n "${KUBECTL_STDOUT+x}" ]]; then
  printf '%s' "${KUBECTL_STDOUT}"
  exit 0
fi
cat << JSON
{"spec":{"replicas":1},"status":{"readyReplicas":${READY:-1}}}
JSON
EOF

cat > "${tmp}/bin/docker" << 'EOF'
#!/usr/bin/env bash
printf 'docker %s\n' "$*" >> "${STUB_LOG}"
if [[ "$1" == "ps" ]]; then
  if [[ "$*" == *"-a"* ]]; then
    if [[ "${DOCKER_PS_A_FAIL:-0}" == 1 ]]; then
      echo "docker ps -a failed" >&2
      exit 1
    fi
    printf '%s\n' "${DOCKER_PS_A:-}"
    exit 0
  fi
  if [[ "${DOCKER_PS_FAIL:-0}" == 1 ]]; then
    echo "docker ps failed" >&2
    exit 1
  fi
  printf '%s\n' "${DOCKER_NAMES:-}"
  exit 0
fi
if [[ "$1" == "stop" ]]; then
  if [[ "${DOCKER_STOP_FAIL:-0}" == 1 ]]; then
    echo "docker stop failed" >&2
    exit 1
  fi
  exit 0
fi
echo "unexpected docker invocation: $*" >&2
exit 1
EOF
chmod +x "${tmp}/bin/kubectl" "${tmp}/bin/docker"

failures=0
run_case() {
  local name="$1"
  local expect="$2"
  shift 2
  : > "${tmp}/log"
  local code=0
  env \
    PATH="${tmp}/bin:${PATH}" \
    KUBECONFIG="${tmp}/kubeconfig" \
    STUB_LOG="${tmp}/log" \
    NAMESPACE=curioed \
    DEPLOYMENT=curioed-cloudflared \
    COMPOSE_CONTAINER_PREFIX=education-platform-prod-cloudflared \
    "$@" \
    > "${tmp}/out" 2>&1 || code=$?
  if [[ "${code}" -ne "${expect}" ]]; then
    echo "FAIL ${name}: exit ${code}, expected ${expect}"
    cat "${tmp}/out"
    failures=$((failures + 1))
    return
  fi
  echo "ok ${name}"
}

run_case "kubectl failure exits 1" 1 KUBECTL_FAIL=1 "${guard}"
if grep -q '^docker ' "${tmp}/log"; then
  echo "FAIL kubectl failure still called docker"
  failures=$((failures + 1))
fi
if grep -q 'Traceback' "${tmp}/out"; then
  echo "FAIL kubectl failure printed a traceback"
  failures=$((failures + 1))
fi

run_case "non-json kubectl exits 1" 1 KUBECTL_STDOUT='not-json' "${guard}"
if grep -q '^docker ' "${tmp}/log"; then
  echo "FAIL non-json called docker"
  failures=$((failures + 1))
fi
if grep -q 'Traceback' "${tmp}/out"; then
  echo "FAIL non-json printed a traceback"
  cat "${tmp}/out"
  failures=$((failures + 1))
fi
if ! grep -q 'WARNING: kubectl output is not JSON' "${tmp}/out"; then
  echo "FAIL non-json did not warn"
  cat "${tmp}/out"
  failures=$((failures + 1))
fi

run_case "not ready exits 0 and leaves docker alone" 0 READY=0 "${guard}"
if grep -q '^docker ' "${tmp}/log"; then
  echo "FAIL not-ready called docker"
  cat "${tmp}/log"
  failures=$((failures + 1))
fi

run_case "no matching container exits 0" 0 DOCKER_NAMES=caddy READY=1 "${guard}"
if grep -q '^docker stop ' "${tmp}/log"; then
  echo "FAIL no-match issued docker stop"
  failures=$((failures + 1))
fi

run_case "stopping compose cloudflared exits 2" 2 \
  READY=1 DOCKER_NAMES=education-platform-prod-cloudflared-1 "${guard}"
if ! grep -q '^docker stop education-platform-prod-cloudflared-1$' "${tmp}/log"; then
  echo "FAIL stop case did not stop the compose container"
  cat "${tmp}/log"
  failures=$((failures + 1))
fi

run_case "dry-run does not stop and exits 0" 0 \
  READY=1 DOCKER_NAMES=education-platform-prod-cloudflared-1 "${guard}" --dry-run
if grep -q '^docker stop ' "${tmp}/log"; then
  echo "FAIL dry-run issued docker stop"
  failures=$((failures + 1))
fi

run_case "docker ps failure exits 1" 1 READY=1 DOCKER_PS_FAIL=1 "${guard}"
run_case "docker stop failure exits 1" 1 \
  READY=1 DOCKER_NAMES=education-platform-prod-cloudflared-1 DOCKER_STOP_FAIL=1 "${guard}"
run_case "docker ps -a failure exits 1" 1 \
  READY=1 DOCKER_NAMES=unrelated DOCKER_PS_A_FAIL=1 "${guard}"

run_case "unknown argument exits 1" 1 "${guard}" --nope

if [[ "${failures}" -ne 0 ]]; then
  echo "${failures} tunnel-guard case(s) failed"
  exit 1
fi
echo "tunnel-guard exit codes passed"
