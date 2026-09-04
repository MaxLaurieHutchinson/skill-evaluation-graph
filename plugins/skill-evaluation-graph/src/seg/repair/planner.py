"""
planner.py - Evidence-driven patch proposal generator for SEG autonomous repair loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from seg.models import Finding


@dataclass
class PatchProposal:
    finding_id: str
    target_file: str
    action: str  # "STRIP_BOM", "CLOSE_FENCE", "FIX_LINK", "CREATE_DIR"
    reason: str
    original_snippet: str = ""
    replacement_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "target_file": self.target_file,
            "action": self.action,
            "reason": self.reason,
            "original_snippet": self.original_snippet,
            "replacement_snippet": self.replacement_snippet,
        }


def plan_repairs(skill_path: Path, findings: List[Finding]) -> List[PatchProposal]:
    """
    Examine findings and generate bounded, deterministic repair proposals.
    Only proposes repairs for safe, verifiable structural issues.
    """
    proposals: List[PatchProposal] = []

    for f in findings:
        # 1. UTF-8 BOM Removal
        if f.rule_id == "SYN-001" and f.file:
            proposals.append(
                PatchProposal(
                    finding_id="SYN-001",
                    target_file=f.file,
                    action="STRIP_BOM",
                    reason="Remove UTF-8 Byte Order Mark header to ensure portable parsing.",
                )
            )

        # 2. Unclosed Code Fence
        elif f.rule_id == "SYN-002" and f.file:
            proposals.append(
                PatchProposal(
                    finding_id="SYN-002",
                    target_file=f.file,
                    action="CLOSE_FENCE",
                    reason="Append missing triple backticks to close orphaned code block.",
                    replacement_snippet="\n```\n",
                )
            )

        # 3. Broken Relative Links (if target exists in references/ or assets/)
        elif f.rule_id == "LINK-001" and f.file:
            match = re_search_link_target(f.message)
            if match:
                missing_target = match
                # Check if target exists in references or assets
                candidate_paths = [
                    Path("references") / Path(missing_target).name,
                    Path("assets") / Path(missing_target).name,
                ]
                for cand in candidate_paths:
                    if (skill_path / cand).exists():
                        proposals.append(
                            PatchProposal(
                                finding_id="LINK-001",
                                target_file=f.file,
                                action="FIX_LINK",
                                reason=f"Update link target from '{missing_target}' to existing '{cand}'.",
                                original_snippet=missing_target,
                                replacement_snippet=str(cand).replace("\\", "/"),
                            )
                        )
                        break

        # 4. Frontmatter Name Alignment
        elif f.rule_id == "SPEC-006" and f.file:
            proposals.append(
                PatchProposal(
                    finding_id="SPEC-006",
                    target_file=f.file,
                    action="ALIGN_NAME",
                    reason=f"Align frontmatter name with directory name '{skill_path.name}'.",
                    replacement_snippet=skill_path.name,
                )
            )

    return proposals


def re_search_link_target(msg: str) -> Optional[str]:
    """Extract link target from finding message '[label](target)'."""
    import re
    m = re.search(r"'\s*\[.*?\]\((.*?)\)\s*'", msg)
    return m.group(1) if m else None
