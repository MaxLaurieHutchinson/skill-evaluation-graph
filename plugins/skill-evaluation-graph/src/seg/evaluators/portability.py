"""portability.py - Cross-harness packaging and manifest evaluator for SEG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from seg.evaluators.base import BaseEvaluatorNode
from seg.evaluators.schema import SchemaEvaluatorNode
from seg.models import Finding, FindingKind, NodeResult

GEMINI_CLI_AUTHORITY = "Google Gemini CLI Extension Specification"
GEMINI_CLI_SPEC_URL = "https://geminicli.com/docs/extensions/reference/"
ANTIGRAVITY_AUTHORITY = "Google Antigravity Agent Skills Documentation"
ANTIGRAVITY_SPEC_URL = "https://antigravity.google/docs/skills/"

CLAUDE_AUTHORITY = "Anthropic Claude Code Plugin Specification"
CLAUDE_SPEC_URL = "https://docs.anthropic.com/en/docs/agents-and-tools/claude-code"
CLAUDE_HOOKS_AUTHORITY = "Anthropic Claude Code Plugin Hooks Specification"
CLAUDE_HOOKS_URL = CLAUDE_SPEC_URL

CODEX_PLUGIN_AUTHORITY = "OpenAI Codex Plugin Specification"
CODEX_MKT_AUTHORITY = "OpenAI Codex Marketplace Manifest Specification"
CODEX_PLUGIN_URL = (
    "https://github.com/openai/plugins/blob/main/"
    ".agents/skills/plugin-creator/references/plugin-json-spec.md"
)
CODEX_MKT_URL = CODEX_PLUGIN_URL
SEG_PORTABILITY_AUTHORITY = "SEG Portability Guidelines"

VALID_CODEX_CATEGORIES = {
    "Developer Tools", "Productivity", "Data & Analytics", "Communication",
    "Design", "Education", "Finance", "Marketing", "Sales", "Security",
    "Writing", "Other",
}
VALID_INSTALLATION_POLICIES = {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}
VALID_AUTH_POLICIES = {"ON_INSTALL", "ON_USE"}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _finding(
    severity: str,
    message: str,
    *,
    file: str,
    rule_id: str,
    authority: str,
    source_url: str | None = None,
    kind: FindingKind = FindingKind.SPECIFICATION_ERROR,
    suggestion: str | None = None,
) -> Finding:
    return Finding(
        severity=severity,
        category="HARNESS",
        message=message,
        file=file,
        suggestion=suggestion,
        rule_id=rule_id,
        kind=kind,
        authority=authority,
        source_url=source_url,
    )


class PortabilityEvaluatorNode(BaseEvaluatorNode):
    """Validate target packaging without conflating packaging, SEG capability, or live verification."""

    def __init__(self, node_id: str = "portability"):
        super().__init__(node_id=node_id, dependencies=["schema"])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        manifest_paths = [
            skill_path / "SKILL.md",
            skill_path / "gemini-extension.json",
            skill_path / ".claude-plugin" / "plugin.json",
            skill_path / ".codex-plugin" / "plugin.json",
            skill_path / ".agents" / "plugins" / "marketplace.json",
            skill_path / "hooks" / "hooks.json",
            skill_path / "CLAUDE.md",
            skill_path / "AGENTS.md",
            skill_path / "GEMINI.md",
        ]
        input_digest = self.compute_input_digest(manifest_paths)

        host_names = [
            "Agent Skills Standard",
            "Anthropic Claude Code",
            "Google Gemini CLI",
            "Google Antigravity",
            "OpenAI Codex",
            "Cursor / Copilot",
        ]
        packaging_evidence = {name: "Not Configured" for name in host_names}
        harness_capabilities = {name: "Not Implemented" for name in host_names}
        harness_capabilities["OpenAI Codex"] = "Adapter Available"
        target_verification = {name: "Not Run" for name in host_names}

        # Agent Skills conformance belongs to the schema evaluator. If this node is
        # invoked directly, run that evaluator rather than inferring validation from file existence.
        schema_result = context.get("schema")
        if not isinstance(schema_result, NodeResult) and (skill_path / "SKILL.md").exists():
            schema_result = SchemaEvaluatorNode().execute(skill_path, {})
        if isinstance(schema_result, NodeResult):
            schema_errors = [f for f in schema_result.findings if f.severity == "ERROR"]
            packaging_evidence["Agent Skills Standard"] = (
                "Manifest Invalid" if schema_errors else "Manifest Validated"
            )
            # Antigravity consumes the Agent Skills standard directly. This is compatibility
            # evidence only; SEG does not claim a dedicated Antigravity plugin manifest/adapter.
            packaging_evidence["Google Antigravity"] = (
                "Agent Skill Invalid" if schema_errors else "Agent Skill Compatible"
            )

        # Gemini CLI extension manifest. Never classify this as an Antigravity plugin manifest.
        gemini_manifest = skill_path / "gemini-extension.json"
        if gemini_manifest.exists():
            errors = 0
            try:
                data = _read_json(gemini_manifest)
                if not isinstance(data, dict) or not data.get("name"):
                    findings.append(_finding(
                        "ERROR", "gemini-extension.json missing required 'name' field.",
                        file="gemini-extension.json", rule_id="HARN-001",
                        authority=GEMINI_CLI_AUTHORITY, source_url=GEMINI_CLI_SPEC_URL,
                    ))
                    errors += 1
                context_file = data.get("contextFileName") if isinstance(data, dict) else None
                if context_file and not (skill_path / context_file).exists():
                    findings.append(_finding(
                        "ERROR", f"gemini-extension.json references missing context file '{context_file}'.",
                        file="gemini-extension.json", rule_id="HARN-002",
                        authority=GEMINI_CLI_AUTHORITY, source_url=GEMINI_CLI_SPEC_URL,
                    ))
                    errors += 1
            except Exception as exc:
                findings.append(_finding(
                    "ERROR", f"Invalid JSON in gemini-extension.json: {exc}",
                    file="gemini-extension.json", rule_id="HARN-003",
                    authority=GEMINI_CLI_AUTHORITY, source_url=GEMINI_CLI_SPEC_URL,
                ))
                errors += 1
            packaging_evidence["Google Gemini CLI"] = "Manifest Invalid" if errors else "Manifest Validated"

        claude_manifest = skill_path / ".claude-plugin" / "plugin.json"
        if claude_manifest.exists():
            errors = 0
            try:
                data = _read_json(claude_manifest)
                if not isinstance(data, dict) or not data.get("name"):
                    findings.append(_finding(
                        "ERROR", ".claude-plugin/plugin.json missing required 'name' field.",
                        file=".claude-plugin/plugin.json", rule_id="HARN-004",
                        authority=CLAUDE_AUTHORITY, source_url=CLAUDE_SPEC_URL,
                    ))
                    errors += 1
            except Exception as exc:
                findings.append(_finding(
                    "ERROR", f"Invalid JSON in .claude-plugin/plugin.json: {exc}",
                    file=".claude-plugin/plugin.json", rule_id="HARN-005",
                    authority=CLAUDE_AUTHORITY, source_url=CLAUDE_SPEC_URL,
                ))
                errors += 1
            packaging_evidence["Anthropic Claude Code"] = "Manifest Invalid" if errors else "Manifest Validated"

        codex_manifest = skill_path / ".codex-plugin" / "plugin.json"
        marketplace_manifest = skill_path / ".agents" / "plugins" / "marketplace.json"
        codex_errors = 0
        codex_name: str | None = None

        if codex_manifest.exists():
            try:
                data = _read_json(codex_manifest)
                if not isinstance(data, dict) or not data.get("name"):
                    findings.append(_finding(
                        "ERROR", ".codex-plugin/plugin.json missing required 'name' field.",
                        file=".codex-plugin/plugin.json", rule_id="HARN-006",
                        authority=CODEX_PLUGIN_AUTHORITY, source_url=CODEX_PLUGIN_URL,
                    ))
                    codex_errors += 1
                else:
                    codex_name = data["name"]
                skills_ref = data.get("skills") if isinstance(data, dict) else None
                if skills_ref and not (skill_path / skills_ref).resolve().exists():
                    findings.append(_finding(
                        "ERROR", f".codex-plugin/plugin.json references missing skills path '{skills_ref}'.",
                        file=".codex-plugin/plugin.json", rule_id="HARN-007",
                        authority=CODEX_PLUGIN_AUTHORITY, source_url=CODEX_PLUGIN_URL,
                    ))
                    codex_errors += 1
                interface = data.get("interface", {}) if isinstance(data, dict) else {}
                if isinstance(interface, dict):
                    for asset_field in ("composerIcon", "logo"):
                        asset = interface.get(asset_field)
                        if asset and not (skill_path / asset).resolve().exists():
                            findings.append(_finding(
                                "WARNING", f".codex-plugin/plugin.json references missing interface asset '{asset}'.",
                                file=".codex-plugin/plugin.json", rule_id="HARN-008",
                                authority=CODEX_PLUGIN_AUTHORITY, source_url=CODEX_PLUGIN_URL,
                                kind=FindingKind.SEG_RECOMMENDATION,
                            ))
                    category = interface.get("category") or data.get("category")
                    if category and category not in VALID_CODEX_CATEGORIES:
                        findings.append(_finding(
                            "ERROR", f".codex-plugin/plugin.json category '{category}' is invalid.",
                            file=".codex-plugin/plugin.json", rule_id="HARN-012",
                            authority=CODEX_PLUGIN_AUTHORITY, source_url=CODEX_PLUGIN_URL,
                        ))
                        codex_errors += 1
            except Exception as exc:
                findings.append(_finding(
                    "ERROR", f"Invalid JSON in .codex-plugin/plugin.json: {exc}",
                    file=".codex-plugin/plugin.json", rule_id="HARN-009",
                    authority=CODEX_PLUGIN_AUTHORITY, source_url=CODEX_PLUGIN_URL,
                ))
                codex_errors += 1

        if marketplace_manifest.exists():
            try:
                data = _read_json(marketplace_manifest)
                if not isinstance(data, dict):
                    findings.append(_finding(
                        "ERROR", ".agents/plugins/marketplace.json must be a JSON object.",
                        file=".agents/plugins/marketplace.json", rule_id="MKT-001",
                        authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                    ))
                    codex_errors += 1
                elif not isinstance(data.get("plugins"), list):
                    findings.append(_finding(
                        "ERROR", ".agents/plugins/marketplace.json missing required 'plugins' array.",
                        file=".agents/plugins/marketplace.json", rule_id="MKT-002",
                        authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                    ))
                    codex_errors += 1
                else:
                    for index, entry in enumerate(data["plugins"]):
                        if not isinstance(entry, dict):
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin #{index} must be an object.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-003",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1
                            continue

                        name = entry.get("name")
                        if not name:
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin #{index} missing required 'name' field.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-004",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1

                        category = entry.get("category")
                        if not category or category not in VALID_CODEX_CATEGORIES:
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name or index}' has missing or invalid category '{category}'.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-015",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1

                        source = entry.get("source")
                        if not isinstance(source, dict):
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name or index}' missing 'source' object.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-005",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1
                            source = {}

                        source_type = source.get("source")
                        if source_type != "local":
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name}' source type '{source_type}' is invalid; repository entries require 'local'.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-006",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1

                        path_value = source.get("path")
                        if not path_value:
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name}' source missing required 'path' field.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-007",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1
                        else:
                            normalized = str(path_value).replace("\\", "/").strip()
                            if normalized in ("", ".", "./") or not (
                                normalized.startswith("./plugins/") or normalized.startswith("plugins/")
                            ):
                                findings.append(_finding(
                                    "ERROR", f"Marketplace plugin '{name}' path '{path_value}' does not follow './plugins/<plugin_name>'.",
                                    file=".agents/plugins/marketplace.json", rule_id="MKT-007",
                                    authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                                ))
                                codex_errors += 1
                            else:
                                resolved = (skill_path / path_value).resolve()
                                if not resolved.exists():
                                    findings.append(_finding(
                                        "ERROR", f"Marketplace plugin '{name}' path '{path_value}' does not exist.",
                                        file=".agents/plugins/marketplace.json", rule_id="MKT-008",
                                        authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                                    ))
                                    codex_errors += 1
                                else:
                                    if name and resolved.name != name:
                                        findings.append(_finding(
                                            "ERROR", f"Marketplace plugin name '{name}' does not match plugin folder name '{resolved.name}'.",
                                            file=".agents/plugins/marketplace.json", rule_id="MKT-014",
                                            authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                                        ))
                                        codex_errors += 1
                                    inner_manifest = resolved / ".codex-plugin" / "plugin.json"
                                    if not inner_manifest.exists():
                                        inner_manifest = resolved / "plugin.json"
                                    if inner_manifest.exists():
                                        try:
                                            inner_name = _read_json(inner_manifest).get("name")
                                            if name and inner_name and name != inner_name:
                                                findings.append(_finding(
                                                    "ERROR", f"Marketplace plugin name '{name}' does not match plugin manifest name '{inner_name}'.",
                                                    file=".agents/plugins/marketplace.json", rule_id="MKT-013",
                                                    authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                                                ))
                                                codex_errors += 1
                                        except Exception:
                                            pass

                        policy = entry.get("policy")
                        if not isinstance(policy, dict):
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name}' missing required 'policy' object.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-009",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1
                            policy = {}
                        if policy.get("installation") not in VALID_INSTALLATION_POLICIES:
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name}' policy.installation value '{policy.get('installation')}' is invalid.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-010",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1
                        if policy.get("authentication") not in VALID_AUTH_POLICIES:
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin '{name}' policy.authentication value '{policy.get('authentication')}' is invalid.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-011",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1

                        if codex_name and name and codex_name != name:
                            findings.append(_finding(
                                "ERROR", f"Marketplace plugin name '{name}' does not match .codex-plugin/plugin.json name '{codex_name}'.",
                                file=".agents/plugins/marketplace.json", rule_id="MKT-013",
                                authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                            ))
                            codex_errors += 1
            except Exception as exc:
                findings.append(_finding(
                    "ERROR", f"Invalid JSON in .agents/plugins/marketplace.json: {exc}",
                    file=".agents/plugins/marketplace.json", rule_id="MKT-012",
                    authority=CODEX_MKT_AUTHORITY, source_url=CODEX_MKT_URL,
                ))
                codex_errors += 1

        if codex_manifest.exists() or marketplace_manifest.exists():
            packaging_evidence["OpenAI Codex"] = "Manifest Invalid" if codex_errors else "Manifest Validated"

        hooks_manifest = skill_path / "hooks" / "hooks.json"
        if hooks_manifest.exists():
            try:
                hooks_data = _read_json(hooks_manifest)
                if not isinstance(hooks_data, dict) or "hooks" not in hooks_data:
                    findings.append(_finding(
                        "WARNING", "hooks/hooks.json missing top-level 'hooks' object.",
                        file="hooks/hooks.json", rule_id="HARN-010",
                        authority=CLAUDE_HOOKS_AUTHORITY, source_url=CLAUDE_HOOKS_URL,
                        kind=FindingKind.SEG_RECOMMENDATION,
                    ))
            except Exception as exc:
                findings.append(_finding(
                    "ERROR", f"Invalid JSON in hooks/hooks.json: {exc}",
                    file="hooks/hooks.json", rule_id="HARN-011",
                    authority=CLAUDE_HOOKS_AUTHORITY, source_url=CLAUDE_HOOKS_URL,
                ))

        root_claude = skill_path / "CLAUDE.md"
        root_agents = skill_path / "AGENTS.md"
        root_gemini = skill_path / "GEMINI.md"
        if root_claude.exists() and root_agents.exists():
            text = root_agents.read_text(encoding="utf-8-sig", errors="ignore").strip()
            if len(text.splitlines()) > 5 and "CLAUDE.md" not in text:
                findings.append(_finding(
                    "INFO", "Divergent 'AGENTS.md' detected alongside 'CLAUDE.md'.",
                    file="AGENTS.md", rule_id="HARN-020", authority=SEG_PORTABILITY_AUTHORITY,
                    kind=FindingKind.SEG_RECOMMENDATION,
                    suggestion="Point AGENTS.md to the canonical contributor instructions.",
                ))
        if root_claude.exists() and root_gemini.exists():
            text = root_gemini.read_text(encoding="utf-8-sig", errors="ignore").strip()
            if len(text.splitlines()) > 5 and "CLAUDE.md" not in text:
                findings.append(_finding(
                    "INFO", "Divergent 'GEMINI.md' detected alongside 'CLAUDE.md'.",
                    file="GEMINI.md", rule_id="HARN-021", authority=SEG_PORTABILITY_AUTHORITY,
                    kind=FindingKind.SEG_RECOMMENDATION,
                    suggestion="Keep shared contributor instructions single-sourced.",
                ))
        if root_agents.exists():
            packaging_evidence["Cursor / Copilot"] = "Pointer Configured"

        metrics["packaging_evidence"] = packaging_evidence
        metrics["harness_capabilities"] = harness_capabilities
        metrics["target_verification"] = target_verification
        metrics["harness_status"] = packaging_evidence  # compatibility alias
        evidence = [{
            "packaging_evidence": packaging_evidence,
            "harness_capabilities": harness_capabilities,
            "target_verification": target_verification,
            "error_count": sum(1 for finding in findings if finding.severity == "ERROR"),
        }]
        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
