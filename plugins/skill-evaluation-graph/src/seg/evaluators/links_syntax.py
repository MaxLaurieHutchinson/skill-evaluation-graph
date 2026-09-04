"""
links_syntax.py - Verifies relative markdown links, code fence syntax, UTF-8 BOM, and orphaned files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from seg.evaluators.base import BaseEvaluatorNode
from seg.models import Finding, NodeResult


def extract_markdown_links(content: str) -> List[Tuple[str, str, int]]:
    """
    Extract relative markdown links [label](target), ignoring links inside code blocks.
    Returns list of (label, target, line_num).
    """
    links: List[Tuple[str, str, int]] = []
    in_code_block = False
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for line_num, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        for match in link_pattern.finditer(line):
            label, target = match.group(1), match.group(2).strip()
            # Ignore absolute web URLs, anchors, mailto
            if re.match(r"^(https?://|mailto:|#)", target, re.IGNORECASE):
                continue
            # Strip anchors from relative links (e.g. 'doc.md#section' -> 'doc.md')
            target_file = target.split("#")[0]
            if target_file:
                links.append((label, target_file, line_num))

    return links


class LinksSyntaxEvaluatorNode(BaseEvaluatorNode):
    """Verifies link integrity, fence closure, BOM headers, and orphaned files."""

    def __init__(self, node_id: str = "links_syntax"):
        super().__init__(node_id=node_id, dependencies=[])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []

        all_md_files: List[Path] = list(skill_path.rglob("*.md"))
        input_digest = self.compute_input_digest(all_md_files)

        referenced_local_paths: Set[Path] = set()
        broken_links: List[str] = []

        # Account for manifest-referenced files automatically
        manifest_files = [
            skill_path / ".codex-plugin" / "plugin.json",
            skill_path / ".claude-plugin" / "plugin.json",
            skill_path / "gemini-extension.json",
            skill_path / ".agents" / "plugins" / "marketplace.json",
            skill_path / "hooks" / "hooks.json",
        ]
        for mf in manifest_files:
            if mf.exists():
                try:
                    data = json.loads(mf.read_text(encoding="utf-8-sig", errors="ignore"))
                    if isinstance(data, dict):
                        # contextFileName (gemini)
                        if "contextFileName" in data:
                            referenced_local_paths.add((skill_path / data["contextFileName"]).resolve())
                        # interface assets (codex)
                        if "interface" in data and isinstance(data["interface"], dict):
                            for key in ["composerIcon", "logo"]:
                                if key in data["interface"]:
                                    referenced_local_paths.add((skill_path / data["interface"][key]).resolve())
                        # plugins array (marketplace)
                        if "plugins" in data and isinstance(data["plugins"], list):
                            for p in data["plugins"]:
                                if isinstance(p, dict) and "source" in p and "path" in p["source"]:
                                    referenced_local_paths.add((skill_path / p["source"]["path"]).resolve())
                except Exception:
                    pass

        # 1. Inspect all markdown files for links, fences, and BOMs
        for md_file in all_md_files:
            rel = md_file.relative_to(skill_path)
            if any(part.startswith((".", "__")) for part in rel.parts) or ".audit_receipts" in rel.parts:
                continue

            rel_md_path = str(rel).replace("\\", "/")

            # BOM Check
            raw_bytes = md_file.read_bytes()
            if raw_bytes.startswith(b"\xef\xbb\xbf"):
                findings.append(
                    Finding(
                        severity="WARNING",
                        category="SYNTAX",
                        message=f"UTF-8 BOM detected in '{rel_md_path}'.",
                        file=rel_md_path,
                        suggestion="Save as standard UTF-8 without BOM to avoid parser errors.",
                        rule_id="SYN-001",
                    )
                )

            content = raw_bytes.decode("utf-8", errors="ignore")

            # Code Fence Closure Check
            fence_count = sum(1 for line in content.splitlines() if line.strip().startswith("```"))
            if fence_count % 2 != 0:
                findings.append(
                    Finding(
                        severity="ERROR",
                        category="SYNTAX",
                        message=f"Unclosed code fence in '{rel_md_path}' ({fence_count} fences found).",
                        file=rel_md_path,
                        suggestion="Close all ``` code blocks.",
                        rule_id="SYN-002",
                    )
                )

            # Unresolved Placeholder Detection
            is_template_file = any(part in ("assets", "templates") for part in rel.parts) or "template" in md_file.name.lower()
            if not is_template_file:
                for idx, line in enumerate(content.splitlines(), start=1):
                    clean_line = re.sub(r'`[^`]*`', '', line)
                    if re.search(r"\b(?:TODO|FIXME|TBD)\b", clean_line) and not line.strip().startswith(("#", "<!--")):
                        findings.append(
                            Finding(
                                severity="INFO",
                                category="CONTENT",
                                message=f"Unresolved marker '{line.strip()[:50]}' found.",
                                file=rel_md_path,
                                line=idx,
                                suggestion="Resolve or remove placeholder note before production release.",
                                rule_id="CONTENT-001",
                            )
                        )

            # Link Resolution
            file_links = extract_markdown_links(content)
            for label, target, line_num in file_links:
                target_path = (md_file.parent / target).resolve()
                if not target_path.exists():
                    # Fallback relative to skill root
                    root_relative_path = (skill_path / target).resolve()
                    if root_relative_path.exists():
                        target_path = root_relative_path

                if not target_path.exists():
                    target_stem = Path(target).stem
                    target_name = Path(target).name
                    is_placeholder = bool(
                        re.search(r"^[A-Z_0-9]+$|VIDEO_ID|TIMESTAMP_URL|PATH|URL|^path\.md$|ENTRY_NAME", target_name, re.IGNORECASE)
                    ) or bool(re.match(r"^[A-Z_0-9]+$", target_stem))

                    if is_template_file and is_placeholder:
                        continue

                    broken_links.append(f"{rel_md_path}:{line_num} -> {target}")
                    findings.append(
                        Finding(
                            severity="ERROR",
                            category="LINKS",
                            message=f"Broken link: '[{label}]({target})' - target does not exist.",
                            file=rel_md_path,
                            line=line_num,
                            suggestion=f"Create '{target}' or fix link path.",
                            rule_id="LINK-001",
                        )
                    )
                else:
                    referenced_local_paths.add(target_path)

        # 2. Check for Orphaned Files
        orphaned_files: List[str] = []
        for sub in ["references", "scripts", "assets", "templates"]:
            subpath = skill_path / sub
            if subpath.exists() and subpath.is_dir():
                for p in subpath.rglob("*"):
                    if (
                        p.is_file()
                        and not p.name.startswith((".", "__"))
                        and p.suffix != ".pyc"
                        and "__pycache__" not in p.parts
                    ):
                        if p.resolve() not in referenced_local_paths:
                            if "test" in p.name.lower() or p.name.lower() == "readme.md":
                                continue
                            rel_name = str(p.relative_to(skill_path))
                            orphaned_files.append(rel_name)
                            findings.append(
                                Finding(
                                    severity="INFO",
                                    category="STRUCTURE",
                                    message=f"File '{rel_name}' is not linked or referenced in any markdown file.",
                                    file=rel_name,
                                    suggestion="Reference this file in SKILL.md or delete if unused.",
                                    rule_id="STRUCT-001",
                                )
                            )

        metrics["broken_links_count"] = len(broken_links)
        metrics["orphaned_files_count"] = len(orphaned_files)
        evidence.append({
            "md_file_count": len(all_md_files),
            "broken_links": broken_links,
            "orphaned_files": orphaned_files,
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
