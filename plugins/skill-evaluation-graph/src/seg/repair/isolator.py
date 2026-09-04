"""
isolator.py - Isolated workspace sandbox execution, diff generation, and atomic rollback for SEG.
"""

from __future__ import annotations

import difflib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from seg.repair.planner import PatchProposal


class RepairIsolator:
    """
    Safely tests and stages repair patches inside a temporary sandbox directory,
    generates unified diffs, and provides atomic rollback capability.
    """

    def __init__(self, skill_path: Path):
        self.skill_path = skill_path.resolve()
        self.sandbox_path: Optional[Path] = None
        self.backup_path: Optional[Path] = None

    def stage_in_sandbox(self, proposals: List[PatchProposal]) -> Tuple[Path, str]:
        """
        Copy skill into an isolated temporary workspace, apply proposed patches,
        and generate a unified diff comparing original against sandbox.
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="seg_repair_sandbox_"))
        self.sandbox_path = temp_dir / self.skill_path.name
        shutil.copytree(
            self.skill_path,
            self.sandbox_path,
            ignore=shutil.ignore_patterns(".git", ".audit_receipts", ".seg_backup", "__pycache__"),
        )

        # Apply patches inside sandbox
        for p in proposals:
            target_file = self.sandbox_path / p.target_file
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
                text = re.sub(r"^name:\s*.*$", f"name: {p.replacement_snippet}", text, flags=re.MULTILINE)
                target_file.write_text(text, encoding="utf-8")

        # Generate unified diff
        diff_lines: List[str] = []
        for orig_file in sorted(self.skill_path.rglob("*")):
            if orig_file.is_file():
                rel = orig_file.relative_to(self.skill_path)
                if (
                    not any(part.startswith((".", "__")) for part in rel.parts)
                    and ".audit_receipts" not in rel.parts
                    and orig_file.suffix != ".pyc"
                ):
                    sand_file = self.sandbox_path / rel
                    if sand_file.exists():
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
        if not self.sandbox_path or not self.sandbox_path.exists():
            return False

        self.backup_path = self.skill_path.parent / f"{self.skill_path.name}.seg_backup"
        if self.backup_path.exists():
            shutil.rmtree(self.backup_path, ignore_errors=True)

        try:
            # 1. Create snapshot backup
            shutil.copytree(
                self.skill_path,
                self.backup_path,
                ignore=shutil.ignore_patterns(".git", ".audit_receipts", "__pycache__"),
            )

            # 2. Copy sandbox over target
            for item in self.sandbox_path.iterdir():
                dest = self.skill_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            # Success: clean up backup snapshot
            shutil.rmtree(self.backup_path, ignore_errors=True)
            return True

        except Exception:
            # Rollback: restore from backup snapshot
            if self.backup_path and self.backup_path.exists():
                for item in self.backup_path.iterdir():
                    dest = self.skill_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
                shutil.rmtree(self.backup_path, ignore_errors=True)
            return False

    def cleanup(self) -> None:
        """Clean up temporary sandbox and backup resources."""
        if self.sandbox_path and self.sandbox_path.parent.exists():
            shutil.rmtree(self.sandbox_path.parent, ignore_errors=True)
        if self.backup_path and self.backup_path.exists():
            shutil.rmtree(self.backup_path, ignore_errors=True)
