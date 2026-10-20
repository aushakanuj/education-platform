#!/usr/bin/env bash
# Prove the scan guard rejects a Trivy invocation that writes no report.
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
script="${root}/deploy/k8s/scan-base-images.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

images="$("${script}" --print)"
if ! printf '%s\n' "${images}" | grep -qx 'nginx:1.27-alpine'; then
  echo "FAIL scan list is missing nginx:1.27-alpine from Dockerfile.web"
  printf '%s\n' "${images}"
  exit 1
fi
for required in \
  python:3.12-slim-bookworm \
  ghcr.io/cloudnative-pg/postgresql:16.15-standard-trixie \
  python:3.12.15-slim-bookworm \
  grafana/k6:2.3.0 \
  cloudflare/cloudflared:2026.10.2
do
  if ! printf '%s\n' "${images}" | grep -qx "${required}"; then
    echo "FAIL scan list is missing ${required}"
    printf '%s\n' "${images}"
    exit 1
  fi
done

cat > "${tmp}/trivy" << 'EOF'
#!/usr/bin/env bash
out=""
prev=""
for arg in "$@"; do
  if [[ "${prev}" == "-o" ]]; then
    out="${arg}"
  fi
  prev="${arg}"
done
image="${!#}"
case "${STUB_MODE}" in
  missing)
    echo "multiple targets cannot be specified" >&2
    exit 1
    ;;
  empty)
    : > "${out}"
    exit 0
    ;;
  ok)
    printf '{"ArtifactName":"%s"}\n' "${image}" > "${out}"
    exit 0
    ;;
  *)
    echo "unknown stub mode" >&2
    exit 1
    ;;
esac
EOF
chmod +x "${tmp}/trivy"

run_mode() {
  local mode="$1"
  local code=0
  env TRIVY="${tmp}/trivy" STUB_MODE="${mode}" SCAN_DIR="${tmp}/scans-${mode}" \
    "${script}" > "${tmp}/${mode}.out" 2> "${tmp}/${mode}.err" || code=$?
  printf '%s' "${code}"
}

missing_code="$(run_mode missing)"
if [[ "${missing_code}" -eq 0 ]]; then
  echo "FAIL broken trivy invocation exited 0"
  cat "${tmp}/missing.err"
  exit 1
fi
if ! grep -q 'missing or empty\|report count' "${tmp}/missing.err"; then
  echo "FAIL broken invocation was not caught by the report guard"
  cat "${tmp}/missing.err"
  exit 1
fi

empty_code="$(run_mode empty)"
if [[ "${empty_code}" -eq 0 ]]; then
  echo "FAIL empty report exited 0"
  exit 1
fi

ok_code="$(run_mode ok)"
if [[ "${ok_code}" -ne 0 ]]; then
  echo "FAIL a complete report was rejected"
  cat "${tmp}/ok.err"
  exit 1
fi

echo "image scan guard passed"
