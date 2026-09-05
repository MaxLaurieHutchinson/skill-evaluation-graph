"""
test_repair_safety.py - Tests for repair planning, sandbox isolation, diff generation, and atomic rollback.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seg.models import Finding
from seg.repair.isolator import RepairIsolator
from seg.repair.planner import PatchProposal, plan_repairs


class TestRepairSafetySubsystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skill_dir = Path(self.temp_dir.name) / "repair-test-skill"
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        refs = self.skill_dir / "references"
        refs.mkdir()
        (refs / "valid_target.md").write_text("# Target", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_plan_repairs_from_findings(self):
        findings = [
            Finding("WARNING", "SYNTAX", "UTF-8 BOM detected", file="SKILL.md", rule_id="SYN-001"),
            Finding("ERROR", "SYNTAX", "Unclosed code fence", file="SKILL.md", rule_id="SYN-002"),
            Finding("ERROR", "LINKS", "Broken link '[Target](valid_target.md)'", file="SKILL.md", rule_id="LINK-001"),
            Finding("WARNING", "FRONTMATTER", "Name mismatch", file="SKILL.md", rule_id="SPEC-006"),
        ]

        proposals = plan_repairs(self.skill_dir, findings)
        actions = [p.action for p in proposals]

        self.assertIn("STRIP_BOM", actions)
        self.assertIn("CLOSE_FENCE", actions)
        self.assertIn("FIX_LINK", actions)
        self.assertIn("ALIGN_NAME", actions)

    def test_sandbox_staging_and_diff_generation(self):
        skill_md = self.skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: old-name\ndescription: Test.\n---\n\n```python\nprint(1)\n",
            encoding="utf-8",
        )

        proposals = [
            PatchProposal(
                finding_id="SPEC-006",
                target_file="SKILL.md",
                action="ALIGN_NAME",
                reason="Align name",
                replacement_snippet="repair-test-skill",
            ),
            PatchProposal(
                finding_id="SYN-002",
                target_file="SKILL.md",
                action="CLOSE_FENCE",
                reason="Close code fence",
                replacement_snippet="\n```\n",
            ),
        ]

        isolator = RepairIsolator(self.skill_dir)
        sandbox_path, diff_str = isolator.stage_in_sandbox(proposals)

        try:
            # 1. Target file on disk MUST NOT be changed during staging (Default Read-Only)
            self.assertIn("name: old-name", skill_md.read_text(encoding="utf-8"))

            # 2. Sandbox file must have patches applied
            sandbox_md = sandbox_path / "SKILL.md"
            self.assertIn("name: repair-test-skill", sandbox_md.read_text(encoding="utf-8"))

            # 3. Diff must contain the changes
            self.assertIn("-name: old-name", diff_str)
            self.assertIn("+name: repair-test-skill", diff_str)
            self.assertIn("+```", diff_str)

            # 4. Apply changes atomically with rollback snapshot
            success = isolator.apply_to_target_with_rollback()
            self.assertTrue(success)

            # Now target file on disk should be updated
            healed = skill_md.read_text(encoding="utf-8")
            self.assertIn("name: repair-test-skill", healed)
            self.assertTrue(healed.rstrip().endswith("```"))

        finally:
            isolator.cleanup()

    def test_atomic_rollback_on_failure(self):
        skill_md = self.skill_dir / "SKILL.md"
        original_content = "---\nname: original\ndescription: Test.\n---\n"
        skill_md.write_text(original_content, encoding="utf-8")

        isolator = RepairIsolator(self.skill_dir)
        sandbox_path, _ = isolator.stage_in_sandbox([
            PatchProposal("SPEC-006", "SKILL.md", "ALIGN_NAME", "Align", replacement_snippet="mutated")
        ])

        try:
            # Make sandbox directory simulate an exception during apply
            # by temporarily creating an invalid state or monkeypatching
            import shutil
            orig_copytree = shutil.copytree

            def failing_copytree(*args, **kwargs):
                raise IOError("Simulated disk failure during atomic copy")

            shutil.copytree = failing_copytree
            try:
                success = isolator.apply_to_target_with_rollback()
                self.assertFalse(success)
            finally:
                shutil.copytree = orig_copytree

            # Verify target file was restored to original content via rollback
            self.assertEqual(skill_md.read_text(encoding="utf-8"), original_content)

        finally:
            isolator.cleanup()

    def test_candidate_sandbox_verification_flow(self):
        """
        Verify that staged candidates can be evaluated in sandbox without affecting
        the original skill on disk, ensuring fail-closed verification.
        """
        skill_md = self.skill_dir / "SKILL.md"
        orig_content = "---\nname: bad_name\ndescription: Test.\n---\n"
        skill_md.write_text(orig_content, encoding="utf-8")

        proposal = PatchProposal(
            finding_id="SPEC-006",
            target_file="SKILL.md",
            action="ALIGN_NAME",
            reason="Align name",
            replacement_snippet="repair-test-skill",
        )

        isolator = RepairIsolator(self.skill_dir)
        sandbox_path, diff_str = isolator.stage_in_sandbox([proposal])

        try:
            # 1. Staging creates an isolated sandbox copy with proposed changes
            self.assertTrue(sandbox_path.exists())
            self.assertIn("repair-test-skill", (sandbox_path / "SKILL.md").read_text(encoding="utf-8"))
            # 2. Disk content is unchanged (read-only by default)
            self.assertEqual(skill_md.read_text(encoding="utf-8"), orig_content)

            # 3. If candidate evaluation is rejected, cleanup leaves original untouched
            isolator.cleanup()
            self.assertFalse(sandbox_path.exists())
            self.assertEqual(skill_md.read_text(encoding="utf-8"), orig_content)
        finally:
            if sandbox_path.exists():
                isolator.cleanup()

    def test_candidate_verification_blocks_gate_regression_and_new_errors(self):
        """
        Verify that candidate repairs introducing new errors or regressing mandatory gates
        are strictly rejected during sandbox verification, protecting the target disk.
        """
        from seg.evaluators import build_default_evaluation_dag
        from seg.oracle import synthesize_joined_evidence

        skill_md = self.skill_dir / "SKILL.md"
        orig_content = "---\nname: repair-test-skill\ndescription: Use when testing.\n---\n# Original\n"
        skill_md.write_text(orig_content, encoding="utf-8")

        # Baseline evaluation
        dag = build_default_evaluation_dag()
        base_results = dag.execute(self.skill_dir)
        base_evidence = synthesize_joined_evidence(base_results)
        base_errors = sum(1 for f in base_evidence.total_findings if f.severity == "ERROR")

        # Proposal that introduces an invalid name format error (SPEC-004 ERROR)
        bad_proposal = PatchProposal(
            finding_id="SPEC-006",
            target_file="SKILL.md",
            action="ALIGN_NAME",
            reason="Regressing change",
            replacement_snippet="BAD NAME!",
        )

        isolator = RepairIsolator(self.skill_dir)
        sandbox_path, _ = isolator.stage_in_sandbox([bad_proposal])

        try:
            # Evaluate candidate in sandbox
            cand_results = dag.execute(sandbox_path)
            cand_evidence = synthesize_joined_evidence(cand_results)
            cand_errors = sum(1 for f in cand_evidence.total_findings if f.severity == "ERROR")

            # Candidate must have introduced a new error
            self.assertGreater(cand_errors, base_errors)

            # Gate-regression protection condition
            is_improved = (
                cand_evidence.evaluation_integrity_passed
                and not (base_evidence.specification_passed and not cand_evidence.specification_passed)
                and not (base_evidence.safety_passed and not cand_evidence.safety_passed)
                and not (base_evidence.privacy_passed and not cand_evidence.privacy_passed)
                and (cand_errors <= base_errors)
                and (cand_evidence.structural_score > base_evidence.structural_score)
            )
            self.assertFalse(is_improved)

            # Target disk must remain strictly untouched
            self.assertEqual(skill_md.read_text(encoding="utf-8"), orig_content)
        finally:
            isolator.cleanup()


if __name__ == "__main__":
    unittest.main()
