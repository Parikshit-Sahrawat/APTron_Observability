#!/usr/bin/env bash
# SEC001-R03B: disposable mTLS + filelog checkpoint/replay qualification.
# No remote endpoints or production credentials; no automatic migration approval.
set -euo pipefail
: "${R03_COLLECTOR_IMAGE:?Pass the exact locally built isolated image tag}"
: "${RUNNER_TEMP:?Requires an owned CI temporary directory}"
work="$(mktemp -d "$RUNNER_TEMP/r03-collector-private.XXXXXX")"
network="r03-internal-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
container="r03-collector-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
  # The container creates state files as UID 10001. Remove only the exact
  # mktemp-owned CI directory after destroying the isolated container/network.
  if [[ "$work" == "$RUNNER_TEMP"/r03-collector-private.* ]]; then
    sudo rm -rf -- "$work"
  fi
}
trap cleanup EXIT
mkdir -p "$work/server" "$work/client" "$work/fixture/state"
chmod 0755 "$work" "$work/fixture" "$work/server"
# Set POSIX mode before ownership transfer: the runner user cannot chmod
# a directory after chown to container UID 10001 on GitHub-hosted Linux.
chmod 0755 "$work/fixture/state"
sudo chown 10001:10001 "$work/fixture/state"
printf '%s\n' SEC001_R03_CHECKPOINT_BEFORE > "$work/fixture/events.log"
chmod 0644 "$work/fixture/events.log"

openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days 1 \
  -keyout "$work/ca.key" -out "$work/ca.crt" -subj "/CN=sec001-r03-test-CA" >/dev/null 2>&1
openssl req -nodes -newkey rsa:2048 -sha256 \
  -keyout "$work/server/server.key" -out "$work/server.csr" \
  -subj "/CN=localhost" >/dev/null 2>&1
printf 'subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n' > "$work/server.ext"
openssl x509 -req -sha256 -days 1 -in "$work/server.csr" \
  -CA "$work/ca.crt" -CAkey "$work/ca.key" -CAcreateserial \
  -out "$work/server/server.crt" -extfile "$work/server.ext" >/dev/null 2>&1
openssl req -nodes -newkey rsa:2048 -sha256 \
  -keyout "$work/client/client.key" -out "$work/client.csr" \
  -subj "/CN=sec001-r03-client" >/dev/null 2>&1
printf 'extendedKeyUsage=clientAuth\n' > "$work/client.ext"
openssl x509 -req -sha256 -days 1 -in "$work/client.csr" \
  -CA "$work/ca.crt" -CAkey "$work/ca.key" -CAcreateserial \
  -out "$work/client/client.crt" -extfile "$work/client.ext" >/dev/null 2>&1
cp "$work/ca.crt" "$work/server/ca.crt"
# Lock key mode while the runner still owns it, then transfer ownership
# to the unprivileged Collector UID. No key bytes are uploaded to CI artifacts.
chmod 0400 "$work/server/server.key"
sudo chown 10001:10001 "$work/server/server.key"
chmod 0644 "$work/server/server.crt" "$work/server/ca.crt"
chmod 0600 "$work/ca.key" "$work/client/client.key"
cat > "$work/fixture/config.yaml" <<'YAML'
extensions:
  file_storage:
    directory: /fixture/state
receivers:
  filelog:
    include: [/fixture/events.log]
    start_at: beginning
    storage: file_storage
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /secrets/server.crt
          key_file: /secrets/server.key
          client_ca_file: /secrets/ca.crt
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
      receivers: [filelog, otlp]
      processors: [batch]
      exporters: [debug]
YAML
cat > "$work/client/otlp.json" <<'JSON'
{"resourceLogs":[{"scopeLogs":[{"logRecords":[{"body":{"stringValue":"SEC001_R03_MTLS_DELIVERED"}}]}]}]}
JSON
docker network create --internal "$network" >/dev/null
start_collector() {
  # Internal Docker network + unprivileged Collector: no host port published.
  docker run -d --name "$container" --network "$network" \
    --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges \
    -v "$work/fixture:/fixture:rw" -v "$work/server:/secrets:ro" \
    --entrypoint /otelcol-contrib "$R03_COLLECTOR_IMAGE" \
    --config=/fixture/config.yaml >/dev/null
}
post_otlp() {
  local mode="${1:-with-cert}"
  # Disposable unprivileged Python client shares ONLY the network namespace.
  # The TLS CA and private client key stay on read-only bind mounts.
  docker run --rm --network "container:$container" \
    --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
    -v "$work/client:/client:ro" -v "$work/ca.crt:/ca.crt:ro" \
    --entrypoint python \
    python:3.12.16-alpine3.23@sha256:fe32c943235f1c5748d1106dbdfa25d206355c1be1ae1e167444a7ff9dfa9422 \
    -c '
import ssl,sys,urllib.request
ctx=ssl.create_default_context(cafile="/ca.crt")
if sys.argv[1] == "with-cert":
    ctx.load_cert_chain("/client/client.crt","/client/client.key")
body=open("/client/otlp.json","rb").read()
req=urllib.request.Request("https://localhost:4318/v1/logs", data=body, headers={"Content-Type":"application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
        assert response.status in (200,202), response.status
except Exception as error:
    print("OTLP TLS client error:",type(error).__name__,file=sys.stderr)
    sys.exit(1)
' "$mode"
}
await_log() {
  local marker="$1" found=false
  for _ in $(seq 1 45); do
    if docker logs "$container" 2>&1 | grep -Fq "$marker"; then found=true; break; fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "$container")" != true ]]; then break; fi
    sleep 1
  done
  [[ "$found" = true ]] || { docker logs "$container" | tail -50; return 1; }
}
start_collector
ready=false
for _ in $(seq 1 40); do
  if post_otlp; then ready=true; break; fi
  sleep 1
done
[[ "$ready" = true ]] || { docker logs "$container" | tail -50; exit 1; }
# Missing client identity must be rejected, not forwarded to the pipeline.
if post_otlp without-cert; then
  echo "FAIL: collector accepted OTLP without client certificate" >&2; exit 1
fi
await_log SEC001_R03_MTLS_DELIVERED
await_log SEC001_R03_CHECKPOINT_BEFORE
docker stop "$container" >/dev/null
docker rm "$container" >/dev/null
printf '%s\n' SEC001_R03_CHECKPOINT_AFTER >> "$work/fixture/events.log"
start_collector
await_log SEC001_R03_CHECKPOINT_AFTER
if docker logs "$container" 2>&1 | grep -Fq SEC001_R03_CHECKPOINT_BEFORE; then
  echo "FAIL: filelog previously checkpointed event replayed after restart" >&2; exit 1
fi
post_otlp
await_log SEC001_R03_MTLS_DELIVERED
echo 'SEC001-R03 mTLS admission rejection, authenticated OTLP delivery and local file checkpoint restart PASS'
echo 'REVIEW_ONLY: no TLS credential governance, tenant auth, remote durable ACK, multi-host spool or native Collector migration certified'
