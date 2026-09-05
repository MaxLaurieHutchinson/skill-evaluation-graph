#!/usr/bin/env python3
"""Validate the canonical repository in place without exporting or rewriting it."""

import argparse
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path("plugins/skill-evaluation-graph")
for directory in (ROOT / PLUGIN / "src", ROOT / PLUGIN / "scripts"):
    sys.path.insert(0, str(directory))

from audit_skill import audit_skill
from seg.behaviour.scenarios import load_scenarios_from_dir
from seg.evaluators.portability import PortabilityEvaluatorNode


REQUIRED_TEST_SUITES = (
    "architecture_docs",
    "behaviour",
    "evaluators",
    "graph",
    "migration_integrity",
    "receipts",
    "release_automation",
    "release_truth",
    "release_validation",
    "repair_boundaries",
    "repair_safety",
    "resource_reachability",
    "terminology",
)


def _semver_tuple(value: str):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value or "")
    return tuple(int(part) for part in match.groups()) if match else None


def validate_release(repo: Path) -> bool:
    """Check release assets, version parity, marketplace routing and self-audit."""
    repo = repo.resolve()
    plugin = repo / PLUGIN
    errors = []
    required = [
        "README.md", "CHANGELOG.md", "LICENSE", "PRIVACY.md", "TERMS.md", ".gitignore",
        ".agents/plugins/marketplace.json", ".github/workflows/test.yml",
        ".github/workflows/architecture.yml", ".github/workflows/release.yml",
        "release-please-config.json", ".release-please-manifest.json",
        "scripts/build_release.py", "scripts/validate_release.py",
        "docs/architecture.md", "docs/architecture/seg.architecture.json",
        "docs/architecture/seg-architecture-dark.svg",
    ]
    required += [str(PLUGIN / relative) for relative in (
        "SKILL.md", "requirements.txt", "src/seg/__init__.py",
        ".codex-plugin/plugin.json", ".claude-plugin/plugin.json", "gemini-extension.json",
        "evaluations/scenarios/subagent_review.json", "evaluations/scenarios/tdd_pressure.json",
        "evaluations/scenarios/verification_gate.json",
    )]
    required += [str(PLUGIN / "tests" / f"test_{suite}.py") for suite in REQUIRED_TEST_SUITES]
    errors.extend(f"Missing release file: {relative}" for relative in required if not (repo / relative).is_file())
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return False
    try:
        runtime_path = plugin / "src/seg/__init__.py"
        runtime_text = runtime_path.read_text(encoding="utf-8")
        module = ast.parse(runtime_text)
        versions = [ast.literal_eval(node.value) for node in module.body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
        if len(versions) != 1 or not isinstance(versions[0], str) or not versions[0]:
            raise ValueError("Expected one nonempty runtime __version__")
        runtime_semver = _semver_tuple(versions[0])
        if runtime_semver is None:
            errors.append(f"Runtime version is not MAJOR.MINOR.PATCH: {versions[0]}")
        if "x-release-please-version" not in runtime_text:
            errors.append("Runtime __version__ must carry x-release-please-version annotation")

        for path in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json", "gemini-extension.json"):
            manifest = json.loads((plugin / path).read_text(encoding="utf-8"))
            if manifest.get("version") != versions[0]:
                errors.append(f"Runtime/manifest version mismatch: {path}")

        release_config = json.loads((repo / "release-please-config.json").read_text(encoding="utf-8"))
        release_package = release_config.get("packages", {}).get(".", {})
        if release_package.get("release-type") != "simple":
            errors.append("Release Please root package must use release-type simple")
        if release_config.get("include-v-in-tag") is not True or release_config.get("include-component-in-tag") is not False:
            errors.append("Release Please tags must use plain vMAJOR.MINOR.PATCH tags")
        expected_json_targets = {
            "plugins/skill-evaluation-graph/.codex-plugin/plugin.json": "$.version",
            "plugins/skill-evaluation-graph/.claude-plugin/plugin.json": "$.version",
            "plugins/skill-evaluation-graph/gemini-extension.json": "$.version",
        }
        observed_json_targets = {
            item.get("path"): item.get("jsonpath")
            for item in release_package.get("extra-files", [])
            if isinstance(item, dict) and item.get("type") == "json"
        }
        if observed_json_targets != expected_json_targets:
            errors.append("Release Please must update all distributed host manifest versions")
        generic_targets = {
            item.get("path") for item in release_package.get("extra-files", [])
            if isinstance(item, dict) and item.get("type") == "generic"
        }
        if "plugins/skill-evaluation-graph/src/seg/__init__.py" not in generic_targets:
            errors.append("Release Please must update the canonical runtime version")

        release_manifest = json.loads((repo / ".release-please-manifest.json").read_text(encoding="utf-8"))
        released_version = release_manifest.get(".")
        released_semver = _semver_tuple(released_version) if isinstance(released_version, str) else None
        if released_semver is None:
            errors.append("Release Please manifest must contain a root MAJOR.MINOR.PATCH version")
        elif runtime_semver is not None and released_semver > runtime_semver:
            errors.append("Release Please manifest cannot be ahead of the runtime version")

        release_workflow = (repo / ".github/workflows/release.yml").read_text(encoding="utf-8")
        for required_text in (
            "Test and Validate SEG",
            "conclusion == 'success'",
            "head_branch == 'main'",
            "head_repository.full_name == github.repository",
            "release-please-oss/release-please-action@",
            "scripts/build_release.py",
            "gh release upload",
        ):
            if required_text not in release_workflow:
                errors.append(f"Release workflow is missing required contract: {required_text}")

        marketplace = json.loads((repo / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        entries = [entry for entry in marketplace.get("plugins", []) if entry.get("name") == "skill-evaluation-graph"]
        if len(entries) != 1 or entries[0].get("source") != {"source": "local", "path": f"./{PLUGIN.as_posix()}"}:
            errors.append("Marketplace must route SEG to the canonical nested plugin")
        result = PortabilityEvaluatorNode().execute(repo, {})
        errors.extend(f.message for f in result.findings if f.severity in ("ERROR", "WARNING"))
        scenarios = load_scenarios_from_dir(plugin / "evaluations/scenarios")
        if len(scenarios) != 3 or not all("version" in s and "minimum_trials" in s for s in scenarios):
            errors.append("Bundled catalogue must contain three versioned scenarios with minimum_trials")
        architecture = json.loads((repo / "docs/architecture/seg.architecture.json").read_text(encoding="utf-8"))
        sources = [source["path"] for component in architecture["components"] for source in component.get("sources", [])]
        if not sources:
            errors.append("Architecture has no repository source evidence")
        for source in sources:
            resolved = (repo / source).resolve()
            if not resolved.is_relative_to(plugin) or not resolved.is_file():
                errors.append(f"Architecture source is missing or outside the package: {source}")
        report = audit_skill(plugin)
        verdict = report.oracle_decision.verdict.value if report.oracle_decision else "UNKNOWN"
        if report.static_quality_score != 100 or report.findings or report.broken_links or verdict != "ACCEPT":
            errors.append(f"Self-audit: score={report.static_quality_score}, findings={len(report.findings)}, verdict={verdict}")
            errors.extend(f.message for f in report.findings)
    except (OSError, ValueError, TypeError, KeyError, SyntaxError) as exc:
        errors.append(f"Invalid release metadata: {exc}")
    for error in errors:
        print(f"[FAIL] {error}")
    if not errors:
        print(f"[PASS] Canonical release {versions[0]}: assets, versions, marketplace, scenarios, release automation, architecture paths and self-audit")
    return not errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, nargs="?", default=ROOT)
    raise SystemExit(0 if validate_release(parser.parse_args().repo) else 1)
