"""Architecture evidence resolves against the canonical nested repository."""

import json
from pathlib import Path
import sys
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
sys.path.insert(0, str(PACKAGE / "src"))
from seg.evaluators import build_default_evaluation_dag


class TestArchitectureDocs(unittest.TestCase):
    def test_architecture_evidence_points_to_real_package_sources(self):
        spec = json.loads((REPO / "docs/architecture/seg.architecture.json").read_text(encoding="utf-8"))
        paths = [s["path"] for c in spec["components"] for s in c.get("sources", [])]
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue((REPO / path).is_file())
                self.assertTrue((REPO / path).resolve().is_relative_to(PACKAGE))
        self.assertNotIn("repository", spec.get("meta", {}))

    def test_default_dag_defers_schema_consumers_to_second_wave(self):
        waves = build_default_evaluation_dag().get_execution_plan()
        self.assertEqual([set(w) for w in waves], [
            {"schema", "links_syntax", "safety_privacy"},
            {"portability", "trigger_routing", "token_economics", "behaviour_policy"},
        ])
