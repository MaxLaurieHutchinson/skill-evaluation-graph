#!/usr/bin/env python3
"""audit_skill.py - Deterministic SEG audit, profile, and evidence-backed scorecard CLI."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seg.evaluators import build_default_evaluation_dag
from seg.models import FileProfile, Finding, FindingKind
from seg.oracle import EvaluatorOracle, synthesize_joined_evidence


@dataclass
class AuditReport:
    skill_name: str = ""
    skill_dir: str = ""
    is_valid_structure: bool = False
    frontmatter_valid: bool = False
    name_matches_dir: bool = False
    word_count_skill_md: int = 0
    line_count_skill_md: int = 0
    estimated_tokens_skill_md: int = 0
    description_length_chars: int = 0
    description_word_count: int = 0
    total_files: int = 0
    referenced_files: list[str] = field(default_factory=list)
    orphaned_files: list[str] = field(default_factory=list)
    broken_links: list[dict[str, Any]] = field(default_factory=list)
    file_profiles: list[FileProfile] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    static_quality_score: int = 100
    oracle_decision: Any = None

    @property
    def structural_score(self) -> int:
        return self.static_quality_score

    @structural_score.setter
    def structural_score(self, value: int) -> None:
        self.static_quality_score = value

    def add_finding(
        self,
        severity: str,
        category: str,
        message: str,
        file: str | None = None,
        line: int | None = None,
        suggestion: str | None = None,
        rule_id: str | None = None,
        kind: Any = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                category=category,
                message=message,
                file=file,
                line=line,
                suggestion=suggestion,
                rule_id=rule_id,
                kind=kind or FindingKind.SEG_RECOMMENDATION,
            )
        )
        if severity == "ERROR":
            self.static_quality_score = max(0, self.static_quality_score - 20)
        elif severity == "WARNING":
            self.static_quality_score = max(0, self.static_quality_score - 5)


def audit_skill(skill_path: Path) -> AuditReport:
    """Execute the canonical SEG Evaluation Graph and Oracle."""
    skill_path = Path(skill_path).resolve()
    report = AuditReport(skill_dir=str(skill_path), skill_name=skill_path.name)

    if not skill_path.exists() or not skill_path.is_dir():
        report.add_finding("ERROR", "STRUCTURE", f"Path '{skill_path}' does not exist or is not a directory.")
        return report
    if not (skill_path / "SKILL.md").exists():
        report.add_finding("ERROR", "STRUCTURE", "Missing required 'SKILL.md' file.", file="SKILL.md")
        return report

    report.is_valid_structure = True
    results = build_default_evaluation_dag().execute(skill_path)
    joined = synthesize_joined_evidence(results)
    decision = EvaluatorOracle(target_score=95).evaluate(joined)

    report.static_quality_score = joined.static_quality_score
    report.findings.extend(joined.total_findings)
    report.oracle_decision = decision

    schema = results.get("schema")
    if schema:
        report.frontmatter_valid = schema.metrics.get("is_valid_spec", True) and not any(
            f.severity == "ERROR" and f.category in ("SPEC", "FRONTMATTER") for f in schema.findings
        )
        report.skill_name = schema.metrics.get("name", skill_path.name)
        report.name_matches_dir = not any(
            f.rule_id == "SPEC-006" or "does not match directory" in f.message for f in schema.findings
        )
        report.description_length_chars = schema.metrics.get("description_chars", 0)
        report.description_word_count = schema.metrics.get("description_words", 0)

    tokens = results.get("token_economics")
    if tokens:
        report.line_count_skill_md = tokens.metrics.get("skill_md_lines", 0)
        report.estimated_tokens_skill_md = tokens.metrics.get("skill_md_tokens", 0)
        report.word_count_skill_md = int(report.estimated_tokens_skill_md / 1.3) if report.estimated_tokens_skill_md else 0
        for item in tokens.evidence:
            for profile in item.get("profiles", []):
                report.file_profiles.append(
                    FileProfile(
                        path=profile["path"],
                        tier=profile["tier"],
                        lines=profile["lines"],
                        words=profile["words"],
                        tokens=profile["tokens"],
                    )
                )
        report.total_files = len(report.file_profiles)

    links = results.get("links_syntax")
    if links:
        for item in links.evidence:
            report.orphaned_files.extend(item.get("orphaned_files", []))
            for broken in item.get("broken_links", []):
                report.broken_links.append({"raw": broken})

    return report


def format_markdown_report(report: AuditReport) -> str:
    healthy = (
        report.is_valid_structure
        and report.frontmatter_valid
        and not any(f.severity == "ERROR" for f in report.findings)
    )
    lines = [
        f"### Skill Audit Report: `{report.skill_name or report.skill_dir}`",
        "",
        "| Metric | Result |",
        "|:---|:---|",
        f"| **Overall Health** | {'✅ Passed' if healthy else '❌ Issues Found'} |",
        f"| **Static Quality Score** | **{report.static_quality_score} / 100** |",
        f"| **Oracle Verdict** | **{report.oracle_decision.verdict.value if report.oracle_decision else 'UNKNOWN'}** |",
        f"| **Directory Alignment** | {'✅ Name matches directory' if report.name_matches_dir else '⚠️ Mismatch'} |",
        f"| **SKILL.md Size** | {report.line_count_skill_md} lines / {report.word_count_skill_md} words (~{report.estimated_tokens_skill_md} tokens) |",
        f"| **Broken Markdown Links** | {len(report.broken_links)} |",
        "",
    ]
    for heading, severity, icon in (
        ("Critical Errors", "ERROR", "❌"),
        ("Warnings", "WARNING", "⚠️"),
        ("Informational Notices", "INFO", "ℹ️"),
    ):
        items = [f for f in report.findings if f.severity == severity]
        if not items:
            continue
        lines += [f"#### {heading}"]
        for finding in items:
            location = f" (`{finding.file}`)" if finding.file else ""
            lines.append(f"- {icon} **[{finding.category}]**{location}: {finding.message}")
            if finding.suggestion:
                lines.append(f"  - {finding.suggestion}")
        lines.append("")
    if not report.findings:
        lines.append("✅ **All configured static checks passed.**")
    return "\n".join(lines)


def format_profile_report(report: AuditReport) -> str:
    lines = [
        f"### Context & Token Budget Profile: `{report.skill_name or report.skill_dir}`",
        "",
        "| Tier / Component | File Path | Lines | Words | Estimated Tokens |",
        "|:---|:---|---:|---:|---:|",
    ]
    for profile in report.file_profiles:
        lines.append(
            f"| {profile.tier} | `{profile.path}` | {profile.lines} | {profile.words} | ~{profile.tokens} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_scorecard(report: AuditReport, target_file: Path) -> None:
    """Project measured SEG evidence without inventing full-rubric pillar scores."""
    target_file = Path(target_file)
    verdict = report.oracle_decision.verdict.value if report.oracle_decision else "UNKNOWN"

    static_notes = {
        "Trigger & Routing Precision": (
            f"Static routing evidence collected; description {report.description_word_count} words / "
            f"{report.description_length_chars} chars. Full rubric not executed."
        ),
        "Progressive Disclosure": (
            f"Static context evidence collected; SKILL.md {report.line_count_skill_md} lines / "
            f"~{report.estimated_tokens_skill_md} tokens. Full rubric not executed."
        ),
        "Steering & Invariants": "Requires dedicated rubric review and/or behavioural trials.",
        "Execution Determinism": "Requires dedicated rubric review and execution evidence.",
        "Safety & Authority Gates": (
            "Safety/privacy evaluator findings are reflected in mandatory gate results; full 1–5 rubric not executed."
        ),
        "Token Economics & Density": (
            f"Static token profiling completed across {report.total_files} tracked files; full rubric not executed."
        ),
    }

    rows = "\n".join(
        f"| **{name}** | NOT EVALUATED | 5 / 5 | {note} |" for name, note in static_notes.items()
    )
    content = f"""# Agent Skill Evaluation Scorecard

| Metadata | Details |
|:---|:---|
| **Skill Name** | `{report.skill_name or Path(report.skill_dir).name}` |
| **Directory Path** | `{report.skill_dir}` |
| **Audit Date** | {date.today().isoformat()} |
| **Oracle Verdict** | **{verdict}** |
| **Static Quality Score** | **{report.static_quality_score} / 100** |

---

## Evidence Summary

Static SEG evaluation found **{len(report.findings)} findings** and **{len(report.broken_links)} broken links**.
The 1–5 rubric is intentionally not inferred from static proxies; run the dedicated rubric/behavioural evaluation before assigning pillar scores.

## 6-Pillar Rubric

| Pillar | Current Score | Target | Evidence Note |
|:---|:---:|:---:|:---|
{rows}

---

## Findings

"""
    if report.findings:
        for finding in report.findings:
            content += f"- **[{finding.severity}][{finding.category}]** {finding.message}\n"
    else:
        content += "No static findings.\n"

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")
    print(f"Generated evidence-backed scorecard: {target_file}")


def _report_dict(report: AuditReport) -> dict[str, Any]:
    return {
        "skill_name": report.skill_name,
        "skill_dir": report.skill_dir,
        "is_valid_structure": report.is_valid_structure,
        "frontmatter_valid": report.frontmatter_valid,
        "name_matches_dir": report.name_matches_dir,
        "static_quality_score": report.static_quality_score,
        "oracle_decision": report.oracle_decision.to_dict() if report.oracle_decision else None,
        "broken_links": report.broken_links,
        "findings": [f.to_dict() for f in report.findings],
        "file_profiles": [asdict(p) for p in report.file_profiles],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an Agent Skill with SEG.")
    parser.add_argument("skill_path", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--scorecard", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    report = audit_skill(args.skill_path)
    if args.scorecard:
        generate_scorecard(report, args.scorecard)
    if args.json_mode:
        print(json.dumps(_report_dict(report), indent=2))
    elif args.markdown:
        print(format_markdown_report(report))
    elif args.profile:
        print(format_profile_report(report))
    else:
        print("=" * 70)
        print(f"SKILL AUDIT REPORT: {report.skill_name or report.skill_dir}")
        print("=" * 70)
        print(f"Directory:            {report.skill_dir}")
        print(f"Structure Valid:      {'YES' if report.is_valid_structure else 'NO'}")
        print(f"Frontmatter Valid:    {'YES' if report.frontmatter_valid else 'NO'}")
        print(f"Name Matches Dir:     {'YES' if report.name_matches_dir else 'NO'}")
        print(f"Static Quality Score: {report.static_quality_score} / 100")
        if report.oracle_decision:
            print(f"Oracle Verdict:       {report.oracle_decision.verdict.value}")
        print(f"Findings:             {len(report.findings)}")
        if args.verbose:
            for finding in report.findings:
                print(f"[{finding.severity}][{finding.category}] {finding.message}")

    has_errors = any(f.severity == "ERROR" for f in report.findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
