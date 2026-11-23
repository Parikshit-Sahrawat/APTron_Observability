import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SH02Tests(unittest.TestCase):
    def test_health_observes_production_https_denial_without_bypass(self):
        health = load("sh02_health", "backend/scripts/check_single_host.py")

        class Handler(BaseHTTPRequestHandler):
            status = 403
            body = {"detail": "HTTPS required"}

            def do_GET(self):
                self.send_response(self.status)
                self.end_headers()
                self.wfile.write(json.dumps(self.body).encode())

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:" + str(server.server_port)
            self.assertTrue(health.api_ready(url))
            Handler.body = {"detail": "arbitrary denial"}
            self.assertFalse(health.api_ready(url))
            Handler.status = 500
            self.assertFalse(health.api_ready(url))
            Handler.status = 200
            self.assertFalse(health.api_ready(url))
            self.assertTrue(health.api_ready(url, production=False))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_runner_rejects_nonhosted_and_remote_docker(self):
        runner = load("sh02_runner", "scripts/staging/single_host_acceptance.py")
        for env in (
            {},
            {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
            {
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "DOCKER_HOST": "tcp://remote:2375",
            },
        ):
            with self.assertRaises(ValueError):
                runner.runner_guard(env)
        runner.runner_guard(
            {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"}
        )

    def test_forwarder_refuses_public_and_outside_subnet(self):
        runner = load("sh02_forwarder", "scripts/staging/single_host_acceptance.py")
        for address, subnet in (
            ("8.8.8.8", "8.8.8.0/24"),
            ("172.30.100.2", "172.30.101.0/28"),
        ):
            with self.assertRaises(ValueError):
                runner.forwarder(address, subnet)
        server = runner.forwarder("172.30.100.2", "172.30.100.0/28")
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.server_close()

    def test_only_exact_scanned_images_and_owned_mounts_are_deployed(self):
        runner = load("sh02_isolation", "scripts/staging/single_host_acceptance.py")
        images = {
            name: "sha256:" + digit * 64
            for name, digit in (
                ("engine", "a"),
                ("gateway", "b"),
                ("postgres", "c"),
                ("migration", "d"),
            )
        }
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            config = {
                "services": {
                    "engine": {
                        "image": images["engine"],
                        "user": "10001:10001",
                        "networks": {"database": {}, "ingress": {}},
                        "command": ["python", "-m", "scripts.run_single_host"],
                        "environment": {
                            "ENVIRONMENT": "production",
                            "TRUSTED_PROXY_IPS": "172.30.100.2",
                        },
                    },
                    "gateway": {
                        "image": images["gateway"],
                        "ports": [{"target": 8443}],
                        "networks": {"ingress": {"ipv4_address": "172.30.100.2"}},
                    },
                    "postgres": {
                        "image": images["postgres"],
                        "networks": {"database": {}},
                        "volumes": [
                            {
                                "type": "bind",
                                "source": str(private / "pgdata"),
                                "target": "/var/lib/postgresql/data",
                            }
                        ],
                    },
                },
                "networks": {
                    "database": {"internal": True},
                    "ingress": {"ipam": {"config": [{"subnet": "172.30.100.0/28"}]}},
                },
                "secrets": {"tls_key": {"file": str(private / "tls.key")}},
            }
            isolated = runner.isolated_config(copy.deepcopy(config), images, private)
            self.assertTrue(isolated["networks"]["ingress"]["internal"])
            self.assertNotIn("ports", isolated["services"]["gateway"])
            bad = copy.deepcopy(config)
            bad["services"]["postgres"]["volumes"][0]["source"] = "/srv/customer/pgdata"
            with self.assertRaises(ValueError):
                runner.isolated_config(bad, images, private)
            bad = copy.deepcopy(config)
            bad["services"]["engine"]["image"] = "sha256:" + "f" * 64
            with self.assertRaises(ValueError):
                runner.isolated_config(bad, images, private)
            bad = copy.deepcopy(config)
            bad["services"]["gateway"]["cap_add"] = ["SYS_ADMIN"]
            with self.assertRaises(ValueError):
                runner.isolated_config(bad, images, private)
