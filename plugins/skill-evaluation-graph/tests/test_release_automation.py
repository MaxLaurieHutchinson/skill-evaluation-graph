"""Regression contract for SEG release automation and deterministic artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_release import build_release_artifacts
from validate_release import validate_release


class TestReleaseAutomation(unittest.TestCase):
    def test_release_please_configuration_tracks_all_distributed_versions(self):
        config = json.loads((REPO / "release-please-config.json").read_text(encoding="utf-8"))
        package = config["packages"]["."]
        self.assertEqual(package["release-type"], "simple")
        self.assertEqual(package["version-file"], "version.txt")
        self.assertTrue(config["include-v-in-tag"])
        self.assertFalse(config["include-component-in-tag"])

        version_file = REPO / package["version-file"]
        self.assertTrue(version_file.is_file())
        canonical_version = version_file.read_text(encoding="utf-8").strip()
        self.assertRegex(canonical_version, r"^\d+\.\d+\.\d+$")

        extra = package["extra-files"]
        json_targets = {
            item["path"]: item.get("jsonpath")
            for item in extra
            if isinstance(item, dict) and item.get("type") == "json"
        }
        self.assertEqual(
            json_targets,
            {
                "plugins/skill-evaluation-graph/.codex-plugin/plugin.json": "$.version",
                "plugins/skill-evaluation-graph/.claude-plugin/plugin.json": "$.version",
                "plugins/skill-evaluation-graph/gemini-extension.json": "$.version",
            },
        )
        for path in json_targets:
            manifest = json.loads((REPO / path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], canonical_version, path)

        generic_targets = {
            item["path"] for item in extra
            if isinstance(item, dict) and item.get("type") == "generic"
        }
        self.assertIn("plugins/skill-evaluation-graph/src/seg/__init__.py", generic_targets)

        runtime = (REPO / "plugins/skill-evaluation-graph/src/seg/__init__.py").read_text(encoding="utf-8")
        self.assertIn("x-release-please-version", runtime)
        match = re.search(r'__version__\s*=\s*"([^"]+)"', runtime)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), canonical_version)

    def test_release_workflow_is_test_gated_and_builds_release_assets(self):
        workflow = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn("Test and Validate SEG", workflow)
        self.assertIn("conclusion == 'success'", workflow)
        self.assertIn("head_branch == 'main'", workflow)
        self.assertIn("head_repository.full_name == github.repository", workflow)
        self.assertIn("release-please-oss/release-please-action@7a6e2d3ff9e08fbd69d0430e4be5d90a3e96c28c", workflow)
        self.assertIn("scripts/build_release.py", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("steps.release.outputs.release_created", workflow)

    def test_release_builder_is_deterministic_and_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            plugin = root / "plugins/skill-evaluation-graph"
            (plugin / "scripts").mkdir(parents=True)
            (plugin / "SKILL.md").write_text("---\nname: skill-evaluation-graph\ndescription: test\n---\n", encoding="utf-8")
            (plugin / "scripts/tool.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "README.md").write_text("# SEG\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git/config").write_text("secret-ish metadata", encoding="utf-8")
            (root / ".audit_receipts").mkdir()
            (root / ".audit_receipts/run.json").write_text("{}", encoding="utf-8")

            out1 = root / "dist-one"
            out2 = root / "dist-two"
            first = build_release_artifacts(root, "1.2.3", out1)
            second = build_release_artifacts(root, "1.2.3", out2)

            for key in ("skill_zip", "repository_zip", "checksums"):
                self.assertEqual(first[key].read_bytes(), second[key].read_bytes(), key)

            with zipfile.ZipFile(first["skill_zip"]) as archive:
                names = archive.namelist()
                self.assertIn("skill-evaluation-graph/SKILL.md", names)
                self.assertIn("skill-evaluation-graph/scripts/tool.py", names)
                self.assertFalse(any(name.startswith("plugins/") for name in names))

            with zipfile.ZipFile(first["repository_zip"]) as archive:
                names = archive.namelist()
                self.assertIn("skill-evaluation-graph-v1.2.3/README.md", names)
                self.assertIn("skill-evaluation-graph-v1.2.3/plugins/skill-evaluation-graph/SKILL.md", names)
                self.assertFalse(any("/.git/" in name or "/.audit_receipts/" in name or "/dist-one/" in name or "/dist-two/" in name for name in names))

            checksum_lines = first["checksums"].read_text(encoding="utf-8").splitlines()
            expected = {}
            for line in checksum_lines:
                digest, filename = line.split("  ", 1)
                expected[filename] = digest
            for key in ("skill_zip", "repository_zip"):
                path = first[key]
                self.assertEqual(expected[path.name], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_release_builder_packages_the_canonical_repository(self):
        version = (REPO / "version.txt").read_text(encoding="utf-8").strip()
        with tempfile.TemporaryDirectory() as td:
            artifacts = build_release_artifacts(REPO, version, Path(td))
            with zipfile.ZipFile(artifacts["skill_zip"]) as archive:
                names = set(archive.namelist())
                self.assertIn("skill-evaluation-graph/SKILL.md", names)
                self.assertIn("skill-evaluation-graph/src/seg/receipts.py", names)
                self.assertIn("skill-evaluation-graph/evaluations/scenarios/tdd_pressure.json", names)
            with zipfile.ZipFile(artifacts["repository_zip"]) as archive:
                names = set(archive.namelist())
                prefix = f"skill-evaluation-graph-v{version}/"
                self.assertIn(prefix + "README.md", names)
                self.assertIn(prefix + "RELEASING.md", names)
                self.assertIn(prefix + ".github/workflows/release.yml", names)
                self.assertFalse(any("/.git/" in name or "/.audit_receipts/" in name or "/dist/" in name for name in names))
            checksum_lines = artifacts["checksums"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(checksum_lines), 2)

    def test_release_validator_requires_release_automation_regressions(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "release"
            shutil.copytree(REPO, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
            target = repo / "plugins/skill-evaluation-graph/tests/test_release_automation.py"
            target.unlink()
            self.assertFalse(validate_release(repo))


if __name__ == "__main__":
    unittest.main()
