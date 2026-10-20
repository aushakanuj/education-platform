#!/usr/bin/env bash
# One Trivy invocation per image. The image list is the external FROM lines
# in deploy/Dockerfile* plus the third-party chart images. A missing, empty,
# or short JSON report fails the run even when Trivy exits 0.
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
ignore="${root}/.trivyignore"
k6_ignore="${root}/.trivyignore.k6"
trivy_bin="${TRIVY:-trivy}"
outdir="${SCAN_DIR:-$(mktemp -d)}"

mapfile -t images < <(python3 - "${root}" << 'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
found = []

def add(image: str) -> None:
    image = image.strip().strip('"').strip("'")
    if not image or image in found:
        return
    found.append(image)

for path in sorted((root / "deploy").glob("Dockerfile*")):
    stages = {}
    last = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        match = re.match(
            r"(?i)^FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?",
            line,
        )
        if match is None:
            continue
        image, alias = match.group(1), match.group(2)
        last = image
        if alias:
            stages[alias] = image
    if last is None:
        continue
    seen = set()
    while last in stages and last not in seen:
        seen.add(last)
        last = stages[last]
    if last.lower() == "scratch":
        continue
    if "/" not in last and ":" not in last and "@" not in last:
        continue
    add(last)

values = (root / "deploy/helm/curioed/values.yaml").read_text(encoding="utf-8")

def field(pattern: str) -> str:
    match = re.search(pattern, values)
    if match is None:
        raise SystemExit(f"values.yaml is missing {pattern}")
    return match.group(1)

add(field(r"(?m)^cnpg:\n(?:[ \t].*\n)*?[ \t]+image:\s+(\S+)"))
add(field(r"(?m)^llmMock:\n(?:[ \t].*\n)*?[ \t]+image:\s+(\S+)"))
add(field(r"(?m)^loadtest:\n(?:.*\n)*?^[ \t]+k6:\n(?:[ \t].*\n)*?[ \t]+image:\s+(\S+)"))
cloudflared_repo = field(
    r"(?m)^cloudflared:\n(?:.*\n)*?^[ \t]+image:\n[ \t]+repository:\s+(\S+)"
)
cloudflared_tag = field(
    r"(?m)^cloudflared:\n(?:.*\n)*?^[ \t]+image:\n(?:[ \t].*\n)*?[ \t]+tag:\s+\"?([^\"\s]+)\"?"
)
add(f"{cloudflared_repo}:{cloudflared_tag}")
wait_repo = field(
    r"(?m)^databaseWait:\n(?:.*\n)*?^[ \t]+image:\n[ \t]+repository:\s+(\S+)"
)
wait_tag = field(
    r"(?m)^databaseWait:\n(?:.*\n)*?^[ \t]+image:\n(?:[ \t].*\n)*?[ \t]+tag:\s+\"?([^\"\s]+)\"?"
)
add(f"{wait_repo}:{wait_tag}")
for image in found:
    print(image)
PY
)

if [[ "${1:-}" == "--print" ]]; then
  printf '%s\n' "${images[@]}"
  exit 0
fi

mkdir -p "${outdir}"
status=0
index=0
for image in "${images[@]}"; do
  index=$((index + 1))
  report="${outdir}/$(printf '%02d' "${index}").json"
  rm -f "${report}"
  # The k6 file lists fixable HIGH findings in grafana/k6:2.3.0. It is not
  # an allowlist for nginx or the other images.
  image_ignore="${ignore}"
  case "${image}" in
    grafana/k6:*|grafana/k6@*)
      image_ignore="${k6_ignore}"
      ;;
  esac
  if ! "${trivy_bin}" image --scanners vuln --exit-code 1 --severity HIGH,CRITICAL \
    --ignorefile "${image_ignore}" \
    --format json -o "${report}" \
    "${image}"; then
    echo "trivy failed for ${image}" >&2
    status=1
  fi
done

if ! python3 - "${outdir}" "${#images[@]}" << 'PY'
import json
import sys
from pathlib import Path

outdir = Path(sys.argv[1])
expected = int(sys.argv[2])
reports = sorted(outdir.glob("*.json"))
if len(reports) != expected:
    raise SystemExit(
        f"scan report count {len(reports)} != expected image count {expected}"
    )
scanned = 0
for report in reports:
    if not report.is_file() or report.stat().st_size == 0:
        raise SystemExit(f"scan report is missing or empty: {report}")
    document = json.loads(report.read_text(encoding="utf-8"))
    if isinstance(document, dict) and document.get("ArtifactName"):
        scanned += 1
    else:
        raise SystemExit(f"scan report has no image: {report}")
if scanned != expected:
    raise SystemExit(f"scanned {scanned} images, expected {expected}")
print(f"scanned {scanned} images")
PY
then
  status=1
fi

exit "${status}"
