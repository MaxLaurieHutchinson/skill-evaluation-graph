"""
isolator.py - Isolated repair staging, diff generation, and rollback protection.
"""

from __future__ import annotations

import difflib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from seg.repair.planner import PatchProposal
from seg.receipts import compute_tree_digest


class RepairIsolator:
    """
    Safely tests and stages repair patches inside a temporary sandbox directory,
    generates unified diffs, and provides rollback-protected mutation.
    """

    def __init__(self, skill_path: Path):
        self.skill_path = skill_path.resolve()
        self.sandbox_path: Optional[Path] = None
        self.backup_path: Optional[Path] = None
        self._input_digest: Optional[str] = None
        self._changed_files: List[Path] = []
        self._preserve_backup = False

    @staticmethod
    def _bounded_file(root: Path, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or path.drive or ".." in path.parts:
            raise ValueError(f"Repair path must stay inside the skill: {relative}")
        target = root / path
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Repair path escapes the skill: {relative}")
        for part in (target, *target.parents):
            if part == root:
                break
            if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                raise ValueError(f"Repair path traverses a link: {relative}")
        return target

    def stage_in_sandbox(self, proposals: List[PatchProposal]) -> Tuple[Path, str]:
        """
        Copy skill into an isolated temporary workspace, apply proposed patches,
        and generate a unified diff comparing original against sandbox.
        """
        for proposal in proposals:
            self._bounded_file(self.skill_path, proposal.target_file)
        for item in self.skill_path.rglob("*"):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise ValueError("Repair staging does not support symbolic links or junctions")
        self._input_digest = compute_tree_digest(self.skill_path)
        self._changed_files = []
        temp_dir = Path(tempfile.mkdtemp(prefix="seg_repair_sandbox_"))
        self.sandbox_path = temp_dir / self.skill_path.name
        shutil.copytree(
            self.skill_path,
            self.sandbox_path,
            ignore=shutil.ignore_patterns(".git", ".audit_receipts", ".seg_backup", "__pycache__"),
        )

        # Apply patches inside sandbox
        for p in proposals:
            target_file = self._bounded_file(self.sandbox_path, p.target_file)
            if not target_file.exists():
                continue

            if p.action == "STRIP_BOM":
                raw = target_file.read_bytes()
                if raw.startswith(b"\xef\xbb\xbf"):
                    target_file.write_bytes(raw[3:])

            elif p.action == "CLOSE_FENCE":
                text = target_file.read_text(encoding="utf-8-sig", errors="ignore")
                text += p.replacement_snippet
                target_file.write_text(text, encoding="utf-8")

            elif p.action == "FIX_LINK":
                text = target_file.read_text(encoding="utf-8-sig", errors="ignore")
                if p.original_snippet and p.replacement_snippet:
                    text = text.replace(f"({p.original_snippet})", f"({p.replacement_snippet})")
                    target_file.write_text(text, encoding="utf-8")

            elif p.action == "ALIGN_NAME":
                text = target_file.read_text(encoding="utf-8-sig", errors="ignore")
                frontmatter = re.match(r"\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|\Z)", text, re.MULTILINE | re.DOTALL)
                if frontmatter is None:
                    continue
                header = re.sub(r"^name:[ \t]*.*$", lambda _: f"name: {p.replacement_snippet}", frontmatter.group(1), count=1, flags=re.MULTILINE)
                text = text[:frontmatter.start(1)] + header + text[frontmatter.end(1):]
                target_file.write_text(text, encoding="utf-8")

        # Generate unified diff
        diff_lines: List[str] = []
        for relative in sorted({p.target_file for p in proposals}):
            orig_file = self._bounded_file(self.skill_path, relative)
            if orig_file.is_file():
                rel = orig_file.relative_to(self.skill_path)
                if orig_file.suffix != ".pyc":
                    sand_file = self.sandbox_path / rel
                    if sand_file.exists():
                        if orig_file.read_bytes() != sand_file.read_bytes():
                            self._changed_files.append(rel)
                        orig_text = orig_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                        sand_text = sand_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                        diff = list(
                            difflib.unified_diff(
                                orig_text,
                                sand_text,
                                fromfile=f"a/{rel}",
                                tofile=f"b/{rel}",
                                lineterm="",
                            )
                        )
                        if diff:
                            diff_lines.extend(diff)

        diff_str = "\n".join(diff_lines)
        return self.sandbox_path, diff_str

    def apply_to_target_with_rollback(self) -> bool:
        """
        Copy verified changes from sandbox to target with a rollback-protected snapshot.
        If an exception occurs, automatically restores from snapshot.
        """
        if not self.sandbox_path or not self.sandbox_path.exists() or not self._changed_files:
            return False
        if compute_tree_digest(self.skill_path) != self._input_digest:
            return False
        for relative in self._changed_files:
            self._bounded_file(self.skill_path, str(relative))
            self._bounded_file(self.sandbox_path, str(relative))
        backup_root = Path(tempfile.mkdtemp(prefix=f"{self.skill_path.name}.seg_backup-", dir=self.skill_path.parent))
        self.backup_path = backup_root / self.skill_path.name
        try:
            # 1. Create snapshot backup
            shutil.copytree(
                self.skill_path,
                self.backup_path,
                ignore=shutil.ignore_patterns(".git", ".audit_receipts", "__pycache__"),
            )

        except Exception:
            # No target writes have happened if creating the snapshot failed.
            shutil.rmtree(backup_root, ignore_errors=True)
            return False
        attempted: List[Path] = []
        try:
            for relative in self._changed_files:
                attempted.append(relative)
                shutil.copy2(self.sandbox_path / relative, self.skill_path / relative)
        except Exception:
            try:
                for relative in attempted:
                    shutil.copy2(self.backup_path / relative, self.skill_path / relative)
            except Exception as exc:
                self._preserve_backup = True
                raise RuntimeError(f"Repair rollback failed; recovery snapshot retained at {self.backup_path}") from exc
            shutil.rmtree(backup_root, ignore_errors=True)
            return False
        shutil.rmtree(backup_root, ignore_errors=True)
        return True

    def cleanup(self) -> None:
        """Clean up temporary sandbox and backup resources."""
        if self.sandbox_path and self.sandbox_path.parent.exists():
            shutil.rmtree(self.sandbox_path.parent, ignore_errors=True)
        if self.backup_path and self.backup_path.parent.exists() and not self._preserve_backup:
            shutil.rmtree(self.backup_path.parent, ignore_errors=True)
