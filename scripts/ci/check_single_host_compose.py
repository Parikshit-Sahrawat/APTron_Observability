"""Render the actual three-service candidate with synthetic config; never deploy."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_single_host import validate


def main():
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="aptron-compose-contract-") as directory:
        private = Path(directory)
        for name in ("owner-password", "tls.crt", "tls.key", "nginx.conf"):
            path = private / name
            path.write_text("synthetic-config-only\n")
            path.chmod(0o600)
        engine = private / "engine.env"
        engine.write_text(
            "DATABASE_URL=postgresql+psycopg://fixture:fixture@postgres/aptron\nCORS_ORIGINS=https://fixture.invalid\n"
        )
        engine.chmod(0o600)
        data = private / "pgdata"
        data.mkdir()
        env = dict(os.environ)
        env.update(
            {
                "APTRON_PROJECT_NAME": "aptron-contract-only",
                "APTRON_BACKEND_IMAGE": "fixture/backend@sha256:" + "a" * 64,
                "APTRON_FRONTEND_IMAGE": "fixture/frontend@sha256:" + "b" * 64,
                "APTRON_POSTGRES_IMAGE": "fixture/postgres@sha256:" + "c" * 64,
                "APTRON_PGDATA": str(data),
                "APTRON_ENGINE_ENV_FILE": str(engine),
                "APTRON_POSTGRES_PASSWORD_FILE": str(private / "owner-password"),
                "APTRON_TLS_CERTIFICATE": str(private / "tls.crt"),
                "APTRON_TLS_KEY": str(private / "tls.key"),
                "APTRON_GATEWAY_CONFIG": str(private / "nginx.conf"),
                "APTRON_BIND_ADDRESS": "127.0.0.1",
                "APTRON_HTTPS_PORT": "8443",
                "APTRON_INGRESS_SUBNET": "172.30.90.0/28",
                "APTRON_GATEWAY_IP": "172.30.90.2",
            }
        )
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                os.devnull,
                "-f",
                str(root / "deploy/single-host/compose.yaml"),
                "config",
                "--format",
                "json",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        validate(json.loads(result.stdout))
    print(
        "Actual Compose render/structure PASS; no images pulled or containers started"
    )


if __name__ == "__main__":
    main()
