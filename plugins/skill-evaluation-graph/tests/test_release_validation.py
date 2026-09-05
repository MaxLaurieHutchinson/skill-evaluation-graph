"""The canonical release validator must detect incomplete or inconsistent trees."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "plugins/skill-evaluation-graph/src"))


class TestReleaseValidation(unittest.TestCase):
    def validate(self, repo):
        from validate_release import validate_release
        with contextlib.redirect_stdout(io.StringIO()):
            return validate_release(repo)

    def test_canonical_repository_validates_without_mutation(self):
        from seg.receipts import compute_tree_digest
        before = compute_tree_digest(REPO)
        self.assertTrue(self.validate(REPO))
        self.assertEqual(compute_tree_digest(REPO), before)

    def test_missing_assets_and_version_drift_fail_validation(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "release"
            shutil.copytree(REPO, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist"))
            plugin = repo / "plugins/skill-evaluation-graph"
            cases = [
                ("missing scenario", plugin / "evaluations/scenarios/tdd_pressure.json", None),
                ("missing tests", plugin / "tests/test_repair_safety.py", None),
                ("manifest mismatch", plugin / ".claude-plugin/plugin.json", '{"name":"skill-evaluation-graph","version":"0.0.0"}'),
                ("empty marketplace", repo / ".agents/plugins/marketplace.json", '{"plugins":[]}'),
            ]
            for label, file, replacement in cases:
                original = file.read_bytes()
                try:
                    if replacement is None:
                        file.unlink()
                    else:
                        file.write_text(replacement, encoding="utf-8")
                    with self.subTest(case=label):
                        self.assertFalse(self.validate(repo))
                finally:
                    file.write_bytes(original)
