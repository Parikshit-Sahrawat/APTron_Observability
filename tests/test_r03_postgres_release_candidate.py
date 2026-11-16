"""Image hardening selection may not weaken existing eight-role policy."""
import json
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/"deploy/release/Dockerfile.postgres"


class PostgreSQLReleaseCandidateTests(TestCase):
    def test_exact_postgres17_source_digest_and_build_toolchain(self):
        s=RELEASE.read_text()
        self.assertIn("FROM postgres:17-alpine@sha256:3540c0362c809df084ffac0ae69fe794515f9de92692f02178bcdce0ef0302ac",s)
        self.assertIn("FROM golang:1.27.4-alpine3.23@sha256:7a93747afee80359e81dbe39c8a65037b147cada0262bf86f5b96dd06842b368 AS gosu-build",s)
        self.assertIn("6456aaa0f3c854d199d0f037f068eb97515b7513",s)
        self.assertIn("go mod verify",s)

    def test_original_entrypoint_and_uid_are_preserved(self):
        s=RELEASE.read_text()
        self.assertIn("gosu postgres id -u | grep -qx '70'",s)
        self.assertIn("COPY --from=gosu-build /out/gosu /usr/local/bin/gosu",s)
        self.assertNotIn("ENTRYPOINT [",s)
        self.assertNotIn("USER 10001",s)
        self.assertNotIn("VOLUME [",s)

    def test_copyright_and_build_info_carried_into_runtime(self):
        s=RELEASE.read_text()
        self.assertIn("/usr/share/licenses/gosu/LICENSE",s)
        self.assertIn("/usr/share/doc/gosu-buildinfo.txt",s)
        self.assertIn("NOT a deployment",s)

    def test_all_eight_release_scan_roles_remain_unchanged(self):
        data=json.loads((ROOT/".ci/image-coverage.json").read_text())
        roles={r["role"] for r in data["roles"]}
        self.assertEqual(roles,{"backend-runtime","backend-migration","uat-backend","frontend","postgres","ingestion-gateway","otel-contrib","production-frontend"})
        self.assertEqual(next(x for x in data["roles"] if x["role"]=="postgres")["file"],"deploy/release/Dockerfile.postgres")
