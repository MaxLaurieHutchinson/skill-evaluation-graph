"""
test_receipts.py - Tests for canonical JSON serialization, input tree digest, and tamper evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seg.receipts import (
    canonical_json_bytes,
    compute_tree_digest,
    generate_evaluation_receipt,
    sha256_digest,
)


class TestReceiptsSubsystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        (self.root_path / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
        (self.root_path / "helper.py").write_text("print('hello')\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_canonical_json_bytes(self):
        dict_a = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}
        dict_b = {"a": 1, "nested": {"y": 25, "z": 26}, "b": 2}

        bytes_a = canonical_json_bytes(dict_a)
        bytes_b = canonical_json_bytes(dict_b)

        # Canonical serialization must be byte-for-byte identical regardless of initial key ordering
        self.assertEqual(bytes_a, bytes_b)
        self.assertNotIn(b" ", bytes_a)  # Compact separators (",", ":")

    def test_compute_tree_digest(self):
        digest_1 = compute_tree_digest(self.root_path)
        self.assertEqual(len(digest_1), 64)

        # Adding ephemeral receipt directory MUST NOT alter tree digest
        receipts_dir = self.root_path / ".audit_receipts"
        receipts_dir.mkdir()
        (receipts_dir / "receipt.json").write_text("{}", encoding="utf-8")
        digest_after_receipt = compute_tree_digest(self.root_path)
        self.assertEqual(digest_1, digest_after_receipt)

        # Modifying a tracked file MUST change the digest
        (self.root_path / "helper.py").write_text("print('modified')\n", encoding="utf-8")
        digest_2 = compute_tree_digest(self.root_path)
        self.assertNotEqual(digest_1, digest_2)

    def test_tamper_evident_receipt_digest(self):
        receipt = generate_evaluation_receipt(
            run_id="test-run-001",
            target_skill_path=self.root_path,
            seg_version="1.0.0",
            config={"target_score": 95},
            joined_evidence={"score": 100},
            oracle_decision={"verdict": "ACCEPT"},
        )

        orig_digest = receipt["receipt_digest"]
        self.assertEqual(len(orig_digest), 64)

        # Verify receipt digest calculation over receipt payload
        payload_copy = dict(receipt)
        del payload_copy["receipt_digest"]
        expected_digest = sha256_digest(canonical_json_bytes(payload_copy))
        self.assertEqual(orig_digest, expected_digest)

        # Tampering with any field invalidates the digest
        payload_copy["oracle_decision"]["verdict"] = "TAMPERED"
        tampered_digest = sha256_digest(canonical_json_bytes(payload_copy))
        self.assertNotEqual(orig_digest, tampered_digest)

    def test_tree_digest_includes_manifests_and_excludes_ephemeral(self):
        base_digest = compute_tree_digest(self.root_path)

        # 1. Ephemeral directories (.seg_backup, __pycache__) MUST NOT change digest
        (self.root_path / ".seg_backup").mkdir()
        (self.root_path / ".seg_backup" / "backup.txt").write_text("backup", encoding="utf-8")
        (self.root_path / "__pycache__").mkdir()
        (self.root_path / "__pycache__" / "temp.pyc").write_bytes(b"\x00\x01")
        self.assertEqual(compute_tree_digest(self.root_path), base_digest)

        # 2. Manifest directories (.codex-plugin, .claude-plugin, .agents) MUST be included in digest
        cx_dir = self.root_path / ".codex-plugin"
        cx_dir.mkdir()
        (cx_dir / "plugin.json").write_text('{"name": "test"}', encoding="utf-8")
        cx_digest = compute_tree_digest(self.root_path)
        self.assertNotEqual(base_digest, cx_digest)

        agents_dir = self.root_path / ".agents" / "plugins"
        agents_dir.mkdir(parents=True)
        (agents_dir / "marketplace.json").write_text('{"plugins": []}', encoding="utf-8")
        agents_digest = compute_tree_digest(self.root_path)
        self.assertNotEqual(cx_digest, agents_digest)

    def test_receipt_digest_tamper_evidence_execution_fields(self):
        iterations_log = [
            {"cycle": 1, "score": 85, "verdict": "REVISE"},
            {"cycle": 2, "score": 100, "verdict": "PASS"},
        ]
        receipt = generate_evaluation_receipt(
            run_id="test-run-exec-001",
            target_skill_path=self.root_path,
            seg_version="1.0.0",
            config={"target_score": 95},
            joined_evidence={"score": 100},
            oracle_decision={"verdict": "ACCEPT"},
            final_status="ACCEPTED",
            final_score=100.0,
            total_iterations=2,
            iterations_log=iterations_log,
        )

        orig_digest = receipt["receipt_digest"]
        self.assertEqual(receipt["final_status"], "ACCEPTED")
        self.assertEqual(receipt["final_score"], 100.0)
        self.assertEqual(receipt["total_iterations"], 2)

        # Tampering with final_status MUST invalidate digest
        payload_copy = dict(receipt)
        del payload_copy["receipt_digest"]
        payload_copy["final_status"] = "FAILED"
        self.assertNotEqual(orig_digest, sha256_digest(canonical_json_bytes(payload_copy)))

        # Tampering with iterations_log MUST invalidate digest
        payload_copy2 = dict(receipt)
        del payload_copy2["receipt_digest"]
        payload_copy2["iterations_log"] = []
        self.assertNotEqual(orig_digest, sha256_digest(canonical_json_bytes(payload_copy2)))

    def test_receipt_includes_node_results_and_tamper_evidence(self):
        sample_node_results = [
            {
                "node_id": "schema",
                "status": "SUCCESS",
                "output_digest": "abcdef1234567890" * 4,
                "metrics": {"name": "test"},
            }
        ]
        receipt = generate_evaluation_receipt(
            run_id="test-run-nodes-001",
            target_skill_path=self.root_path,
            seg_version="1.0.0",
            node_results=sample_node_results,
        )
        self.assertEqual(len(receipt["node_results"]), 1)
        self.assertEqual(receipt["node_results"][0]["node_id"], "schema")

        # Tampering with node_results must invalidate receipt_digest
        orig_digest = receipt["receipt_digest"]
        payload_copy = dict(receipt)
        del payload_copy["receipt_digest"]
        payload_copy["node_results"] = []
        self.assertNotEqual(orig_digest, sha256_digest(canonical_json_bytes(payload_copy)))


if __name__ == "__main__":
    unittest.main()
