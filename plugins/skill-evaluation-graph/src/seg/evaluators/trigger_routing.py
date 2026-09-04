"""
trigger_routing.py - Evaluates invocation trigger precision, routing boundaries, and SDO.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from seg.evaluators.base import BaseEvaluatorNode, parse_frontmatter
from seg.models import Finding, NodeResult


class TriggerRoutingEvaluatorNode(BaseEvaluatorNode):
    """Evaluates whether the skill description provides clear semantic routing triggers."""

    def __init__(self, node_id: str = "trigger_routing"):
        super().__init__(node_id=node_id, dependencies=["schema"])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []

        skill_md = skill_path / "SKILL.md"
        input_digest = self.compute_input_digest([skill_md])

        if not skill_md.exists():
            return NodeResult(node_id=self.node_id, input_digest=input_digest)

        content = skill_md.read_text(encoding="utf-8-sig", errors="ignore")
        fm_data, _ = parse_frontmatter(content)
        if not fm_data or "description" not in fm_data:
            return NodeResult(node_id=self.node_id, input_digest=input_digest)

        desc = str(fm_data["description"]).strip()
        words = desc.split()
        metrics["word_count"] = len(words)

        has_use_when = bool(re.search(r"\buse\s+when\b", desc, re.IGNORECASE))
        has_negative_boundary = bool(re.search(r"\bdo\s+not\s+use\b|\bavoid\b|\bnot\s+for\b", desc, re.IGNORECASE))

        metrics["has_use_when"] = has_use_when
        metrics["has_negative_boundary"] = has_negative_boundary

        # 1. Check for explicit "Use when"
        if not has_use_when:
            findings.append(
                Finding(
                    severity="WARNING",
                    category="ROUTING",
                    message="Description lacks explicit 'Use when...' trigger condition.",
                    file="SKILL.md",
                    suggestion="Add 'Use when <condition> to <accomplish goal>' to anchor agent activation.",
                    rule_id="ROUTE-001",
                )
            )

        # 2. Check for negative boundary
        if not has_negative_boundary:
            findings.append(
                Finding(
                    severity="INFO",
                    category="ROUTING",
                    message="Description lacks negative boundary (e.g. 'Do not use for...').",
                    file="SKILL.md",
                    suggestion="Define when NOT to trigger to prevent routing collisions.",
                    rule_id="ROUTE-002",
                )
            )

        # 3. Check for discovery bloat (>150 words)
        if len(words) > 150:
            findings.append(
                Finding(
                    severity="WARNING",
                    category="TOKEN_ECONOMY",
                    message=f"Description is {len(words)} words; discovery context cost exceeds recommended 150 words.",
                    file="SKILL.md",
                    suggestion="Compress description triggers under 150 words to conserve system context budget.",
                    rule_id="ROUTE-003",
                )
            )

        # 4. SDO Internal Pipeline Anti-Pattern Check
        workflow_indicators = [
            r"\bdispatches?\s+(?:parallel\s+)?subagents?",
            r"\btwo-stage\s+review\b",
            r"\bfirst\b[\w\s,]+then\b",
            r"\bstep[\s-]*by[\s-]*step\b",
            r"\bphase\s+\d",
            r"\bexecutes?\s+(?:a\s+)?pipeline\b",
        ]
        for pat in workflow_indicators:
            if re.search(pat, desc, re.IGNORECASE):
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="FRONTMATTER",
                        message="Description appears to summarize internal execution workflow (SDO anti-pattern). Agents may follow this shallow summary shortcut instead of reading the full SKILL.md body.",
                        file="SKILL.md",
                        suggestion="Focus description strictly on WHEN to invoke (triggers, symptoms, user requests). Move step-by-step workflow and review rules into the SKILL.md body.",
                        rule_id="ANTI-010",
                    )
                )
                break

        evidence.append({
            "has_use_when": has_use_when,
            "has_negative_boundary": has_negative_boundary,
            "word_count": len(words),
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
