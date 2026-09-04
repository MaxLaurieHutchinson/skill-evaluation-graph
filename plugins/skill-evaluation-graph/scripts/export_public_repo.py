#!/usr/bin/env python3
"""
export_public_repo.py - Compiles the development workshop repository into the
canonical OpenAI-compatible public release topology.

Topology:
<out_dir>/
├── .agents/
│   └── plugins/
│       └── marketplace.json      (source: local, path: ./plugins/skill-evaluation-graph)
├── .github/
│   └── workflows/
│       └── architecture.yml      (reproducible Archify evidence validation)
├── plugins/
│   └── skill-evaluation-graph/   (contains .codex-plugin/plugin.json + full skill package)
├── docs/                         (public architecture guide + reproducible Archify source)
├── README.md
├── LICENSE
├── PRIVACY.md
└── TERMS.md

Usage:
    python scripts/export_public_repo.py [--output <path>] [--validate]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List

# Ensure utf-8 stdout in Windows environments
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).parent.parent.resolve()
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
SCRIPT_DIR = ROOT_DIR / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from seg.evaluators.portability import PortabilityEvaluatorNode
from audit_skill import audit_skill


MARKETPLACE_SPEC: Dict[str, Any] = {
    "plugins": [
        {
            "name": "skill-evaluation-graph",
            "source": {
                "source": "local",
                "path": "./plugins/skill-evaluation-graph",
            },
            "category": "Developer Tools",
            "description": "Graph-based auditor and behavioral evaluator for Agent Skills across Claude Code, Antigravity, and OpenAI Codex.",
            "policy": {
                "installation": "AVAILABLE",
                "authentication": "ON_USE",
            },
        }
    ]
}

PUBLIC_PLUGIN_DIR = "plugins/skill-evaluation-graph"
PUBLIC_PLUGIN_PREFIX = f"{PUBLIC_PLUGIN_DIR}/"
PUBLIC_REPO_URL = "https://github.com/MaxLaurieHutchinson/skill-evaluation-graph"


def should_ignore(path: Path) -> bool:
    for part in path.parts:
        if part in ["__pycache__", ".pytest_cache", ".git", ".audit_receipts", ".seg_backup"]:
            return True
        if part.endswith(".pyc") or part.endswith(".pyo"):
            return True
    return False


def copy_tree_filtered(src: Path, dst: Path) -> None:
    """Recursively copy directory tree excluding temporary and build artifacts."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if should_ignore(item):
            continue
        target = dst / item.name
        if item.is_dir():
            copy_tree_filtered(item, target)
        else:
            shutil.copy2(item, target)


def adapt_architecture_source_for_public_repo(spec_path: Path) -> None:
    """Rewrite workshop-relative Archify source paths for the nested public plugin."""
    if not spec_path.exists():
        return

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec.get("meta", {}).pop("repository", None)
    for component in spec.get("components", []):
        for source in component.get("sources", []):
            path = source.get("path")
            if path and not path.startswith(PUBLIC_PLUGIN_PREFIX):
                source["path"] = f"{PUBLIC_PLUGIN_PREFIX}{path}"

    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")


def _prefix_inline_code_paths(text: str) -> str:
    """Retarget inline workshop code paths to the nested public plugin package."""
    for prefix in ("src/", "scripts/", "references/"):
        text = text.replace(f"`{prefix}", f"`{PUBLIC_PLUGIN_PREFIX}{prefix}")
    return text


def adapt_public_document_links(output_dir: Path) -> None:
    """Project workshop-facing docs onto the clean public repository topology."""
    readme_path = output_dir / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8")

        # Navigation/assets live inside the nested plugin package in the public tree.
        readme = readme.replace('src="assets/', f'src="{PUBLIC_PLUGIN_PREFIX}assets/')
        readme = readme.replace('(references/', f'({PUBLIC_PLUGIN_PREFIX}references/')
        readme = _prefix_inline_code_paths(readme)

        # Executable examples must call the nested public plugin scripts.
        readme = readme.replace("python scripts/", f"python {PUBLIC_PLUGIN_PREFIX}scripts/")
        readme = readme.replace(
            f"python {PUBLIC_PLUGIN_PREFIX}scripts/audit_skill.py . --verbose",
            f"python {PUBLIC_PLUGIN_PREFIX}scripts/audit_skill.py {PUBLIC_PLUGIN_DIR} --verbose",
        )

        # The clean public repo intentionally omits workshop-only modular tests and the
        # release compiler workflow. Keep only commands that are actually runnable there.
        readme = readme.replace("python -m unittest discover -s tests\n", "")
        readme = readme.replace(
            "python -m unittest discover -s scripts\n",
            f"python -m unittest discover -s {PUBLIC_PLUGIN_PREFIX}scripts\n",
        )
        readme = readme.replace(
            f"python {PUBLIC_PLUGIN_PREFIX}scripts/export_public_repo.py --output dist/public_release --validate\n",
            "",
        )

        workshop_ci = (
            "CI executes both test suites, self-audits the workshop, builds the clean public tree, "
            "and validates the exported package. A separate architecture-evidence workflow validates "
            "the committed Archify source and regenerates its interactive/browser evidence artifact."
        )
        public_ci = (
            "The workshop release pipeline runs the full unit/self-audit/export validation before publication. "
            "This public repository retains the architecture-evidence workflow, which validates the committed "
            "Archify source and regenerates its interactive/browser evidence artifact."
        )
        readme = readme.replace(workshop_ci, public_ci)

        old_badge = (
            f"[![Tests]({PUBLIC_REPO_URL}/actions/workflows/test.yml/badge.svg)]"
            f"({PUBLIC_REPO_URL}/actions/workflows/test.yml)"
        )
        architecture_badge = (
            f"[![Architecture Evidence]({PUBLIC_REPO_URL}/actions/workflows/architecture.yml/badge.svg)]"
            f"({PUBLIC_REPO_URL}/actions/workflows/architecture.yml)"
        )
        readme = readme.replace(old_badge, architecture_badge)
        readme_path.write_text(readme, encoding="utf-8")

    architecture_doc = output_dir / "docs" / "architecture.md"
    if architecture_doc.exists():
        text = architecture_doc.read_text(encoding="utf-8")
        text = text.replace(
            "](../references/",
            f"](../{PUBLIC_PLUGIN_PREFIX}references/",
        )
        text = _prefix_inline_code_paths(text)
        architecture_doc.write_text(text, encoding="utf-8")


def compile_public_repo(output_dir: Path) -> Path:
    """Compile workshop repository into clean public release topology."""
    print(f"[EXPORT] Compiling clean public release to: {output_dir}")
    if output_dir.exists():
        def _on_rm_error(func, path, exc_info):
            """Handle read-only or locked files on Windows."""
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(output_dir, onerror=_on_rm_error)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Root governance and license files
    for root_file in ["README.md", "LICENSE", "PRIVACY.md", "TERMS.md"]:
        src_file = ROOT_DIR / root_file
        if src_file.exists():
            shutil.copy2(src_file, output_dir / root_file)
            print(f"  + Copied root: {root_file}")

    # 2. Public documentation and reproducible architecture evidence.
    docs_src = ROOT_DIR / "docs"
    if docs_src.exists() and docs_src.is_dir():
        copy_tree_filtered(docs_src, output_dir / "docs")
        public_architecture = output_dir / "docs" / "architecture" / "seg.architecture.json"
        adapt_architecture_source_for_public_repo(public_architecture)
        print("  + Copied public docs: docs/")
        print("  + Adapted Archify source paths to public plugin topology")

    # The architecture workflow is safe to expose publicly because it validates
    # only committed documentation/source evidence and downloads a pinned Archify release.
    architecture_workflow = ROOT_DIR / ".github" / "workflows" / "architecture.yml"
    if architecture_workflow.exists():
        workflow_dest = output_dir / ".github" / "workflows" / "architecture.yml"
        workflow_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(architecture_workflow, workflow_dest)
        print("  + Copied architecture evidence workflow")

    # 3. Canonical marketplace manifest in .agents/plugins/marketplace.json
    agents_dir = output_dir / ".agents" / "plugins"
    agents_dir.mkdir(parents=True, exist_ok=True)
    mkt_file = agents_dir / "marketplace.json"
    mkt_file.write_text(json.dumps(MARKETPLACE_SPEC, indent=2), encoding="utf-8")
    print("  + Generated marketplace: .agents/plugins/marketplace.json")

    # 4. Full skill package in plugins/skill-evaluation-graph/
    plugin_dest = output_dir / "plugins" / "skill-evaluation-graph"
    plugin_dest.mkdir(parents=True, exist_ok=True)

    # Package root files
    for skill_root_file in [
        "CLAUDE.md",
        "GEMINI.md",
        "AGENTS.md",
        "gemini-extension.json",
    ]:
        src_path = ROOT_DIR / skill_root_file
        if src_path.exists():
            shutil.copy2(src_path, plugin_dest / skill_root_file)

    # Transform SKILL.md frontmatter name to match the public plugin directory name ('skill-evaluation-graph')
    skill_md_src = ROOT_DIR / "SKILL.md"
    if skill_md_src.exists():
        skill_content = skill_md_src.read_text(encoding="utf-8")
        skill_content = skill_content.replace("name: skill-auditor", "name: skill-evaluation-graph", 1)
        (plugin_dest / "SKILL.md").write_text(skill_content, encoding="utf-8")
        print("  + Configured SKILL.md: name -> 'skill-evaluation-graph'")

    # Package directories
    package_dirs = [
        ".claude-plugin",
        ".codex-plugin",
        "hooks",
        "src",
        "scripts",
        "references",
        "assets",
        "agents",
    ]
    for p_dir in package_dirs:
        src_p = ROOT_DIR / p_dir
        if src_p.exists() and src_p.is_dir():
            copy_tree_filtered(src_p, plugin_dest / p_dir)
            print(f"  + Bundled package dir: plugins/skill-evaluation-graph/{p_dir}/")

    # Retarget README/docs after the nested plugin package exists.
    adapt_public_document_links(output_dir)
    print("  + Adapted public README/docs links and commands to release topology")

    print("[EXPORT] Compilation complete.")
    return output_dir


def validate_public_repo(repo_dir: Path) -> bool:
    """Validate exported repository with PortabilityEvaluatorNode and audit_skill."""
    print("\n[VALIDATE] Validating exported release repository...")
    plugin_dir = repo_dir / "plugins" / "skill-evaluation-graph"

    # Step 1: Validate repository-level portability and marketplace conformance
    portability_node = PortabilityEvaluatorNode()
    result = portability_node.execute(repo_dir, context={})
    errors = [f for f in result.findings if f.severity == "ERROR"]
    warnings = [f for f in result.findings if f.severity == "WARNING"]

    print(f"  Repo-level Portability Findings: {len(result.findings)} (Errors: {len(errors)}, Warnings: {len(warnings)})")
    for f in result.findings:
        print(f"    [{f.severity}][{f.rule_id or f.category}] {f.message}")

    if errors:
        print("[FAIL] Repository-level marketplace validation failed.")
        return False

    # Step 2: Validate the bundled skill itself using SEG self-audit
    print("\n[VALIDATE] Auditing bundled skill package...")
    report = audit_skill(plugin_dir)
    print(f"  Static Quality Score: {report.static_quality_score} / 100")
    print(f"  Total Findings:       {len(report.findings)}")
    print(f"  Broken Links:         {len(report.broken_links)}")
    oracle_verdict = report.oracle_decision.verdict.value if report.oracle_decision else "UNKNOWN"
    print(f"  Oracle Verdict:       {oracle_verdict}")

    if report.static_quality_score < 95 or oracle_verdict != "ACCEPT":
        print(f"[FAIL] Bundled skill audit failed (Score {report.static_quality_score} < 95 or Verdict {oracle_verdict} != ACCEPT).")
        return False

    print("[PASS] Clean public release tree fully verified.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile workshop repository into clean public release topology."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=ROOT_DIR / "dist" / "public_release",
        help="Destination directory for public release tree (default: dist/public_release)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the exported repository using PortabilityEvaluatorNode and audit_skill",
    )
    args = parser.parse_args()

    out_dir = compile_public_repo(args.output)

    if args.validate:
        ok = validate_public_repo(out_dir)
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
