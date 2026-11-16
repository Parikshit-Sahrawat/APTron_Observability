"""Raw legal-material collection must expose gaps and never issue signoff."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collect_legal", ROOT / "scripts/ci/r03_collect_go_legal.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class CompiledLegalMaterialTests(unittest.TestCase):
    def test_preserves_nested_notices_replacements_and_missing_modules(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("source", "go", "module", "empty"):
                (root / name).mkdir()
            (root / "source/LICENSE").write_text("Upstream license text\n")
            (root / "go/LICENSE").write_text("Go license text\n")
            (root / "module/subpackage").mkdir()
            (root / "module/subpackage/NOTICE.txt").write_text("Nested notice\n")
            (root / "module/.github/workflows").mkdir(parents=True)
            (root / "module/.github/license-header.txt").write_text("Hidden license header\n")
            (root / "module/.github/workflows/license.yml").write_text("License workflow material\n")
            (root / "module/LICENSE").symlink_to(root / "go/LICENSE")
            packages = [
                {"Module": {"Path": "example.test/module", "Version": "v1", "Replace": {
                    "Path": "example.test/patched", "Version": "v2", "Dir": str(root / "module")}}},
                {"Module": {"Path": "example.test/empty", "Version": "v1", "Dir": str(root / "empty")}},
            ]
            data = "\n".join(json.dumps(x) for x in packages)
            result = collector.collect(data, root / "source", root / "go", root / "output")
            self.assertEqual(result["status"], "PENDING_ACCOUNTABLE_REVIEW")
            self.assertIsNone(result["reviewer"])
            self.assertFalse(result["release_eligible"])
            self.assertEqual(result["missing_modules"], ["example.test/empty"])
            patched = result["modules"][1]
            self.assertEqual(patched["replacement"]["Version"], "v2")
            self.assertEqual(len(patched["files"]), 3)  # Symlink license excluded.
            self.assertEqual(sorted(Path(name).name for name in patched["files"]),
                             ["NOTICE.txt", "license-header.txt", "license.yml"])
            self.assertTrue(any("/.github/" in name for name in patched["files"]))
            # The pinned upload action excludes hidden paths by default. The
            # exact generated legal bundle must opt in or its manifest is broken.
            workflow = yaml.load((ROOT / ".github/workflows/sec001-r03-candidates.yml").read_text(), Loader=yaml.BaseLoader)
            uploads = [step["with"] for step in workflow["jobs"]["candidate-evidence"]["steps"]
                       if step.get("with", {}).get("name") == "sec001-r03-rebuilt-collector-binary-for-uat"]
            self.assertEqual(len(uploads), 1)
            self.assertEqual(uploads[0]["include-hidden-files"], "true")
            self.assertEqual(uploads[0]["path"], "${{ runner.temp }}/r03-patched-collector/")
            for line in (root / "output/SHA256SUMS").read_text().splitlines():
                sha, name = line.split("  ", 1)
                self.assertEqual(collector.digest(root / "output" / name), sha)

    def test_missing_upstream_license_or_bad_go_list_cannot_be_reported_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("source", "go", "module"):
                (root / name).mkdir()
            data = json.dumps({"Module": {"Path": "example.test/a", "Dir": str(root / "module")}})
            with self.assertRaisesRegex(ValueError, "license absent"):
                collector.collect(data, root / "source", root / "go", root / "missing")
            with self.assertRaisesRegex(ValueError, "unresolved package"):
                collector.collect('{"Error":{"Err":"missing"}}', root / "source", root / "go", root / "bad")
