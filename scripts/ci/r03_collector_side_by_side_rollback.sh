#!/usr/bin/env bash
# SEC001-R03: isolated 0.123.0 -> patched 0.165.0 -> 0.123.0 rollback.
# This qualifies only local filelog checkpoint compatibility, not CL-2/CL-3,
# authenticated central ACK, production upgrade or native Collector promotion.
set -euo pipefail
: "${RUNNER_TEMP:?An isolated CI-owned temporary root is required}"
: "${R03_COLLECTOR_IMAGE:?Use the locally built patched 0.165 candidate}"
legacy='otel/opentelemetry-collector-contrib:0.123.0@sha256:e39311df1f3d941923c00da79ac7ba6269124a870ee87e3c3ad24d60f8aee4d2'
docker pull "$legacy"
docker run --rm --entrypoint /otelcol-contrib "$legacy" --version | grep -F '0.123.0'
docker run --rm --entrypoint /otelcol-contrib "$R03_COLLECTOR_IMAGE" --version | grep -F '0.165.0'
work="$(mktemp -d "$RUNNER_TEMP/r03-collector-rollback.XXXXXX")"
container="r03-rollback-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  sudo rm -rf -- "$work"
}
trap cleanup EXIT
mkdir -p "$work/state"
chmod 0755 "$work"
chmod 0775 "$work/state"
sudo chown 10001:10001 "$work/state"
cat > "$work/collector.yaml" <<'YAML'
extensions:
  file_storage:
    directory: /fixture/state
receivers:
  filelog:
    include: [/fixture/events.log]
    start_at: beginning
    storage: file_storage
processors:
  batch:
    timeout: 200ms
exporters:
  debug:
    verbosity: detailed
service:
  extensions: [file_storage]
  pipelines:
    logs:
      receivers: [filelog]
      processors: [batch]
      exporters: [debug]
YAML
chmod 0644 "$work/collector.yaml"
start_phase() {
  local image="$1"
  docker run -d --name "$container" --network none \
    --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges \
    -v "$work:/fixture:rw" \
    --entrypoint /otelcol-contrib "$image" \
    --config=/fixture/collector.yaml >/dev/null
}
await_marker() {
  local marker="$1"
  for i in $(seq 1 40); do
    if docker logs "$container" 2>&1 | grep -Fq "$marker"; then return 0; fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "$container")" != true ]]; then
      docker logs "$container" >&2
      return 1
    fi
    sleep 1
  done
  docker logs "$container" >&2
  return 1
}
stop_phase() {
  local logfile="$1"
  docker stop "$container" >/dev/null
  docker logs "$container" > "$work/$logfile" 2>&1
  docker rm "$container" >/dev/null
}
printf '%s\n' SEC001_R03_LEGACY_0_123 > "$work/events.log"
chmod 0644 "$work/events.log"
start_phase "$legacy"
await_marker SEC001_R03_LEGACY_0_123
stop_phase "phase-legacy.log"
printf '%s\n' SEC001_R03_NEW_0_165 >> "$work/events.log"
start_phase "$R03_COLLECTOR_IMAGE"
await_marker SEC001_R03_NEW_0_165
if docker logs "$container" 2>&1 | grep -Fq SEC001_R03_LEGACY_0_123; then
  echo "FAIL: patched 0.165 replayed an already checkpointed legacy log" >&2
  exit 1
fi
stop_phase "phase-patched.log"
printf '%s\n' SEC001_R03_ROLLBACK_0_123 >> "$work/events.log"
start_phase "$legacy"
await_marker SEC001_R03_ROLLBACK_0_123
if docker logs "$container" 2>&1 | grep -Eq 'SEC001_R03_(LEGACY_0_123|NEW_0_165)'; then
  echo "FAIL: rollback 0.123 replayed a previously checkpointed log" >&2
  exit 1
fi
stop_phase "phase-rollback.log"
echo "PASS: isolated pinned 0.123 -> patched 0.165 -> 0.123 filelog checkpoint and no-duplicate rollback"
echo "REVIEW_ONLY: central receipt durability, identity, HA, TLS rotation and production rollback are not certified"
