"""
behaviour_policy.py - Deterministic static analysis of behavioral steering policies and rationalization tables.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from seg.evaluators.base import BaseEvaluatorNode
from seg.models import Finding, NodeResult


class BehaviourPolicyEvaluatorNode(BaseEvaluatorNode):
    """
    Performs deterministic static analysis on skill text to verify whether it encodes
    anti-rationalization tables, red flag checklists, and completion verification invariants.
    """

    def __init__(self, node_id: str = "behaviour_policy"):
        super().__init__(node_id=node_id, dependencies=["schema"])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []

        all_text_files: List[Path] = [skill_path / "SKILL.md"]
        refs_dir = skill_path / "references"
        if refs_dir.exists():
            all_text_files.extend(list(refs_dir.glob("*.md")))

        input_digest = self.compute_input_digest(all_text_files)

        aggregated_text = ""
        for p in all_text_files:
            if p.exists():
                try:
                    aggregated_text += "\n" + p.read_text(encoding="utf-8-sig", errors="ignore")
                except Exception:
                    pass

        # Determine if this is an active discipline-enforcing skill from name and description
        schema_res = context.get("schema")
        name = ""
        description = ""
        if schema_res and schema_res.metrics:
            name = schema_res.metrics.get("name", "")
            description = schema_res.metrics.get("description", "")

        if not name and (skill_path / "SKILL.md").exists():
            from seg.evaluators.base import parse_frontmatter
            fm, _ = parse_frontmatter((skill_path / "SKILL.md").read_text(encoding="utf-8-sig", errors="ignore"))
            if fm:
                name = str(fm.get("name", ""))
                description = str(fm.get("description", ""))

        name_desc = f"{name} {description}".lower()
        is_discipline_skill = bool(
            re.search(r"\b(test-driven|tdd|verification-before|code-review|discipline-enforcing)\b", name_desc)
        )

        has_rationalization_table = bool(
            re.search(r"\|\s*Excuse\s*\|\s*Reality\s*\|", aggregated_text, re.IGNORECASE)
            or re.search(r"\|\s*Rationalization\s*\|\s*Rule\s*\|", aggregated_text, re.IGNORECASE)
        )
        has_red_flags = bool(re.search(r"\bRed\s+Flags?\b", aggregated_text, re.IGNORECASE))
        has_verification_invariants = bool(re.search(r"\bverify\b|\bverification\b|\bvalidate\b", aggregated_text, re.IGNORECASE))

        metrics["is_discipline_skill"] = is_discipline_skill
        metrics["has_rationalization_table"] = has_rationalization_table
        metrics["has_red_flags"] = has_red_flags
        metrics["has_verification_invariants"] = has_verification_invariants

        # Guardrail check for discipline skills (Anti-Pattern 2: The Rationalization Loophole)
        if is_discipline_skill and not has_rationalization_table:
            findings.append(
                Finding(
                    severity="WARNING",
                    category="STEERING",
                    message="Skill encodes discipline/verification rules but lacks an Anti-Rationalization Table (| Excuse | Reality |) (Anti-Pattern 2).",
                    file="SKILL.md",
                    suggestion="Add a table pairing common agent evasions with ironclad reality directives.",
                    rule_id="STEER-001",
                )
            )

        if is_discipline_skill and not has_red_flags:
            findings.append(
                Finding(
                    severity="INFO",
                    category="STEERING",
                    message="Skill lacks an explicit 'Red Flags' checklist.",
                    file="SKILL.md",
                    suggestion="List behavioral red flags that immediately halt execution.",
                    rule_id="STEER-002",
                )
            )

        evidence.append({
            "has_rationalization_table": has_rationalization_table,
            "has_red_flags": has_red_flags,
            "has_verification_invariants": has_verification_invariants,
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
