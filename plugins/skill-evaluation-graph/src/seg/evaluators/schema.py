"""
schema.py - Frontmatter, naming conventions, and structural specification validator for SEG.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from seg.evaluators.base import BaseEvaluatorNode, parse_frontmatter
from seg.models import Finding, FindingKind, NodeResult

SPEC_AUTHORITY = "Agent Skills Specification"
SPEC_SOURCE_URL = "https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx"


class SchemaEvaluatorNode(BaseEvaluatorNode):
    """Validates core Agent Skills specification compliance and directory conventions."""

    def __init__(
        self,
        node_id: str = "schema",
        allowed_name_aliases: Optional[Set[str]] = None,
    ):
        super().__init__(node_id=node_id, dependencies=[])
        self.allowed_name_aliases: Optional[Set[str]] = set(allowed_name_aliases) if allowed_name_aliases else None

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []

        skill_md = skill_path / "SKILL.md"
        input_digest = self.compute_input_digest([skill_md])

        if not skill_md.exists():
            findings.append(
                Finding(
                    severity="ERROR",
                    category="STRUCTURE",
                    message="Mandatory 'SKILL.md' not found in skill root directory.",
                    file="SKILL.md",
                    suggestion="Create a valid SKILL.md file with YAML frontmatter.",
                    rule_id="SPEC-001",
                    kind=FindingKind.SPECIFICATION_ERROR,
                    authority=SPEC_AUTHORITY,
                    source_url=SPEC_SOURCE_URL,
                )
            )
            return NodeResult(node_id=self.node_id, findings=findings, input_digest=input_digest)

        content = skill_md.read_text(encoding="utf-8-sig", errors="ignore")
        fm_data, body = parse_frontmatter(content)

        if fm_data is None:
            findings.append(
                Finding(
                    severity="ERROR",
                    category="FRONTMATTER",
                    message="Missing or unparseable YAML frontmatter in SKILL.md.",
                    file="SKILL.md",
                    suggestion="Ensure SKILL.md begins and ends frontmatter with '---'.",
                    rule_id="SPEC-002",
                    kind=FindingKind.SPECIFICATION_ERROR,
                    authority=SPEC_AUTHORITY,
                    source_url=SPEC_SOURCE_URL,
                )
            )
            return NodeResult(node_id=self.node_id, findings=findings, input_digest=input_digest)

        name = fm_data.get("name")
        description = fm_data.get("description")

        # 1. Validate 'name'
        if not name or not isinstance(name, str):
            findings.append(
                Finding(
                    severity="ERROR",
                    category="FRONTMATTER",
                    message="Frontmatter missing mandatory 'name' field.",
                    file="SKILL.md",
                    suggestion="Add a lowercase hyphenated name field.",
                    rule_id="SPEC-003",
                    kind=FindingKind.SPECIFICATION_ERROR,
                    authority=SPEC_AUTHORITY,
                    source_url=SPEC_SOURCE_URL,
                )
            )
        else:
            name_clean = name.strip()
            metrics["name"] = name_clean
            if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name_clean):
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Name '{name_clean}' must be lowercase alphanumeric with hyphens.",
                        file="SKILL.md",
                        suggestion="Rename to lowercase hyphenated format (e.g. 'my-skill-name').",
                        rule_id="SPEC-004",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )

            if len(name_clean) > 64:
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Name exceeds 64 characters ({len(name_clean)} chars). Maximum allowed is 64.",
                        file="SKILL.md",
                        suggestion="Keep name concise (<=64 chars).",
                        rule_id="SPEC-005",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )

            # Directory match check: specification requires skill name to match directory name.
            # Development or test aliases require explicit configuration via allowed_name_aliases.
            dir_name = skill_path.name
            matches_dir = (name_clean == dir_name) or (self.allowed_name_aliases and name_clean in self.allowed_name_aliases)
            if not matches_dir:
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Frontmatter name '{name_clean}' does not match directory name '{dir_name}'.",
                        file="SKILL.md",
                        suggestion=f"Rename directory or update name to '{dir_name}'.",
                        rule_id="SPEC-006",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )

        # 2. Validate 'description'
        if not description or not isinstance(description, str):
            findings.append(
                Finding(
                    severity="ERROR",
                    category="FRONTMATTER",
                    message="Frontmatter missing mandatory 'description' field.",
                    file="SKILL.md",
                    suggestion="Add a description describing when and what the skill does.",
                    rule_id="SPEC-007",
                    kind=FindingKind.SPECIFICATION_ERROR,
                    authority=SPEC_AUTHORITY,
                    source_url=SPEC_SOURCE_URL,
                )
            )
        else:
            desc_clean = description.strip()
            metrics["description"] = desc_clean
            metrics["description_chars"] = len(desc_clean)
            metrics["description_words"] = len(desc_clean.split())
            if len(desc_clean) > 1024:
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Description exceeds 1024 characters ({len(desc_clean)} chars). Maximum allowed is 1024.",
                        file="SKILL.md",
                        suggestion="Keep description concise (<=1024 chars).",
                        rule_id="SPEC-008",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )

        # 3. Validate optional 'compatibility' (max 500 characters string)
        if "compatibility" in fm_data:
            compat = fm_data["compatibility"]
            if not isinstance(compat, str):
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Field 'compatibility' must be a string, got {type(compat).__name__}.",
                        file="SKILL.md",
                        suggestion="Ensure compatibility is a string (e.g. 'Requires git >= 2.30').",
                        rule_id="SPEC-009",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )
            elif len(compat.strip()) > 500:
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Field 'compatibility' exceeds 500 characters ({len(compat.strip())} chars). Maximum allowed is 500.",
                        file="SKILL.md",
                        suggestion="Keep compatibility notice concise (<=500 chars).",
                        rule_id="SPEC-009",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )
            else:
                metrics["compatibility"] = compat.strip()

        # 4. Validate optional 'metadata' (string-to-string mapping)
        if "metadata" in fm_data:
            meta = fm_data["metadata"]
            if not isinstance(meta, dict):
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Field 'metadata' must be a string-to-string key-value mapping, got {type(meta).__name__}.",
                        file="SKILL.md",
                        suggestion="Format metadata as a YAML mapping of string keys to string values.",
                        rule_id="SPEC-010",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )
            else:
                invalid_entries = [
                    f"'{k}': {type(v).__name__}" for k, v in meta.items()
                    if not isinstance(k, str) or not isinstance(v, str)
                ]
                if invalid_entries:
                    findings.append(
                        Finding(
                            severity="ERROR",
                            category="FRONTMATTER",
                            message=f"Field 'metadata' must contain only string keys and string values. Invalid entries: {', '.join(invalid_entries)}.",
                            file="SKILL.md",
                            suggestion="Ensure all keys and values in metadata are strings.",
                            rule_id="SPEC-010",
                            kind=FindingKind.SPECIFICATION_ERROR,
                            authority=SPEC_AUTHORITY,
                            source_url=SPEC_SOURCE_URL,
                        )
                    )
                else:
                    metrics["metadata"] = meta

        # 5. Validate optional 'allowed-tools' (string)
        if "allowed-tools" in fm_data:
            tools = fm_data["allowed-tools"]
            if not isinstance(tools, str):
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="FRONTMATTER",
                        message=f"Field 'allowed-tools' must be a string, got {type(tools).__name__}.",
                        file="SKILL.md",
                        suggestion="Provide allowed-tools as a space-delimited string (e.g. 'Bash ReadFile').",
                        rule_id="SPEC-011",
                        kind=FindingKind.SPECIFICATION_ERROR,
                        authority=SPEC_AUTHORITY,
                        source_url=SPEC_SOURCE_URL,
                    )
                )
            else:
                metrics["allowed-tools"] = tools.strip()

        # 6. Unstandardized Directory Check (Anti-Pattern 13) - SEG Recommendation
        docs_dir = skill_path / "docs"
        if docs_dir.exists() and docs_dir.is_dir():
            findings.append(
                Finding(
                    severity="WARNING",
                    category="STRUCTURE",
                    message="Unstandardized 'docs/' directory detected (Anti-Pattern 13). Use 'references/' for on-demand knowledge and 'scripts/' for deterministic tools.",
                    file="docs/",
                    suggestion="Move agent manuals to 'references/' and human manuals to README.md.",
                    rule_id="ANTI-013",
                    kind=FindingKind.SEG_RECOMMENDATION,
                    authority="SEG Context Tier Architecture",
                )
            )

        metrics["is_valid_spec"] = not any(f.severity == "ERROR" for f in findings)
        evidence.append({
            "name": name,
            "description_words": metrics.get("description_words", 0),
            "frontmatter_valid": fm_data is not None,
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
