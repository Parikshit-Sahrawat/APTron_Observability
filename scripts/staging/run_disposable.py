"""Deploy scanned images on this CI runner only, validate, and remove the stack."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
from urllib.request import urlopen
import uuid
from loopback_proxy import start as start_loopback_proxy


def isolation(config, images):
    services = config["services"]
    if set(services) != {"postgres", "migration", "api", "worker", "frontend"}:
        raise ValueError("Unexpected staging services")
    if any(not network.get("internal") or network.get("external") for network in config["networks"].values()):
        raise ValueError("Staging network must be internal and locally owned")
    if any(volume.get("external") for volume in config.get("volumes", {}).values()):
        raise ValueError("External staging volume forbidden")
    for name, service in services.items():
        if service["image"] != images[name] or not re.fullmatch(r"sha256:[0-9a-f]{64}", service["image"]):
            raise ValueError("Staging must use the exact scanned local image ID")
        for key in ("build", "privileged", "devices", "cap_add", "network_mode", "pid", "ipc", "external_links", "volumes_from"):
            if service.get(key):
                raise ValueError("Unsafe staging configuration: " + key)
        if not service.get("networks") or set(service["networks"]) != {"staging"}:
            raise ValueError("Unexpected staging network attachment")
        if not set(service.get("environment", {})) <= {
            "ENVIRONMENT", "APTRON_DISPOSABLE_STAGING", "SEED_DEMO_DATA", "DATABASE_URL",
            "CORS_ORIGINS", "AWS_EC2_METADATA_DISABLED", "OPSCONTROL_WORKER_HEARTBEAT",
            "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}:
            raise ValueError("Unapproved staging environment variable")
        for port in service.get("ports", []):
            if port.get("host_ip") != "127.0.0.1" or name not in {"api", "frontend"}:
                raise ValueError("Only API/frontend loopback ports permitted")
        for volume in service.get("volumes", []):
            if name != "postgres" or volume.get("type") != "volume" or volume.get("source") != "pgdata":
                raise ValueError("Host bind mounts or unowned volumes forbidden")


def main(decision, evidence):
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise ValueError("Disposable staging requires a GitHub-hosted runner")
    if os.environ.get("DOCKER_HOST", "") not in {"", "unix:///var/run/docker.sock"} or os.environ.get("DOCKER_CONTEXT", "default") != "default":
        raise ValueError("Remote Docker targets are outside disposable staging scope")
    evidence.mkdir(parents=True, exist_ok=True)
    report = json.loads(decision.read_text())
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if (report.get("status") != "STAGING_ELIGIBLE_WITH_EXCEPTIONS" or
            report.get("source_sha") != sha or report.get("profile") != "deployment" or
            report.get("scope") != "disposable-ci-staging" or report.get("production_eligible") is not False):
        raise ValueError("Exact-source staging exception decision required")
    # Re-evaluate the decision immediately before deployment to reject changed
    # evidence, policy edits or an expired exception; do not trust a JSON flag.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
    from staging_image_gate import evaluate
    root = Path(__file__).resolve().parents[2]
    policy = json.loads((root / ".ci/staging-exceptions.json").read_text())
    current = evaluate(decision.parent, sha, policy)
    if current != report:
        raise ValueError("Staging decision no longer matches current evidence")
    by_role = {r["role"]: r["image_config_id"] for r in report["images"]}
    images = {"postgres": by_role["postgres"], "frontend": by_role["frontend"],
              **{name: by_role["uat-backend"] for name in ("api", "worker", "migration")}}
    project = "aptron-staging-" + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    env = {"ENVIRONMENT": "test", "APTRON_DISPOSABLE_STAGING": "1", "SEED_DEMO_DATA": "false",
           "DATABASE_URL": "postgresql+psycopg://staging:" + password + "@postgres:5432/aptron_staging",
           "CORS_ORIGINS": "http://127.0.0.1:5173", "AWS_EC2_METADATA_DISABLED": "true"}
    secure = {"security_opt": ["no-new-privileges:true"], "networks": ["staging"]}
    app = {**secure, "image": by_role["uat-backend"], "environment": env,
           "read_only": True, "tmpfs": ["/tmp"], "cap_drop": ["ALL"]}
    config = {"services": {
        "postgres": {**secure, "image": images["postgres"],
                     "environment": {"POSTGRES_USER": "staging", "POSTGRES_PASSWORD": password, "POSTGRES_DB": "aptron_staging"},
                     "volumes": ["pgdata:/var/lib/postgresql/data"]},
        "migration": {**app, "command": ["python", "-m", "alembic", "upgrade", "head"]},
        "api": {**app},
        "worker": {**app, "command": ["python", "-m", "scripts.run_collector_worker"],
                   "environment": {**env, "OPSCONTROL_WORKER_HEARTBEAT": "/tmp/staging-worker-heartbeat"}},
        "frontend": {**secure, "image": images["frontend"], "read_only": True,
                     "tmpfs": ["/tmp", "/var/run", "/var/cache/nginx"]}},
        "volumes": {"pgdata": {}}, "networks": {"staging": {"internal": True}}}
    result = {"schema": 1, "source_sha": sha, "scope": "disposable-ci-staging", "project": project,
              "status": "STAGING_VALIDATION_FAILED", "images": images, "checks": [],
              "production_eligible": False, "physical_ha_certified": False, "legal_approved": False,
              "production_reassessment_required": True, "cleanup_completed": False}
    with tempfile.TemporaryDirectory(prefix="aptron-staging-private-") as temp:
        compose_file = Path(temp) / "compose.json"
        compose_file.write_text(json.dumps(config))
        compose_file.chmod(0o600)
        compose = ["docker", "compose", "--project-name", project, "--file", str(compose_file)]
        proxies = []

        def run(*args):
            p = subprocess.run(args, text=True, capture_output=True, timeout=180)
            if p.returncode:
                diagnostics = (p.stdout + p.stderr).replace(password, "[REDACTED]")[-4000:]
                raise RuntimeError("Staging command failed: " + diagnostics)
            return p.stdout

        def ready(url):
            for _ in range(60):
                try:
                    with urlopen(url, timeout=2) as response:
                        if response.status == 200:
                            return
                except OSError:
                    pass
                time.sleep(1)
            raise RuntimeError("Staging endpoint readiness failed: " + url)

        try:
            isolation(json.loads(run(*compose, "config", "--format", "json")), images)
            if run("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project).strip():
                raise ValueError("Refusing an existing Docker project")
            result["checks"].append("rendered-isolation")
            run(*compose, "up", "-d", "--no-build", "--pull", "never", "postgres")
            for attempt in range(60):
                try:
                    assert run(*compose, "exec", "-T", "postgres", "psql", "-U", "staging", "-d", "aptron_staging", "-Atqc", "SELECT 1").strip() == "1"
                    break
                except RuntimeError:
                    if attempt == 59:
                        raise
                    time.sleep(1)
            run(*compose, "run", "--rm", "--no-deps", "--pull", "never", "migration")
            result["checks"].append("postgres-migration")
            run(*compose, "up", "-d", "--no-build", "--pull", "never", "api", "worker", "frontend")
            for attempt in range(30):
                try:
                    run(*compose, "exec", "-T", "api", "python", "-c",
                        "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200")
                    break
                except RuntimeError:
                    if attempt == 29:
                        raise
                    time.sleep(1)
            result["checks"].append("api-container-health")
            # Internal-network port publication is not reachable on this runner.
            # Verify live container ownership and image/network identity before
            # binding runner-only forwarders to the actual private addresses.
            ids = run(*compose, "ps", "-q").split()
            inspected = json.loads(run("docker", "inspect", *ids))
            if len(inspected) != 4:
                raise ValueError("Expected four running staging services")
            targets = {}
            for container in inspected:
                name = container["Config"]["Labels"]["com.docker.compose.service"]
                if container["Image"] != images[name] or container["HostConfig"]["Privileged"]:
                    raise ValueError("Running image or privilege mismatch")
                if any(container["NetworkSettings"]["Ports"].values()):
                    raise ValueError("Unexpected Docker-published port on private staging network")
                for network_name, attachment in container["NetworkSettings"]["Networks"].items():
                    network = json.loads(run("docker", "network", "inspect", network_name))[0]
                    if not network["Internal"] or network["Labels"].get("com.docker.compose.project") != project:
                        raise ValueError("Running network is not isolated staging")
                    if name in {"api", "frontend"}:
                        subnet = next(c["Subnet"] for c in network["IPAM"]["Config"] if ":" not in c["Subnet"])
                        targets[name] = (attachment["IPAddress"], subnet)
            for name, listen_port, target_port in (("api", 8000, 8000), ("frontend", 5173, 80)):
                address, subnet = targets[name]
                proxies.append(start_loopback_proxy(address, subnet, listen_port, target_port))
            result["checks"].append("verified-runner-loopback-forwarding")
            ready("http://127.0.0.1:8000/health")
            ready("http://127.0.0.1:5173")
            for module in ("auth_tenant_probe", "deep_tenant_security_probe", "critical_event_schema_probe"):
                output = run(*compose, "exec", "-T", "api", "python", "-m", "scripts." + module)
                (evidence / (module + ".txt")).write_text(output.replace(password, "[REDACTED]"))
                result["checks"].append(module)
            # Inspect what Docker actually started, not just the Compose input.
            ids = run(*compose, "ps", "-q").split()
            inspected = json.loads(run("docker", "inspect", *ids))
            if len(inspected) != 4:
                raise ValueError("Expected four running staging services")
            for container in inspected:
                name = container["Config"]["Labels"]["com.docker.compose.service"]
                if container["Image"] != images[name] or container["HostConfig"]["Privileged"]:
                    raise ValueError("Running image or privilege mismatch")
                for ports in container["NetworkSettings"]["Ports"].values():
                    if ports and any(port["HostIp"] != "127.0.0.1" for port in ports):
                        raise ValueError("Unexpected public port")
                for network_name in container["NetworkSettings"]["Networks"]:
                    network = json.loads(run("docker", "network", "inspect", network_name))[0]
                    if not network["Internal"] or network["Labels"].get("com.docker.compose.project") != project:
                        raise ValueError("Running network is not isolated staging")
            result["checks"].append("running-image-and-network-isolation")
            browser = run("node", str(root / "scripts/staging/browser.mjs"), str(evidence.resolve()))
            (evidence / "browser.json").write_text(browser)
            result["checks"].append("authenticated-browser")
            run(*compose, "restart", "api", "worker")
            ready("http://127.0.0.1:8000/health")
            run(*compose, "exec", "-T", "api", "python", "-c",
                "from scripts.auth_tenant_probe import login,expect; token=login('test-north'); expect(200,'GET','/api/v1/organizations',token)")
            for attempt in range(30):
                try:
                    run(*compose, "exec", "-T", "worker", "python", "-c",
                        "import pathlib,time; p=pathlib.Path('/tmp/staging-worker-heartbeat'); "
                        "assert p.is_file() and time.time()-float(p.read_text())<30")
                    break
                except RuntimeError:
                    if attempt == 29:
                        raise
                    time.sleep(1)
            result["checks"].append("api-worker-restart-and-persisted-auth")
            result["status"] = "DISPOSABLE_STAGING_VALIDATED_WITH_EXCEPTIONS"
        except Exception as error:
            result["error"] = str(error).replace(password, "[REDACTED]")
            for service in ("api", "worker", "postgres", "frontend"):
                logs = subprocess.run([*compose, "logs", "--no-color", "--tail", "100", service],
                                      text=True, capture_output=True, timeout=30)
                (evidence / (service + "-startup.log")).write_text(
                    (logs.stdout + logs.stderr).replace(password, "[REDACTED]"))
            raise
        finally:
            for proxy in proxies:
                proxy.shutdown()
                proxy.server_close()
            run(*compose, "down", "--volumes", "--remove-orphans")
            result["cleanup_completed"] = not run("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project).strip()
            (evidence / "staging-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    main(args.decision, args.evidence)
