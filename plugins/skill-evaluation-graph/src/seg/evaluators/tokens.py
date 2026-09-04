"""
tokens.py - Multi-tier token economics and context budget analyzer for SEG.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from seg.evaluators.base import BaseEvaluatorNode, estimate_tokens, parse_frontmatter
from seg.models import FileProfile, Finding, NodeResult


class TokensEvaluatorNode(BaseEvaluatorNode):
    """Profiles token footprints across the 5-tier progressive disclosure hierarchy."""

    def __init__(self, node_id: str = "token_economics"):
        super().__init__(node_id=node_id, dependencies=["schema"])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []
        file_profiles: List[FileProfile] = []

        skill_md = skill_path / "SKILL.md"
        all_skill_files: List[Path] = [skill_md] if skill_md.exists() else []

        for sub in ["references", "scripts", "assets", "templates"]:
            subpath = skill_path / sub
            if subpath.exists() and subpath.is_dir():
                for p in subpath.rglob("*"):
                    if p.is_file() and not p.name.startswith((".", "__")) and p.suffix != ".pyc":
                        all_skill_files.append(p)

        input_digest = self.compute_input_digest(all_skill_files)

        tier_tokens: Dict[str, int] = {
            "Tier 1 (Metadata)": 0,
            "Tier 2 (Base Orchestrator)": 0,
            "Tier 3 (On-Demand References)": 0,
            "Tier 4 (Deterministic Tools)": 0,
            "Tier 5 (Templates & Assets)": 0,
        }

        # 1. Profile SKILL.md (Tier 1 + Tier 2)
        if skill_md.exists():
            content = skill_md.read_text(encoding="utf-8-sig", errors="ignore")
            lines = content.splitlines()
            words = content.split()
            tokens = estimate_tokens(content)

            fm_data, body = parse_frontmatter(content)
            fm_text = content[: len(content) - len(body)] if fm_data else ""
            t1_tokens = estimate_tokens(fm_text) if fm_text else 50
            t2_tokens = max(0, tokens - t1_tokens)

            tier_tokens["Tier 1 (Metadata)"] += t1_tokens
            tier_tokens["Tier 2 (Base Orchestrator)"] += t2_tokens

            file_profiles.append(
                FileProfile(
                    path="SKILL.md",
                    tier="Tier 2 (Base Orchestrator)",
                    lines=len(lines),
                    words=len(words),
                    tokens=tokens,
                )
            )

            metrics["skill_md_lines"] = len(lines)
            metrics["skill_md_tokens"] = tokens

            if len(lines) > 300:
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="TOKEN_ECONOMY",
                        message=f"SKILL.md is {len(lines)} lines; exceeds recommended 300 lines (Anti-Pattern 1: Monolithic Orchestrator).",
                        file="SKILL.md",
                        suggestion="Refactor specialized procedures into 'references/' and link them.",
                        rule_id="TOKEN-001",
                    )
                )

            if tokens > 2500:
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="TOKEN_ECONOMY",
                        message=f"SKILL.md estimated at {tokens} tokens; exceeds 2,500 token budget for Tier 2.",
                        file="SKILL.md",
                        suggestion="Move domain references to 'references/' to keep orchestrator lean.",
                        rule_id="TOKEN-002",
                    )
                )

        # 2. Profile Subdirectories
        for p in all_skill_files:
            if p == skill_md:
                continue
            rel_str = str(p.relative_to(skill_path))
            try:
                text = p.read_text(encoding="utf-8-sig", errors="ignore")
                lines = len(text.splitlines())
                words = len(text.split())
                toks = estimate_tokens(text)
            except Exception:
                lines, words, toks = 0, 0, 0

            tier = "Tier 5 (Templates & Assets)"
            if p.parts[len(skill_path.parts):][0] == "references":
                tier = "Tier 3 (On-Demand References)"
                tier_tokens[tier] += toks
            elif p.parts[len(skill_path.parts):][0] == "scripts":
                tier = "Tier 4 (Deterministic Tools)"
                tier_tokens[tier] += toks
            else:
                tier_tokens[tier] += toks

            file_profiles.append(FileProfile(path=rel_str, tier=tier, lines=lines, words=words, tokens=toks))

        total_tokens = sum(tier_tokens.values())
        metrics["total_tokens"] = total_tokens
        metrics["tier_tokens"] = tier_tokens
        evidence.append({
            "total_files": len(file_profiles),
            "tier_breakdown": tier_tokens,
            "profiles": [fp.to_dict() for fp in file_profiles],
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
