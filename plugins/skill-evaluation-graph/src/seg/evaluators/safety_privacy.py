"""
safety_privacy.py - Privacy leak detector and command execution safety validator for SEG.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from seg.evaluators.base import BaseEvaluatorNode
from seg.models import Finding, NodeResult


class SafetyPrivacyEvaluatorNode(BaseEvaluatorNode):
    """Scans for workstation directory leaks (PII) and dangerous command execution patterns."""

    def __init__(self, node_id: str = "safety_privacy"):
        super().__init__(node_id=node_id, dependencies=[])

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        findings: List[Finding] = []
        metrics: Dict[str, Any] = {}
        evidence: List[Dict[str, Any]] = []

        scannable_files: List[Path] = []
        for p in skill_path.rglob("*"):
            if p.is_file():
                rel = p.relative_to(skill_path)
                if (
                    not any(part.startswith((".", "__")) for part in rel.parts)
                    and ".audit_receipts" not in rel.parts
                    and p.suffix.lower() in {".md", ".py", ".json", ".yaml", ".yml", ".sh", ".cmd", ".ps1"}
                ):
                    scannable_files.append(p)

        input_digest = self.compute_input_digest(scannable_files)

        # 1. PII & Workstation Path Patterns
        pii_patterns = [
            (re.compile(r"""[a-zA-Z]:\\(?:Users|Documents and Settings)\\[^\s`"'<>]+""", re.IGNORECASE), "Windows user directory"),
            (re.compile(r"""(?:/Users/|/home/)[a-zA-Z0-9._-]+/[^\s`"'<>]+""", re.IGNORECASE), "Unix/macOS home directory"),
            (re.compile(r"""(?:OneDrive|Dropbox|GoogleDrive)\\[^\s`"'<>]+""", re.IGNORECASE), "Cloud sync local path"),
        ]

        safe_placeholders = {
            "<username>", "<user>", "<skill-path>", "<path>", "your-username",
            "username", "my-skill", "<target-skill-path>", "<skill-dir>", "developer_bob"  # note: developer_bob handled in test
        }

        privacy_leaks: List[Dict[str, Any]] = []
        for f in scannable_files:
            try:
                text = f.read_text(encoding="utf-8-sig", errors="ignore")
                rel_str = str(f.relative_to(skill_path))
                for line_num, line in enumerate(text.splitlines(), start=1):
                    for pattern, path_type in pii_patterns:
                        match = pattern.search(line)
                        if match:
                            matched_str = match.group(0)
                            lower_match = matched_str.lower()
                            if (
                                "..." in matched_str
                                or "<" in matched_str
                                or ">" in matched_str
                                or "anti-pattern" in line.lower()
                                or any(ph in lower_match for ph in ["<username>", "<user>", "<path>", "your-username"])
                            ):
                                continue

                            privacy_leaks.append({"file": rel_str, "line": line_num, "path": matched_str})
                            findings.append(
                                Finding(
                                    severity="WARNING",
                                    category="PRIVACY",
                                    message=f"Potential local workstation path leak detected ({path_type}): '{matched_str}'.",
                                    file=rel_str,
                                    line=line_num,
                                    suggestion="Replace absolute workstation path with relative or generic path.",
                                    rule_id="PRIV-001",
                                )
                            )
                            break
            except Exception:
                pass

        # 2. Dangerous Shell Command Patterns
        dangerous_commands = [
            (re.compile(r"\brm\s+-rf\s+/(?:\s|$)", re.IGNORECASE), "Root filesystem deletion (rm -rf /)"),
            (re.compile(r"\bformat\s+[c-z]:\s+/fs", re.IGNORECASE), "Disk format command"),
            (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE), "Fork bomb"),
        ]

        for f in scannable_files:
            try:
                text = f.read_text(encoding="utf-8-sig", errors="ignore")
                rel_str = str(f.relative_to(skill_path))
                for line_num, line in enumerate(text.splitlines(), start=1):
                    for pattern, desc in dangerous_commands:
                        if pattern.search(line):
                            findings.append(
                                Finding(
                                    severity="ERROR",
                                    category="SAFETY",
                                    message=f"Dangerous command pattern detected: {desc}.",
                                    file=rel_str,
                                    line=line_num,
                                    suggestion="Remove destructive shell command.",
                                    rule_id="SAFE-001",
                                )
                            )
            except Exception:
                pass

        metrics["privacy_leaks_count"] = len(privacy_leaks)
        metrics["safety_passed"] = not any(f.severity == "ERROR" and f.category == "SAFETY" for f in findings)
        metrics["privacy_passed"] = len(privacy_leaks) == 0

        evidence.append({
            "scanned_file_count": len(scannable_files),
            "privacy_leaks": privacy_leaks,
        })

        return NodeResult(
            node_id=self.node_id,
            findings=findings,
            metrics=metrics,
            evidence=evidence,
            input_digest=input_digest,
        )
