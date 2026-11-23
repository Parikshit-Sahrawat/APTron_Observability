import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SingleHostTests(unittest.TestCase):
    def run_pair(self, *, child_exit=False, ignore_interrupt=False):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / str(i) for i in range(2)]
            commands = []
            for i, path in enumerate(paths):
                code = (
                    "import os,signal,time; from pathlib import Path; "
                    + (
                        "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                        if ignore_interrupt
                        else ""
                    )
                    + f"Path({str(path)!r}).write_text(str(os.getpid())); "
                    + ("time.sleep(.3)" if child_exit and i == 0 else "time.sleep(60)")
                )
                commands.append([sys.executable, "-c", code])
            runner = (
                "import sys,json; sys.path.insert(0,sys.argv[1]); "
                "from scripts.run_single_host import supervise; "
                "sys.exit(supervise(json.loads(sys.argv[2]),shutdown_timeout=.3,poll_interval=.02))"
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    runner,
                    str(ROOT / "backend"),
                    json.dumps(commands),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5
                while not all(p.exists() for p in paths):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail("Engine did not start both test children")
                    time.sleep(0.02)
                if not child_exit:
                    process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=5), 1 if child_exit else 0)
                for path in paths:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(int(path.read_text()), 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    def test_child_failure_stops_peer(self):
        self.run_pair(child_exit=True)

    def test_sigterm_stops_and_reaps_children(self):
        self.run_pair()

    def test_shutdown_deadline_kills_unresponsive_child(self):
        self.run_pair(ignore_interrupt=True)

    def test_start_failure_reaps_started_child(self):
        module = load_module("supervisor", "backend/scripts/run_single_host.py")
        self.assertEqual(
            module.supervise(
                [
                    [sys.executable, "-c", "import time; time.sleep(60)"],
                    ["/aptron-no-such-executable"],
                ],
                shutdown_timeout=0.2,
            ),
            1,
        )

    def test_stale_missing_and_future_heartbeat_fail_closed(self):
        module = load_module("health", "backend/scripts/check_single_host.py")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "heartbeat"
            self.assertFalse(module.heartbeat_fresh(path, now=100))
            for value in ("nan", "inf", "bad", "1", "101"):
                path.write_text(value)
                self.assertFalse(module.heartbeat_fresh(path, now=100))
            path.write_text("90")
            self.assertTrue(module.heartbeat_fresh(path, now=100))

    def test_resolved_deployment_rejects_unsafe_overrides(self):
        module = load_module("contract", "scripts/validate_single_host.py")
        service = {"image": "example/image@sha256:" + "a" * 64}
        config = {
            "services": {
                "gateway": {
                    **service,
                    "ports": [{"target": 8443}],
                    "networks": {"ingress": {"ipv4_address": "172.30.90.2"}},
                },
                "engine": {
                    **service,
                    "command": ["python", "-m", "scripts.run_single_host"],
                    "environment": {
                        "ENVIRONMENT": "production",
                        "TRUSTED_PROXY_IPS": "172.30.90.2",
                    },
                },
                "postgres": {
                    **service,
                    "volumes": [
                        {
                            "type": "bind",
                            "source": "/srv/aptron/pgdata",
                            "target": "/var/lib/postgresql/data",
                        }
                    ],
                },
            },
            "networks": {
                "database": {"internal": True},
                "ingress": {"ipam": {"config": [{"subnet": "172.30.90.0/28"}]}},
            },
        }
        module.validate(config)
        for service_name, key, value in (
            ("engine", "ports", [{"target": 8000}]),
            ("postgres", "image", "postgres:17"),
            ("gateway", "privileged", True),
            (
                "engine",
                "environment",
                {"ENVIRONMENT": "demo", "TRUSTED_PROXY_IPS": "172.30.90.2"},
            ),
        ):
            bad = copy.deepcopy(config)
            bad["services"][service_name][key] = value
            with self.assertRaises(ValueError):
                module.validate(bad)

    def test_gateway_render_keeps_hash_csp_and_clears_forwarding(self):
        with tempfile.TemporaryDirectory() as directory:
            index, output = (
                Path(directory) / "index.html",
                Path(directory) / "nginx.conf",
            )
            index.write_text(
                "<script>document.documentElement.dataset.theme='dark'</script>"
            )
            subprocess.run(
                [
                    "node",
                    str(ROOT / "frontend/scripts/render-production-nginx.mjs"),
                    str(index),
                    str(output),
                    "http://engine:8000",
                    str(ROOT / "deploy/single-host/nginx.conf.template"),
                ],
                check=True,
            )
            rendered = output.read_text()
            self.assertIn("'sha256-", rendered)
            self.assertNotIn("__INLINE_SCRIPT_HASHES__", rendered)
            self.assertIn('proxy_set_header Forwarded ""', rendered)
            self.assertIn("proxy_pass http://engine:8000", rendered)
            self.assertIn("listen 8443 ssl", rendered)
            # Existing callers retain the historical template/upstream defaults.
            subprocess.run(
                [
                    "node",
                    str(ROOT / "frontend/scripts/render-production-nginx.mjs"),
                    str(index),
                    str(output),
                ],
                check=True,
            )
            self.assertIn("proxy_pass http://api:8000", output.read_text())

    def test_compose_source_retains_isolation_and_single_tmpfs_mount(self):
        import yaml

        config = yaml.safe_load((ROOT / "deploy/single-host/compose.yaml").read_text())
        self.assertEqual(set(config["services"]), {"gateway", "engine", "postgres"})
        engine = config["services"]["engine"]
        self.assertEqual(engine["tmpfs"], ["/tmp:rw,noexec,nosuid,size=64m,mode=1777"])
        self.assertNotIn("ports", engine)
        self.assertNotIn("ports", config["services"]["postgres"])
        self.assertTrue(config["networks"]["database"]["internal"])
