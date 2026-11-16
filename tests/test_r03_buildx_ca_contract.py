"""Hosted Buildx must provide real CA bundle, not disable TLS checks."""
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/local-uat-image-validation.yml"
UAT=ROOT/"backend/Dockerfile.uat"

class UATBuildCertificateTests(TestCase):
    def test_hosted_runner_supplies_trusted_public_ca_bundle_to_backend_build(self):
        source=WORKFLOW.read_text()
        uat_step=source.split("name: Build backend locally on hosted runner (no push)",1)[1].split("name: Build frontend locally",1)[0]
        self.assertIn("proxy_ca=/etc/ssl/certs/ca-certificates.crt",uat_step)
        self.assertIn("secret-files: |",uat_step)
        self.assertIn("test -s /etc/ssl/certs/ca-certificates.crt",source)
        self.assertIn("push: false",uat_step)
        self.assertNotIn("tls-verify=false",uat_step)

    def test_release_uat_still_requires_ca_for_pip_and_apk(self):
        source=UAT.read_text()
        self.assertGreaterEqual(source.count("required=true"),2)
        self.assertIn("PIP_CERT=/run/secrets/proxy_ca",source)
        self.assertIn("SSL_CERT_FILE=/run/secrets/proxy_ca",source)
        self.assertNotIn("required=false",source)
