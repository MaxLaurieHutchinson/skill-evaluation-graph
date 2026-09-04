"""
models.py - Core data models and schema definitions for SEG (Skill Evaluation Graph).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class FindingKind(str, Enum):
    SPECIFICATION_ERROR = "SPECIFICATION_ERROR"
    SEG_RECOMMENDATION = "SEG_RECOMMENDATION"
    OBSERVED_FAILURE = "OBSERVED_FAILURE"


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    TIMED_OUT = "TIMED_OUT"


class OracleVerdict(str, Enum):
    ACCEPT = "ACCEPT"
    REVISE = "REVISE"
    ESCALATE = "ESCALATE"


class RunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PREVIEWED = "PREVIEWED"
    MUTATED = "MUTATED"
    ABORTED = "ABORTED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


@dataclass
class Finding:
    severity: str  # "ERROR", "WARNING", "INFO"
    category: str  # "SPEC", "LINKS", "STRUCTURE", "TOKEN_ECONOMY", "SAFETY", "PRIVACY", "HARNESS", "STEERING"
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    suggestion: Optional[str] = None
    rule_id: Optional[str] = None
    kind: FindingKind = FindingKind.SEG_RECOMMENDATION
    authority: Optional[str] = None
    source_url: Optional[str] = None
    source_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(self.kind, FindingKind):
            d["kind"] = self.kind.value
        return d


@dataclass
class FileProfile:
    path: str
    tier: str  # "Tier 1", "Tier 2", etc.
    lines: int
    words: int
    tokens: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NodeResult:
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    findings: List[Finding] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_sec: float = 0.0
    input_digest: str = ""
    output_digest: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status.value if isinstance(self.status, NodeStatus) else str(self.status),
            "findings": [f.to_dict() for f in self.findings],
            "metrics": self.metrics,
            "evidence": self.evidence,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_sec": round(self.duration_sec, 4),
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "error_message": self.error_message,
        }


@dataclass
class JoinedEvidence:
    total_findings: List[Finding] = field(default_factory=list)
    static_quality_score: int = 100
    evaluation_integrity_passed: bool = False
    specification_passed: bool = False
    safety_passed: bool = False
    privacy_passed: bool = False
    failed_nodes: List[str] = field(default_factory=list)
    skipped_nodes: List[str] = field(default_factory=list)
    harness_compatibility: Dict[str, str] = field(default_factory=dict)
    node_summaries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    broken_links: List[str] = field(default_factory=list)
    token_metrics: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        total_findings: Optional[List[Finding]] = None,
        static_quality_score: Optional[int] = None,
        evaluation_integrity_passed: bool = False,
        specification_passed: bool = False,
        safety_passed: bool = False,
        privacy_passed: bool = False,
        failed_nodes: Optional[List[str]] = None,
        skipped_nodes: Optional[List[str]] = None,
        harness_compatibility: Optional[Dict[str, str]] = None,
        node_summaries: Optional[Dict[str, Dict[str, Any]]] = None,
        broken_links: Optional[List[str]] = None,
        token_metrics: Optional[Dict[str, Any]] = None,
        structural_score: Optional[int] = None,
    ):
        self.total_findings = total_findings if total_findings is not None else []
        if static_quality_score is not None:
            self.static_quality_score = static_quality_score
        elif structural_score is not None:
            self.static_quality_score = structural_score
        else:
            self.static_quality_score = 100
        self.evaluation_integrity_passed = evaluation_integrity_passed
        self.specification_passed = specification_passed
        self.safety_passed = safety_passed
        self.privacy_passed = privacy_passed
        self.failed_nodes = failed_nodes if failed_nodes is not None else []
        self.skipped_nodes = skipped_nodes if skipped_nodes is not None else []
        self.harness_compatibility = harness_compatibility if harness_compatibility is not None else {}
        self.node_summaries = node_summaries if node_summaries is not None else {}
        self.broken_links = broken_links if broken_links is not None else []
        self.token_metrics = token_metrics if token_metrics is not None else {}

    @property
    def structural_score(self) -> int:
        return self.static_quality_score

    @structural_score.setter
    def structural_score(self, val: int) -> None:
        self.static_quality_score = val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "static_quality_score": self.static_quality_score,
            "structural_score": self.static_quality_score,  # backward compatibility alias
            "evaluation_integrity_passed": self.evaluation_integrity_passed,
            "specification_passed": self.specification_passed,
            "safety_passed": self.safety_passed,
            "privacy_passed": self.privacy_passed,
            "failed_nodes": self.failed_nodes,
            "skipped_nodes": self.skipped_nodes,
            "harness_compatibility": self.harness_compatibility,
            "broken_links_count": len(self.broken_links),
            "findings_count": len(self.total_findings),
            "node_summaries": self.node_summaries,
            "token_metrics": self.token_metrics,
        }


@dataclass
class GateResult:
    gate_id: str
    display_name: str
    passed: bool
    details: str = ""
    mandatory: bool = True

    @property
    def name(self) -> str:
        return self.display_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "display_name": self.display_name,
            "name": self.display_name,
            "passed": self.passed,
            "details": self.details,
            "mandatory": self.mandatory,
        }


@dataclass
class OracleDecision:
    verdict: OracleVerdict
    reasons: List[str] = field(default_factory=list)
    gate_results: List[GateResult] = field(default_factory=list)
    iteration: int = 1
    max_iterations: int = 3

    @property
    def gates(self) -> List[GateResult]:
        return self.gate_results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value if isinstance(self.verdict, OracleVerdict) else str(self.verdict),
            "reasons": self.reasons,
            "gate_results": [g.to_dict() if hasattr(g, "to_dict") else asdict(g) for g in self.gate_results],
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
        }
