#!/usr/bin/env bash
# SEC001-R03: isolated 0.123 -> patched 0.165 -> 0.163.2 JSON-bridge
# -> 0.123 rollback experiment. OpenTelemetry v0.164+ writes protobuf-only
# checkpoints, so direct downgrade to 0.123 is NOT safe. The 0.163.2
# bridge MUST explicitly disable its beta protobufCheckpointEncoding gate
# (enabled by default since 0.156) to write JSON for legacy 0.123.
# Bridge is evaluation-only, never a production/release promotion.
# Never claim central ACK, physical HA, prod upgrade or legal approval.
set -euo pipefail
: "${RUNNER_TEMP:?An isolated CI-owned temporary root is required}"
: "${R03_COLLECTOR_IMAGE:?Use the locally built patched 0.165 candidate}"
legacy='otel/opentelemetry-collector-contrib:0.123.0@sha256:e39311df1f3d941923c00da79ac7ba6269124a870ee87e3c3ad24d60f8aee4d2'
# This pinned, previously evaluated 0.163.2 image is a temporary local
# JSON-checkpoint bridge, not an accepted production/release binary.
bridge='otel/opentelemetry-collector-contrib:0.163.2@sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849'
docker pull "$legacy"
docker pull "$bridge"
docker run --rm --entrypoint /otelcol-contrib "$legacy" --version | grep -F '0.123.0'
docker run --rm --entrypoint /otelcol-contrib "$bridge" --version | grep -F '0.163.2'
docker run --rm --entrypoint /otelcol-contrib "$R03_COLLECTOR_IMAGE" --version | grep -F '0.165.0'
# Do not silently trust floating aliases: exact RepoDigest must be present.
BRIDGE_IMAGE="$bridge" python - <<'PY'
import json,os,subprocess
image=os.environ["BRIDGE_IMAGE"]
digests=json.loads(subprocess.check_output(["docker","image","inspect",image],text=True))[0]["RepoDigests"]
assert any(d.endswith("@"+image.split("@")[1]) for d in digests), digests
print("Checkpoint bridge immutable upstream RepoDigest verified")
PY
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
  shift
  docker run -d --name "$container" --network none \
    --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges \
    -v "$work:/fixture:rw" \
    --entrypoint /otelcol-contrib "$image" \
    --config=/fixture/collector.yaml "$@" >/dev/null
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
# 0.163.2 reads protobuf checkpoints from v0.165, but the
# filelog.protobufCheckpointEncoding gate became BETA/ON by default in
# v0.156.0. EXPLICITLY DISABLE IT on the intermediate bridge only so a
# newly processed event saves the cursor checkpoint in legacy JSON.
# Do NOT disable it on v0.165 (stable/immutable), delete state or reset offsets.
# Source: https://pkg.go.dev/github.com/open-telemetry/opentelemetry-collector-contrib/receiver/filelogreceiver
# Source: https://github.com/open-telemetry/opentelemetry-collector/blob/main/featuregate/README.md
printf '%s\n' SEC001_R03_BRIDGE_0_163 >> "$work/events.log"
start_phase "$bridge" '--feature-gates=-filelog.protobufCheckpointEncoding'
await_marker SEC001_R03_BRIDGE_0_163
if docker logs "$container" 2>&1 | grep -Eq 'SEC001_R03_(LEGACY_0_123|NEW_0_165)'; then
  echo "FAIL: bridge replayed an already checkpointed log" >&2
  exit 1
fi
# Permit two checkpoint polling cycles before a clean stop and JSON handoff.
sleep 1
stop_phase "phase-bridge.log"
printf '%s\n' SEC001_R03_ROLLBACK_0_123 >> "$work/events.log"
start_phase "$legacy"
await_marker SEC001_R03_ROLLBACK_0_123
if docker logs "$container" 2>&1 | grep -Eq 'SEC001_R03_(LEGACY_0_123|NEW_0_165|BRIDGE_0_163)'; then
  echo "FAIL: rollback 0.123 replayed a previously checkpointed log" >&2
  exit 1
fi
stop_phase "phase-rollback.log"
echo "PASS: isolated 0.123 -> patched 0.165 -> 0.163.2 JSON bridge (protobuf encoding explicitly disabled) -> 0.123 with retained filelog offsets"
echo "REVIEW_ONLY: 0.163.2 bridge is NOT a qualified final image; central receipt durability, tenant identity, HA, TLS rotation and production rollback are NOT certified"
