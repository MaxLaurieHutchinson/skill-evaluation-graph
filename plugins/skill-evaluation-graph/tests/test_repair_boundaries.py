"""Repair operations must preserve content and stay inside the selected skill."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import shutil
import contextlib
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_loop import EvaluatorLoopEngine
from seg.repair.isolator import RepairIsolator
from seg.repair.planner import PatchProposal


class TestRepairBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / "sample-skill"
        self.skill.mkdir()
        self.document = self.skill / "SKILL.md"
        self.original = "---\nname: wrong\ndescription: Use when testing.\n---\n# Example\n```yaml\nname: example\n```\n"
        self.document.write_text(self.original, encoding="utf-8")
        self.isolator = RepairIsolator(self.skill)
        self.addCleanup(self.isolator.cleanup)

    def proposal(self, path="SKILL.md"):
        return PatchProposal("SPEC-006", path, "ALIGN_NAME", "Align name", replacement_snippet="sample-skill")

    def test_align_name_preserves_body_examples(self):
        sandbox, _ = self.isolator.stage_in_sandbox([self.proposal()])
        self.assertEqual((sandbox / "SKILL.md").read_text(encoding="utf-8"), self.original.replace("name: wrong", "name: sample-skill", 1))

    def test_absolute_patch_target_is_rejected_without_touching_external_file(self):
        external = self.root / "outside.md"
        external.write_text(self.original, encoding="utf-8")
        with self.assertRaises(ValueError):
            self.isolator.stage_in_sandbox([self.proposal(str(external))])
        self.assertEqual(external.read_text(encoding="utf-8"), self.original)

    def test_parent_traversal_patch_is_rejected(self):
        with self.assertRaises(ValueError):
            self.isolator.stage_in_sandbox([self.proposal("../outside.md")])

    def test_existing_sibling_backup_is_preserved(self):
        backup = self.root / "sample-skill.seg_backup"
        backup.mkdir()
        saved = backup / "valuable.txt"
        saved.write_text("previous recovery data", encoding="utf-8")
        self.isolator.stage_in_sandbox([self.proposal()])
        self.assertTrue(self.isolator.apply_to_target_with_rollback())
        self.assertTrue(saved.exists())
        self.assertEqual(saved.read_text(), "previous recovery data")

    def test_target_edits_after_staging_abort_mutation(self):
        self.isolator.stage_in_sandbox([self.proposal()])
        self.document.write_text("new user content", encoding="utf-8")
        self.assertFalse(self.isolator.apply_to_target_with_rollback())
        self.assertEqual(self.document.read_text(), "new user content")

    def test_replacing_old_errors_with_a_new_error_is_rejected_by_real_loop(self):
        original = "---\nname: sample-skill\ndescription: Use when testing repairs.\n---\n# Test\n[a](a.md) [b](b.md) [c](c.md)\n"
        self.document.write_text(original, encoding="utf-8")
        (self.skill / "valid.md").write_text("# Valid\n", encoding="utf-8")
        proposals = [PatchProposal("LINK-001", "SKILL.md", "FIX_LINK", "Test candidate",
                                   original_snippet=old, replacement_snippet=new)
                     for old, new in (("a.md", "valid.md"), ("b.md", "valid.md"), ("c.md", "new-error.md"))]
        with patch("run_loop.plan_repairs", return_value=proposals), contextlib.redirect_stdout(io.StringIO()):
            receipt = EvaluatorLoopEngine(self.skill, apply_mutations=True, max_iterations=2).run()
        self.assertEqual(self.document.read_text(encoding="utf-8"), original)
        self.assertEqual(receipt["repair_actions"], [])

    def test_symlink_patch_target_is_rejected(self):
        external = self.root / "external.md"
        external.write_text(self.original, encoding="utf-8")
        linked = self.skill / "linked.md"
        try:
            linked.symlink_to(external)
        except OSError:
            self.skipTest("Host does not permit creating symbolic links")
        with self.assertRaises(ValueError):
            self.isolator.stage_in_sandbox([self.proposal("linked.md")])
        self.assertEqual(external.read_text(encoding="utf-8"), self.original)

    def test_partial_apply_failure_restores_already_written_files(self):
        second = self.skill / "second.md"
        second.write_bytes(b"\xef\xbb\xbf# Second\n")
        original_bytes = self.document.read_bytes()
        second_bytes = second.read_bytes()
        sandbox, _ = self.isolator.stage_in_sandbox([
            self.proposal(), PatchProposal("SYN-001", "second.md", "STRIP_BOM", "Remove BOM"),
        ])
        real_copy = shutil.copy2
        written = []

        def fail_second_copy(src, dst, *args, **kwargs):
            if Path(src) == sandbox / "second.md":
                self.assertEqual(written, ["SKILL.md"])
                raise OSError("simulated second write failure")
            result = real_copy(src, dst, *args, **kwargs)
            if Path(src) == sandbox / "SKILL.md":
                written.append("SKILL.md")
            return result

        with patch("seg.repair.isolator.shutil.copy2", side_effect=fail_second_copy):
            self.assertFalse(self.isolator.apply_to_target_with_rollback())
        self.assertEqual(self.document.read_bytes(), original_bytes)
        self.assertEqual(second.read_bytes(), second_bytes)

    def test_failed_rollback_keeps_recovery_snapshot_after_cleanup(self):
        self.isolator.stage_in_sandbox([self.proposal()])
        with patch("seg.repair.isolator.shutil.copy2", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(RuntimeError, "snapshot"):
                self.isolator.apply_to_target_with_rollback()
        backup = self.isolator.backup_path
        self.isolator.cleanup()
        self.assertIsNotNone(backup)
        self.assertTrue(backup.exists())
        self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), self.original)
