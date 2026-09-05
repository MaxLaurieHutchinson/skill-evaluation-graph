"""
test_terminology.py - Regression test enforcing canonical SEG vocabulary and preventing retired terms.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = Path(__file__).parent.parent


class TestCanonicalTerminology(unittest.TestCase):
    """
    Ensures retired and non-canonical terms do not regress into SEG source code,
    scripts, documentation, or specifications.
    """

    BANNED_TERMS = [
        "immutable receipt",
        "rfc 8785",
        "merkle tree",
        "cryptographic receipt digest",
        "restored atomically",
        "atomic snapshots",
        "atomic operations",
        "oracle gate",
        "structural score",
        "zero credential leakage",
        "zero context waste",
        "zero-waste precision",
    ]

    def test_banned_terms_not_in_source_or_scripts(self):
        scan_dirs = [ROOT_DIR / "src", ROOT_DIR / "scripts"]
        violations = []

        for s_dir in scan_dirs:
            for py_file in s_dir.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8", errors="ignore").lower()
                for term in self.BANNED_TERMS:
                    if term in content:
                        violations.append(f"{py_file.relative_to(ROOT_DIR)}: contains banned term '{term}'")

        self.assertEqual(violations, [], "Found banned terminology in source/scripts:\n" + "\n".join(violations))

    def test_banned_terms_not_in_documentation_or_drivers(self):
        docs_to_scan = [
            ROOT_DIR / "SKILL.md",
            ROOT_DIR / "CLAUDE.md",
            ROOT_DIR / "GEMINI.md",
            ROOT_DIR / "AGENTS.md",
            ROOT_DIR.parents[1] / "README.md",
            ROOT_DIR.parents[1] / "PRIVACY.md",
            ROOT_DIR.parents[1] / "TERMS.md",
        ]
        # Include all references except terminology.md which explicitly documents retired terms
        ref_dir = ROOT_DIR / "references"
        if ref_dir.exists():
            for md_file in ref_dir.glob("*.md"):
                if md_file.name != "terminology.md":
                    docs_to_scan.append(md_file)

        violations = []
        for doc in docs_to_scan:
            if not doc.exists():
                continue
            content = doc.read_text(encoding="utf-8", errors="ignore").lower()
            for term in self.BANNED_TERMS:
                if term in content:
                    violations.append(f"{doc.relative_to(ROOT_DIR.parents[1])}: contains banned term '{term}'")

        self.assertEqual(violations, [], "Found banned terminology in documentation/drivers:\n" + "\n".join(violations))

    def test_verdict_reject_eliminated(self):
        from seg.models import OracleVerdict
        verdict_values = [v.value for v in OracleVerdict]
        self.assertNotIn("REJECT", verdict_values)
        self.assertEqual(set(verdict_values), {"ACCEPT", "REVISE", "ESCALATE"})

    def test_canonical_enums_defined_and_consumed(self):
        from seg.models import FindingKind, NodeStatus, OracleVerdict, RunStatus, Severity

        self.assertEqual(set(v.value for v in OracleVerdict), {"ACCEPT", "REVISE", "ESCALATE"})
        self.assertEqual(set(k.value for k in FindingKind), {"SPECIFICATION_ERROR", "SEG_RECOMMENDATION", "OBSERVED_FAILURE"})
        self.assertEqual(set(s.value for s in NodeStatus), {"PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED", "TIMED_OUT"})
        self.assertEqual(set(r.value for r in RunStatus), {"COMPLETED", "PREVIEWED", "MUTATED", "ABORTED", "ESCALATED", "FAILED"})
        self.assertEqual(set(x.value for x in Severity), {"ERROR", "WARNING", "INFO"})

    def test_stable_gate_ids_in_oracle_and_models(self):
        from seg.models import GateResult, JoinedEvidence
        from seg.oracle import EvaluatorOracle

        expected_gate_ids = {
            "evaluation_integrity",
            "specification_conformance",
            "safety_privacy",
            "link_integrity",
            "quality_policy",
        }

        # Verify GateResult supports gate_id and display_name
        gr = GateResult(gate_id="evaluation_integrity", display_name="Evaluation Integrity Gate", passed=True)
        self.assertEqual(gr.gate_id, "evaluation_integrity")
        self.assertEqual(gr.display_name, "Evaluation Integrity Gate")
        self.assertEqual(gr.name, "Evaluation Integrity Gate")  # Backward compatibility property

        # Verify Oracle evaluates all 5 canonical gates
        oracle = EvaluatorOracle(target_score=95)
        evidence = JoinedEvidence(
            total_findings=[],
            static_quality_score=100,
            specification_passed=True,
            safety_passed=True,
            privacy_passed=True,
            broken_links=[],
            evaluation_integrity_passed=True,
        )
        decision = oracle.evaluate(evidence)
        evaluated_gate_ids = {g.gate_id for g in decision.gates}
        self.assertEqual(evaluated_gate_ids, expected_gate_ids)


if __name__ == "__main__":
    unittest.main()
