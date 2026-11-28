"""SH-02 actual Compose candidate acceptance, disposable hosted runner only.

No user-supplied Docker target, existing project, volume or data directory.
Uses exact-source scanned local image IDs; never publishes images or receipts.
"""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPSHandler, ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/ci"))

ROLES = {
    "engine": "backend-runtime",
    "migration": "backend-migration",
    "gateway": "production-frontend",
    "postgres": "postgres",
}


class PreflightError(ValueError):
    def __init__(self, stage, reason, *, role=None, uncovered_matches=None):
        super().__init__(reason)
        self.stage = stage
        self.role = role
        self.uncovered_matches = uncovered_matches


def preflight_diagnostic(error):
    detail = {"error_type": type(error).__name__}
    if isinstance(error, PreflightError):
        detail.update(preflight_stage=error.stage, reason=str(error))
        if error.role is not None:
            detail["image_role"] = error.role
        if error.uncovered_matches is not None:
            detail["uncovered_severe_matches"] = error.uncovered_matches
    return detail


def runner_guard(env):
    if (
        env.get("GITHUB_ACTIONS") != "true"
        or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise PreflightError(
            "runner", "SH-02 requires a disposable GitHub-hosted runner"
        )
    if (
        env.get("DOCKER_HOST", "") not in {"", "unix:///var/run/docker.sock"}
        or env.get("DOCKER_CONTEXT", "default") != "default"
    ):
        raise PreflightError("runner", "Remote Docker targets forbidden")


def image_decision(directory, source):
    from image_coverage import contract, verify
    from security_manifest import verify_evidence
    from staging_image_gate import UncoveredSevereFindings, assess

    try:
        policy = json.loads((ROOT / ".ci/staging-exceptions.json").read_text())
        rows = {r["role"]: r for r in contract()}
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise PreflightError(
            "policy-inputs", "Could not load the staging policy or image role contract"
        ) from error

    result = {}
    for role in ROLES.values():
        path = directory / ("image-evidence-" + role)
        try:
            binding = verify(path, rows[role], source)
            verify_evidence(path)
            scan = json.loads((path / "grype.json").read_text())
        except (ValueError, KeyError, TypeError, OSError) as error:
            raise PreflightError(
                "image-evidence",
                "Check source and image binding, evidence checksums, and scanner database freshness",
                role=role,
            ) from error

        try:
            decision = assess(policy, role, scan, datetime.now(timezone.utc))
        except UncoveredSevereFindings as error:
            raise PreflightError(
                "staging-exceptions",
                "New or changed severe finding requires owner review",
                role=role,
                uncovered_matches=error.match_count,
            ) from error
        except (ValueError, KeyError, TypeError) as error:
            raise PreflightError(
                "staging-exceptions",
                "Check the staging policy and scope, approval, and expiry of exceptions",
                role=role,
            ) from error
        result[role] = {**decision, "image_id": binding["image_id"]}
    # Reuse accountable per-role exceptions without editing staging_roles,
    # exception fingerprints/expiry, or the independent eight-image gate.
    return result


def forwarder(address, subnet):
    network = ipaddress.ip_network(subnet)
    target = ipaddress.ip_address(address)
    if (
        not isinstance(target, ipaddress.IPv4Address)
        or target not in network
        or not any(
            network.subnet_of(ipaddress.ip_network(n))
            for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        )
    ):
        raise ValueError("HTTPS target must be in owned private IPv4 subnet")

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                with socket.create_connection(
                    (str(target), 8443), timeout=5
                ) as upstream:
                    for sock in (self.request, upstream):
                        sock.settimeout(20)
                    while True:
                        ready, _, _ = select.select(
                            [self.request, upstream], [], [], 20
                        )
                        if not ready:
                            return
                        for source in ready:
                            data = source.recv(65536)
                            if not data:
                                return
                            (
                                upstream if source is self.request else self.request
                            ).sendall(data)
            except OSError:
                return

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        block_on_close = False

    # Not started until live Docker labels, image IDs, networks and IP are checked.
    return Server(("127.0.0.1", 0), Handler)


def isolated_config(config, images, private):
    from validate_single_host import validate

    validate(
        config,
        local_images={name: images[name] for name in ("gateway", "engine", "postgres")},
    )
    # Only these two isolation changes from the actual deployment candidate.
    config["services"]["gateway"].pop("ports")
    config["networks"]["ingress"]["internal"] = True
    if set(config["services"]) != {"postgres", "engine", "gateway"}:
        raise ValueError("Unexpected service")
    expected_networks = {
        "gateway": {"ingress"},
        "engine": {"ingress", "database"},
        "postgres": {"database"},
    }
    for name, service in config["services"].items():
        if service.get("ports") or service.get("build") or service.get("privileged"):
            raise ValueError("Published ports/build/privilege forbidden in fixture")
        if set(service.get("networks", {})) != expected_networks[name]:
            raise ValueError("Unexpected service network attachment")
        allowed_caps = (
            {"CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"}
            if name == "gateway"
            else set()
        )
        if not set(service.get("cap_add", [])) <= allowed_caps:
            raise ValueError("Unexpected added Linux capability")
        if name == "engine" and service.get("user") != "10001:10001":
            raise ValueError("Nonroot engine identity required")
        for mount in service.get("volumes", []):
            if mount["type"] != "bind" or not Path(
                mount["source"]
            ).resolve().is_relative_to(private.resolve()):
                raise ValueError("Only fixture-owned bind mounts allowed")
    if any(
        not n.get("internal") or n.get("external") for n in config["networks"].values()
    ):
        raise ValueError("Only internal fixture networks allowed")
    for secret in config["secrets"].values():
        if not Path(secret["file"]).resolve().is_relative_to(private.resolve()):
            raise ValueError("Only fixture-owned secret files allowed")
    return config


def main(image_evidence, evidence):
    runner_guard(os.environ)
    if evidence.resolve().is_relative_to(
        ROOT
    ) or image_evidence.resolve().is_relative_to(ROOT):
        raise PreflightError(
            "workspace", "Evidence must be outside clean source checkout"
        )
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip():
        raise PreflightError("workspace", "Clean committed source required")
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    decisions = image_decision(image_evidence, source)
    images = {name: decisions[role]["image_id"] for name, role in ROLES.items()}
    evidence.mkdir(parents=True, exist_ok=True)
    private = Path(tempfile.mkdtemp(prefix="aptron-sh02-private-"))
    project = "aptron-sh02-" + uuid.uuid4().hex[:12]
    owner_password, app_password = secrets.token_hex(24), secrets.token_hex(24)
    report = {
        "source_sha": source,
        "project": project,
        "status": "FAILED",
        "checks": [],
        "commands": [],
        "images": images,
        "decisions": decisions,
        "cleanup_completed": False,
        "production_eligible": False,
        "receipts_enabled": False,
        "reconciliation_enabled": False,
        "physical_ha_certified": False,
        "license_approved": False,
    }
    proxy = None
    proxy_started = False
    owned = False
    compose = []
    env = dict(os.environ)

    # Only explicit synthetic destination/DB configuration enters the containers.
    def redact(value):
        for secret in (
            owner_password,
            app_password,
            "testing-only-StrongPassword-123!",
        ):
            value = value.replace(secret, "[REDACTED]")
        return value

    def run(*args, input=None, extra_env=None, label="command", timeout=240):
        p = subprocess.run(
            args,
            cwd=ROOT,
            env={**env, **(extra_env or {})},
            input=input,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        report["commands"].append({"label": label, "exit_code": p.returncode})
        if p.returncode:
            raise RuntimeError(label + ": " + redact(p.stdout + p.stderr)[-3000:])
        return p.stdout

    def wait(check, label, seconds=150):
        until = time.monotonic() + seconds
        while True:
            try:
                if check():
                    report["checks"].append(label)
                    return
            except (RuntimeError, URLError):
                pass
            if time.monotonic() >= until:
                raise RuntimeError("Timed out: " + label)
            time.sleep(1)

    def inspect_service(name):
        cid = run(*compose, "ps", "-aq", name, label="service-identity").strip()
        if not cid:
            raise RuntimeError("Missing fixture service")
        row = json.loads(run("docker", "inspect", cid, label="inspect-service"))[0]
        if (
            row["Config"]["Labels"].get("com.docker.compose.project") != project
            or row["Image"] != images[name]
        ):
            raise RuntimeError("Live service ownership or scanned image mismatch")
        return row

    def healthy(name):
        row = inspect_service(name)
        return (
            row["State"].get("Health", {}).get("Status") == "healthy"
            and not row["State"]["Restarting"]
        )

    def maintenance(*command, production=False):
        return run(
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--name",
            project + "-maintenance",
            "--label",
            "aptron.sh02.run=" + project,
            "--network",
            project + "_database",
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "--mount",
            "type=bind,src=" + str(private / "fixture") + ",dst=/fixture,readonly",
            "-e",
            "DATABASE_URL",
            "-e",
            "SH02_APP_PASSWORD",
            "-e",
            "APTRON_SH02_FIXTURE=1",
            "-e",
            "ENVIRONMENT=" + ("production" if production else "test"),
            images["migration"],
            *command,
            label="maintenance",
            extra_env={
                "DATABASE_URL": "postgresql+psycopg://aptron_owner:"
                + owner_password
                + "@postgres:5432/aptron",
                "SH02_APP_PASSWORD": app_password,
            },
        )

    try:
        # Pick a Docker-unused private subnet; daemon also rejects collisions.
        networks = [
            json.loads(line)
            for line in run(
                "docker", "network", "ls", "--format", "json", label="network-inventory"
            ).splitlines()
        ]
        used = []
        for n in networks:
            row = json.loads(
                run("docker", "network", "inspect", n["ID"], label="network-subnet")
            )[0]
            used.extend(
                ipaddress.ip_network(c["Subnet"])
                for c in row.get("IPAM", {}).get("Config", [])
                if c.get("Subnet")
            )
        subnet = next(
            ipaddress.ip_network(f"172.30.{i}.0/28")
            for i in range(100, 250)
            if not any(
                ipaddress.ip_network(f"172.30.{i}.0/28").overlaps(n)
                for n in used
                if n.version == 4
            )
        )
        gateway_ip = str(subnet.network_address + 2)
        proxy = forwarder(gateway_ip, str(subnet))
        origin = "https://127.0.0.1:" + str(proxy.server_address[1])
        for name, content in (
            ("owner-password", owner_password),
            (
                "engine.env",
                "DATABASE_URL=postgresql+psycopg://sh02_app:"
                + app_password
                + "@postgres:5432/aptron\nCORS_ORIGINS="
                + origin
                + "\n",
            ),
        ):
            (private / name).write_text(content)
            (private / name).chmod(0o600)
        (private / "pgdata").mkdir()
        (private / "fixture").mkdir(mode=0o755)
        shutil.copyfile(
            ROOT / "deploy/examples/restricted-database-roles.sql",
            private / "fixture/restricted-roles.sql",
        )
        run(
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(private / "tls.key"),
            "-out",
            str(private / "tls.crt"),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1,DNS:localhost",
            label="fixture-certificate",
        )
        env.update(
            {
                "APTRON_PROJECT_NAME": project,
                "APTRON_BACKEND_IMAGE": images["engine"],
                "APTRON_FRONTEND_IMAGE": images["gateway"],
                "APTRON_POSTGRES_IMAGE": images["postgres"],
                "APTRON_PGDATA": str(private / "pgdata"),
                "APTRON_ENGINE_ENV_FILE": str(private / "engine.env"),
                "APTRON_POSTGRES_PASSWORD_FILE": str(private / "owner-password"),
                "APTRON_TLS_CERTIFICATE": str(private / "tls.crt"),
                "APTRON_TLS_KEY": str(private / "tls.key"),
                "APTRON_GATEWAY_CONFIG": str(private / "nginx.conf"),
                "APTRON_GATEWAY_IP": gateway_ip,
                "APTRON_INGRESS_SUBNET": str(subnet),
                "APTRON_BIND_ADDRESS": "127.0.0.1",
                "APTRON_HTTPS_PORT": "8443",
            }
        )
        index = run(
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--name",
            project + "-utility",
            "--label",
            "aptron.sh02.run=" + project,
            "--network",
            "none",
            "--entrypoint",
            "cat",
            images["gateway"],
            "/usr/share/nginx/html/index.html",
            label="exact-image-index",
        )
        (private / "index.html").write_text(index)
        run(
            "node",
            "frontend/scripts/render-production-nginx.mjs",
            str(private / "index.html"),
            str(private / "nginx.conf"),
            "http://engine:8000",
            "deploy/single-host/nginx.conf.template",
            label="exact-build-csp",
        )
        rendered = json.loads(
            run(
                "docker",
                "compose",
                "--env-file",
                os.devnull,
                "-f",
                "deploy/single-host/compose.yaml",
                "config",
                "--format",
                "json",
                label="actual-compose-render",
            )
        )
        config = isolated_config(rendered, images, private)
        config_file = private / "compose.json"
        config_file.write_text(json.dumps(config))
        config_file.chmod(0o600)
        compose = ["docker", "compose", "-p", project, "-f", str(config_file)]
        if run(
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project=" + project,
            label="no-existing-project",
        ).strip():
            raise RuntimeError("Refusing existing project")
        if image_decision(image_evidence, source) != decisions:
            raise RuntimeError("Image decision changed/expired")
        owned = True
        run(
            *compose,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "postgres",
            label="start-postgres",
        )
        wait(lambda: healthy("postgres"), "postgres-ready")
        maintenance("python", "-m", "alembic", "upgrade", "head")
        ids = json.loads(
            maintenance("python", "-m", "scripts.single_host_fixture", "initialize")
        )
        # Owner identity must be rejected by the production role guard.
        maintenance(
            "python",
            "-c",
            "from scripts.run_single_host import main\ntry: main()\nexcept RuntimeError: pass\nelse: raise AssertionError('Owner accepted')",
            production=True,
        )
        run(
            *compose,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "engine",
            "gateway",
            label="start-three-services",
        )
        wait(lambda: healthy("engine") and healthy("gateway"), "engine-gateway-ready")
        for name in ("postgres", "engine", "gateway"):
            row = inspect_service(name)
            if row["HostConfig"]["Privileged"] or any(
                row["NetworkSettings"]["Ports"].values()
            ):
                raise RuntimeError("Live privilege/port isolation failure")
            for network_name, attachment in row["NetworkSettings"]["Networks"].items():
                network = json.loads(
                    run(
                        "docker",
                        "network",
                        "inspect",
                        network_name,
                        label="live-network",
                    )
                )[0]
                if (
                    not network["Internal"]
                    or network["Labels"].get("com.docker.compose.project") != project
                ):
                    raise RuntimeError("Unowned or external network")
                if name == "gateway" and attachment["IPAddress"] != gateway_ip:
                    raise RuntimeError("Gateway IP mismatch")
        if len(run(*compose, "ps", "-q", label="steady-state-count").split()) != 3:
            raise RuntimeError("Exactly three running central containers required")
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        proxy_started = True
        report["checks"].append("three-exact-images-private-networks-restricted-role")
        context = ssl.create_default_context(cafile=str(private / "tls.crt"))
        http = build_opener(ProxyHandler({}), HTTPSHandler(context=context))

        def request(path, *, token=None, tenant=None, body=None, expected=200):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            if tenant:
                headers["X-OpsControl-Customers"] = tenant
            req = Request(
                origin + path,
                headers=headers,
                data=json.dumps(body).encode() if body is not None else None,
            )
            try:
                response = http.open(req, timeout=10)
            except HTTPError as error:
                response = error
            with response:
                if response.status != expected:
                    raise RuntimeError(
                        "HTTP acceptance mismatch: " + str(response.status)
                    )
                return response.headers, response.read()

        headers, _ = request("/health")
        if not headers.get("Strict-Transport-Security"):
            raise RuntimeError("Missing HSTS")
        headers, _ = request("/")
        script_policy = (
            headers["Content-Security-Policy"]
            .split("script-src", 1)[1]
            .split(";", 1)[0]
        )
        if "'unsafe-inline'" in script_policy or "'sha256-" not in script_policy:
            raise RuntimeError("Missing exact-build CSP hashes")
        try:
            with build_opener(
                ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context())
            ).open(origin, timeout=5):
                raise RuntimeError("Untrusted fixture certificate accepted")
        except URLError:
            pass
        with socket.create_connection(proxy.server_address, timeout=5) as sock:
            try:
                with context.wrap_socket(sock, server_hostname="wrong.invalid"):
                    raise RuntimeError("Wrong TLS hostname accepted")
            except ssl.SSLCertVerificationError:
                pass
        request("/api/v1/organizations", expected=401)
        token = json.loads(
            request(
                "/api/v1/auth/login",
                body={
                    "username": "test-north",
                    "password": "testing-only-StrongPassword-123!",
                },
            )[1]
        )["access_token"]
        organizations = json.loads(
            request("/api/v1/organizations", token=token, tenant=ids["a"])[1]
        )
        if {row["id"] for row in organizations} != {ids["a"]}:
            raise RuntimeError("Tenant inventory leak")
        request(
            "/api/v1/monitoring/data-sources/" + ids["sa"], token=token, tenant=ids["a"]
        )
        request(
            "/api/v1/monitoring/data-sources/" + ids["sb"],
            token=token,
            tenant=ids["a"],
            expected=404,
        )
        reader = json.loads(
            request(
                "/api/v1/auth/login",
                body={
                    "username": "test-reader",
                    "password": "testing-only-StrongPassword-123!",
                },
            )[1]
        )["access_token"]
        request(
            "/api/v1/organizations",
            token=reader,
            tenant=ids["a"],
            body={"name": "forbidden"},
            expected=403,
        )
        report["checks"].append("verified-tls-hostname-csp-auth-and-tenant-negatives")
        pubkey = run(
            "openssl",
            "x509",
            "-in",
            str(private / "tls.crt"),
            "-pubkey",
            "-noout",
            label="fixture-public-key",
        )
        der = subprocess.run(
            ["openssl", "pkey", "-pubin", "-outform", "DER"],
            input=pubkey.encode(),
            capture_output=True,
            check=True,
        ).stdout
        browser = run(
            "node",
            "scripts/staging/sh02_browser.mjs",
            str(evidence.resolve()),
            label="real-browser",
            extra_env={
                "SH02_ORIGIN": origin,
                "SH02_SPKI": base64.b64encode(hashlib.sha256(der).digest()).decode(),
                "NODE_EXTRA_CA_CERTS": str(private / "tls.crt"),
            },
        )
        (evidence / "browser.json").write_text(browser)
        baseline = json.loads(
            maintenance("python", "-m", "scripts.single_host_fixture", "snapshot")
        )

        def child_signal(module, signum):
            code = (
                "import os,signal,pathlib\nfound=[]\nfor p in pathlib.Path('/proc').iterdir():\n if p.name.isdigit():\n  try: args=(p/'cmdline').read_bytes().split(b'\\0')\n  except (OSError,PermissionError): continue\n  if args[1:3]==[b'-m',"
                + repr(module.encode())
                + "]: found.append(int(p.name))\nassert len(found)==1\nos.kill(found[0],"
                + str(signum)
                + ")"
            )
            run(
                *compose,
                "exec",
                "-T",
                "engine",
                "python",
                "-c",
                code,
                label="child-signal",
            )

        for module in ("scripts.run_api", "scripts.run_collector_worker"):
            count = inspect_service("engine")["RestartCount"]
            child_signal(module, 9)
            wait(
                lambda: inspect_service("engine")["RestartCount"] > count
                and healthy("engine"),
                "restart-after-" + module,
            )
            request("/api/v1/auth/me", token=token)
        count = inspect_service("engine")["RestartCount"]
        child_signal("scripts.run_collector_worker", 19)
        wait(
            lambda: inspect_service("engine")["State"]["Health"]["Status"]
            == "unhealthy",
            "stalled-worker-unhealthy",
        )
        request("/health")
        if inspect_service("engine")["RestartCount"] != count:
            raise RuntimeError("Unexpected restart during stalled-worker observation")
        child_signal("scripts.run_collector_worker", 18)
        wait(lambda: healthy("engine"), "resumed-worker-healthy")
        before = json.loads(
            maintenance("python", "-m", "scripts.single_host_fixture", "snapshot")
        )
        if before != baseline:
            raise RuntimeError(
                "Process fault probes changed protected fixture identities"
            )
        old = {
            name: inspect_service(name)["Id"]
            for name in ("postgres", "engine", "gateway")
        }
        run(*compose, "down", label="remove-owned-containers-preserve-bind")
        run(
            *compose,
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            label="recreate-three-services",
        )
        wait(lambda: all(healthy(n) for n in old), "recreated-services-ready")
        after = json.loads(
            maintenance("python", "-m", "scripts.single_host_fixture", "snapshot")
        )
        if before != after or any(inspect_service(n)["Id"] == old[n] for n in old):
            raise RuntimeError("Recreation persistence/identity mismatch")
        request("/api/v1/auth/me", token=token)
        report["checks"].append(
            "postgres-identities-and-session-survive-container-recreation"
        )
        report["snapshot"] = after
        report["status"] = "RUNTIME_ACCEPTANCE_PASSED_WITH_STAGING_EXCEPTIONS"
    except Exception as error:
        report["error"] = redact(str(error))
    finally:
        if proxy_started:
            proxy.shutdown()
        if proxy:
            proxy.server_close()
        try:
            # Interrupted one-shot helpers also carry an exact run label.
            for suffix in ("maintenance", "utility"):
                leftover = subprocess.run(
                    ["docker", "inspect", project + "-" + suffix],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if leftover.returncode == 0:
                    row = json.loads(leftover.stdout)[0]
                    if row["Config"]["Labels"].get("aptron.sh02.run") != project:
                        raise RuntimeError("Helper cleanup ownership mismatch")
                    run("docker", "rm", "-f", row["Id"], label="cleanup-helper")
            if owned:
                for name in ("engine", "gateway", "postgres"):
                    logs = subprocess.run(
                        [*compose, "logs", "--no-color", "--tail", "80", name],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    (evidence / (name + ".log")).write_text(
                        redact(logs.stdout + logs.stderr)
                    )
                # Every resource is isolated under this freshly allocated project.
                for cid in run(
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                    label="cleanup-ownership",
                ).split():
                    row = json.loads(
                        run("docker", "inspect", cid, label="cleanup-inspect")
                    )[0]
                    if (
                        row["Config"]["Labels"].get("com.docker.compose.project")
                        != project
                    ):
                        raise RuntimeError("Cleanup ownership mismatch")
                run(*compose, "down", "--remove-orphans", label="cleanup-owned-project")
                # This directory was exclusively allocated by this run. Never
                # accept a caller path or mount the parent/host root for deletion.
                run(
                    "docker",
                    "run",
                    "--rm",
                    "--pull",
                    "never",
                    "--network",
                    "none",
                    "--name",
                    project + "-utility",
                    "--label",
                    "aptron.sh02.run=" + project,
                    "--user",
                    "0",
                    "--mount",
                    "type=bind,src=" + str(private / "pgdata") + ",dst=/owned",
                    "--entrypoint",
                    "/bin/sh",
                    images["postgres"],
                    "-c",
                    "find /owned -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +",
                    label="cleanup-synthetic-data",
                )
                if run(
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                    label="verify-cleanup",
                ).strip():
                    raise RuntimeError("Fixture containers remain")
                if run(
                    "docker",
                    "network",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                    label="verify-network-cleanup",
                ).strip():
                    raise RuntimeError("Fixture networks remain")
                if run(
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    "label=aptron.sh02.run=" + project,
                    label="verify-helper-cleanup",
                ).strip():
                    raise RuntimeError("Fixture helpers remain")
            shutil.rmtree(private)
            report["cleanup_completed"] = True
        except Exception as error:
            report["cleanup_error"] = redact(str(error))
            report["status"] = "FAILED"
        (evidence / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "source_sha",
                    "checks",
                    "cleanup_completed",
                    "production_eligible",
                )
            },
            indent=2,
        )
    )
    return (
        0
        if report["status"] == "RUNTIME_ACCEPTANCE_PASSED_WITH_STAGING_EXCEPTIONS"
        and report["cleanup_completed"]
        else 1
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-evidence", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        exit_code = main(args.image_evidence, args.evidence)
    except Exception as error:
        # Only explicitly authored diagnostic text is safe for hosted logs.
        diagnostic = preflight_diagnostic(error)
        if not args.evidence.resolve().is_relative_to(ROOT):
            args.evidence.mkdir(parents=True, exist_ok=True)
            (args.evidence / "acceptance.json").write_text(
                json.dumps(
                    {
                        "status": "BLOCKED_BEFORE_DEPLOYMENT",
                        **diagnostic,
                        "production_eligible": False,
                        "receipts_enabled": False,
                        "reconciliation_enabled": False,
                    },
                    indent=2,
                )
                + "\n"
            )
        print("SH-02 preflight blocked: " + json.dumps(diagnostic), file=sys.stderr)
        exit_code = 1
    raise SystemExit(exit_code)
