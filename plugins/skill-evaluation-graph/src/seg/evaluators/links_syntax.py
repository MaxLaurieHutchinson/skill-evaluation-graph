"""
links_syntax.py - Verifies relative links, syntax, and package resource reachability.
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Set, Tuple

from seg.evaluators.base import BaseEvaluatorNode
from seg.models import Finding, NodeResult


RESOURCE_DIRS = ("references", "scripts", "assets", "templates")


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
            if re.match(r"^(https?://|mailto:|#)", target, re.IGNORECASE):
                continue
            target_file = target.split("#")[0]
            if target_file:
                links.append((label, target_file, line_num))

    return links


def _resource_files(skill_path: Path) -> List[Path]:
    files: List[Path] = []
    for sub in RESOURCE_DIRS:
        subpath = skill_path / sub
        if not subpath.exists() or not subpath.is_dir():
            continue
        for path in subpath.rglob("*"):
            if (
                path.is_file()
                and not path.name.startswith((".", "__"))
                and path.suffix != ".pyc"
                and "__pycache__" not in path.parts
            ):
                files.append(path)
    return files


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_markdown_entrypoint(path: Path, skill_path: Path) -> bool:
    """Treat packaged Markdown outside resource directories as an intentional entrypoint."""
    try:
        rel = path.resolve().relative_to(skill_path.resolve())
    except ValueError:
        return False
    if not rel.parts:
        return False
    if any(part.startswith((".", "__")) for part in rel.parts) or ".audit_receipts" in rel.parts:
        return False
    return rel.parts[0] not in RESOURCE_DIRS


def _resolve_python_module(skill_path: Path, source_file: Path, module: str | None, level: int = 0) -> Path | None:
    """Resolve a local Python import to a bundled source file when possible."""
    module_parts = module.split(".") if module else []

    if level:
        base = source_file.parent
        for _ in range(max(level - 1, 0)):
            base = base.parent
        bases = [base]
    else:
        bases = [source_file.parent, skill_path, skill_path / "scripts"]

    for base in bases:
        module_base = base.joinpath(*module_parts) if module_parts else base
        candidates = [module_base.with_suffix(".py"), module_base / "__init__.py"]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file() and _path_is_within(candidate, skill_path):
                return candidate.resolve()
    return None


def _python_import_edges(skill_path: Path, source_file: Path) -> Iterable[Tuple[Path, int]]:
    """Yield locally resolvable Python import targets and their source lines."""
    try:
        tree = ast.parse(source_file.read_text(encoding="utf-8-sig", errors="ignore"))
    except (OSError, SyntaxError, UnicodeError):
        return []

    edges: List[Tuple[Path, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_python_module(skill_path, source_file, alias.name, 0)
                if target is not None:
                    edges.append((target, getattr(node, "lineno", 0)))
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_python_module(skill_path, source_file, node.module, node.level)
            if target is not None:
                edges.append((target, getattr(node, "lineno", 0)))
    return edges


class LinksSyntaxEvaluatorNode(BaseEvaluatorNode):
    """Verifies link integrity, syntax, and evidence of package resource reachability."""

    def __init__(self, node_id: str = "links_syntax"):
        super().__init__(node_id=node_id, dependencies=[])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []

        all_md_files: List[Path] = list(skill_path.rglob("*.md"))
        resource_files = _resource_files(skill_path)
        resource_by_rel = {
            str(path.relative_to(skill_path)).replace("\\", "/"): path.resolve()
            for path in resource_files
        }

        manifest_files = [
            skill_path / ".codex-plugin" / "plugin.json",
            skill_path / ".claude-plugin" / "plugin.json",
            skill_path / "gemini-extension.json",
            skill_path / ".agents" / "plugins" / "marketplace.json",
            skill_path / "hooks" / "hooks.json",
        ]
        input_files = list(dict.fromkeys(all_md_files + resource_files + [p for p in manifest_files if p.exists()]))
        input_digest = self.compute_input_digest(input_files)

        referenced_local_paths: Set[Path] = set()
        resource_reference_evidence: List[Dict[str, Any]] = []
        markdown_edges: DefaultDict[Path, List[Tuple[Path, str, int]]] = defaultdict(list)
        broken_links: List[str] = []

        def add_reference(target: Path, source: str, relation: str, line: int | None = None) -> None:
            resolved = target.resolve()
            if not _path_is_within(resolved, skill_path):
                return
            referenced_local_paths.add(resolved)
            item: Dict[str, Any] = {
                "source": source,
                "target": str(resolved.relative_to(skill_path.resolve())).replace("\\", "/"),
                "relation": relation,
            }
            if line:
                item["line"] = line
            if item not in resource_reference_evidence:
                resource_reference_evidence.append(item)

        def add_markdown_edge(source: Path, target: Path, relation: str, line: int) -> None:
            edge = (target.resolve(), relation, line)
            if edge not in markdown_edges[source.resolve()]:
                markdown_edges[source.resolve()].append(edge)

        # Account for known manifest-referenced files as direct reachability evidence.
        for mf in manifest_files:
            if not mf.exists():
                continue
            try:
                data = json.loads(mf.read_text(encoding="utf-8-sig", errors="ignore"))
                if not isinstance(data, dict):
                    continue
                source_name = str(mf.relative_to(skill_path)).replace("\\", "/")
                if "contextFileName" in data:
                    add_reference(skill_path / data["contextFileName"], source_name, "manifest_reference")
                if "interface" in data and isinstance(data["interface"], dict):
                    for key in ["composerIcon", "logo"]:
                        if key in data["interface"]:
                            add_reference(skill_path / data["interface"][key], source_name, "manifest_reference")
                if "plugins" in data and isinstance(data["plugins"], list):
                    for plugin in data["plugins"]:
                        if isinstance(plugin, dict) and isinstance(plugin.get("source"), dict) and "path" in plugin["source"]:
                            add_reference(skill_path / plugin["source"]["path"], source_name, "manifest_reference")
            except Exception:
                pass

        # 1. Inspect every Markdown file for syntax/link integrity and record potential
        # resource edges. Reachability is resolved separately from real entrypoints.
        for md_file in all_md_files:
            rel = md_file.relative_to(skill_path)
            if any(part.startswith((".", "__")) for part in rel.parts) or ".audit_receipts" in rel.parts:
                continue

            rel_md_path = str(rel).replace("\\", "/")
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

            file_links = extract_markdown_links(content)
            for label, target, line_num in file_links:
                target_path = (md_file.parent / target).resolve()
                if not target_path.exists():
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
                    add_markdown_edge(md_file, target_path, "markdown_link", line_num)

            # Explicit package-relative paths are potential edges whether expressed as
            # inline code, prose, or a script invocation. They only become reachability
            # evidence when their source Markdown is itself reachable.
            normalized_content = content.replace("\\", "/")
            content_lines = normalized_content.splitlines()
            for rel_resource, target_path in resource_by_rel.items():
                variants = (rel_resource, f"./{rel_resource}")
                for line_num, line in enumerate(content_lines, start=1):
                    if any(variant in line for variant in variants):
                        relation = "script_invocation" if rel_resource.startswith("scripts/") else "inline_path"
                        add_markdown_edge(md_file, target_path, relation, line_num)
                        break

        # 2. Traverse Markdown edges from real package/control-plane entrypoints.
        markdown_queue = deque(path.resolve() for path in all_md_files if _is_markdown_entrypoint(path, skill_path))
        visited_markdown: Set[Path] = set()
        while markdown_queue:
            source_file = markdown_queue.popleft().resolve()
            if source_file in visited_markdown:
                continue
            visited_markdown.add(source_file)
            source_name = str(source_file.relative_to(skill_path.resolve())).replace("\\", "/")
            for target, relation, line_num in markdown_edges.get(source_file, []):
                add_reference(target, source_name, relation, line_num)
                if target.suffix.lower() == ".md" and target not in visited_markdown:
                    markdown_queue.append(target)

        # A manifest can make a Markdown context/resource directly reachable; follow its
        # outgoing edges as well.
        for path in list(referenced_local_paths):
            if path.suffix.lower() == ".md" and path not in visited_markdown:
                markdown_queue.append(path)
        while markdown_queue:
            source_file = markdown_queue.popleft().resolve()
            if source_file in visited_markdown:
                continue
            visited_markdown.add(source_file)
            source_name = str(source_file.relative_to(skill_path.resolve())).replace("\\", "/")
            for target, relation, line_num in markdown_edges.get(source_file, []):
                add_reference(target, source_name, relation, line_num)
                if target.suffix.lower() == ".md" and target not in visited_markdown:
                    markdown_queue.append(target)

        # 3. Follow local Python imports transitively, but only from scripts for which
        # reachability has already been established by reachable instructions/manifests.
        script_queue = deque(
            path for path in referenced_local_paths
            if path.suffix == ".py" and _path_is_within(path, skill_path / "scripts")
        )
        visited_scripts: Set[Path] = set()
        while script_queue:
            source_file = script_queue.popleft().resolve()
            if source_file in visited_scripts:
                continue
            visited_scripts.add(source_file)
            source_name = str(source_file.relative_to(skill_path.resolve())).replace("\\", "/")
            for target, line_num in _python_import_edges(skill_path, source_file):
                was_new = target not in referenced_local_paths
                add_reference(target, source_name, "python_import", line_num)
                if was_new and target.suffix == ".py" and _path_is_within(target, skill_path / "scripts"):
                    script_queue.append(target)

        # 4. Report resources for which SEG could not establish reachability.
        unresolved_resources: List[str] = []
        for path in resource_files:
            if path.resolve() in referenced_local_paths:
                continue
            if "test" in path.name.lower() or path.name.lower() == "readme.md":
                continue
            rel_name = str(path.relative_to(skill_path)).replace("\\", "/")
            unresolved_resources.append(rel_name)
            findings.append(
                Finding(
                    severity="INFO",
                    category="STRUCTURE",
                    message=f"SEG could not establish a resource reference to '{rel_name}'.",
                    file=rel_name,
                    suggestion="Confirm this resource is intentionally reachable from skill instructions, manifests, or another referenced resource; remove it only if it is genuinely unused.",
                    rule_id="STRUCT-001",
                )
            )

        metrics["broken_links_count"] = len(broken_links)
        metrics["orphaned_files_count"] = len(unresolved_resources)
        metrics["resource_reference_count"] = len(resource_reference_evidence)
        evidence.append({
            "md_file_count": len(all_md_files),
            "broken_links": broken_links,
            "orphaned_files": unresolved_resources,
            "resource_references": resource_reference_evidence,
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
