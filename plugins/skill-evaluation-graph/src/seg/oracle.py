"""
oracle.py - Evidence Join and Multi-Gate Evaluator Oracle for SEG.
"""

from __future__ import annotations

from typing import Any, Dict, List

from seg.models import (
    Finding,
    FindingKind,
    GateResult,
    JoinedEvidence,
    NodeResult,
    NodeStatus,
    OracleDecision,
    OracleVerdict,
)


def synthesize_joined_evidence(node_results: Dict[str, NodeResult]) -> JoinedEvidence:
    """
    Synthesize independent node execution results into a unified JoinedEvidence structure.
    Calculates composite score, aggregate findings, and validates execution integrity.
    """
    total_findings: List[Finding] = []
    broken_links: List[str] = []
    harness_compat: Dict[str, str] = {}
    node_summaries: Dict[str, Dict[str, Any]] = {}
    token_metrics: Dict[str, Any] = {}
    failed_nodes: List[str] = []
    skipped_nodes: List[str] = []

    # Fail closed by default: flags are False until proven True by successful nodes
    spec_passed = False
    safety_passed = False
    privacy_passed = False

    for nid, res in node_results.items():
        total_findings.extend(res.findings)
        node_summaries[nid] = {
            "status": res.status.value if isinstance(res.status, NodeStatus) else str(res.status),
            "findings_count": len(res.findings),
            "duration_sec": res.duration_sec,
            "output_digest": res.output_digest,
            "error_message": res.error_message,
        }

        # Track execution failures and unhandled skips
        if res.status in (NodeStatus.FAILED, NodeStatus.TIMED_OUT) or res.error_message:
            failed_nodes.append(nid)
        elif res.status == NodeStatus.SKIPPED:
            skipped_nodes.append(nid)

        # Only accept metrics from nodes that succeeded
        if res.status == NodeStatus.SUCCESS:
            if nid == "schema":
                spec_passed = bool(res.metrics.get("is_valid_spec", False))
            elif nid == "links_syntax":
                broken_links.extend(res.evidence[0].get("broken_links", [])) if res.evidence else None
            elif nid == "safety_privacy":
                safety_passed = bool(res.metrics.get("safety_passed", False))
                privacy_passed = bool(res.metrics.get("privacy_passed", False))
            elif nid == "portability":
                harness_compat = res.metrics.get("harness_status", {})
            elif nid == "token_economics":
                token_metrics = res.metrics

    # Calculate static quality score (0 to 100)
    score = 100
    for f in total_findings:
        if f.severity == "ERROR":
            score -= 10
        elif f.severity == "WARNING":
            score -= 3

    # Extra penalty for broken links and node failures
    score -= len(broken_links) * 5
    if failed_nodes:
        score -= len(failed_nodes) * 20

    clamped_score = max(0, min(100, score))
    integrity_passed = (len(failed_nodes) == 0 and len(skipped_nodes) == 0 and len(node_results) > 0)

    # Fail specification conformance if ANY evaluator emitted a SPECIFICATION_ERROR finding
    has_spec_errors = any(f.kind == FindingKind.SPECIFICATION_ERROR for f in total_findings)
    if has_spec_errors:
        spec_passed = False

    return JoinedEvidence(
        total_findings=total_findings,
        static_quality_score=clamped_score,
        evaluation_integrity_passed=integrity_passed,
        specification_passed=spec_passed,
        safety_passed=safety_passed,
        privacy_passed=privacy_passed,
        failed_nodes=failed_nodes,
        skipped_nodes=skipped_nodes,
        harness_compatibility=harness_compat,
        node_summaries=node_summaries,
        broken_links=broken_links,
        token_metrics=token_metrics,
    )


class EvaluatorOracle:
    """
    Evaluates JoinedEvidence against explicit mandatory gates to produce an
    explainable OracleDecision (ACCEPT, REVISE, or ESCALATE).
    """

    def __init__(self, target_score: int = 95, max_iterations: int = 3):
        self.target_score = target_score
        self.max_iterations = max_iterations

    def evaluate(self, evidence: JoinedEvidence, iteration: int = 1) -> OracleDecision:
        reasons: List[str] = []
        gate_results: List[GateResult] = []

        # Gate 0: Evaluation Integrity Gate (Must pass before anything else)
        gate_integrity = GateResult(
            gate_id="evaluation_integrity",
            display_name="Evaluation Integrity Gate",
            passed=evidence.evaluation_integrity_passed and len(evidence.failed_nodes) == 0,
            details="All required evaluator nodes executed successfully without crashes or skips",
            mandatory=True,
        )
        gate_results.append(gate_integrity)
        if not gate_integrity.passed:
            failed_info = []
            if evidence.failed_nodes:
                failed_info.append(f"failed nodes: {evidence.failed_nodes}")
            if evidence.skipped_nodes:
                failed_info.append(f"skipped nodes: {evidence.skipped_nodes}")
            reasons.append(f"Evaluation integrity gate failed ({', '.join(failed_info) if failed_info else 'missing required nodes'})")

        # Gate 1: Specification Conformance Gate
        gate_spec = GateResult(
            gate_id="specification_conformance",
            display_name="Specification Conformance Gate",
            passed=evidence.specification_passed,
            details="Strict compliance with Agent Skills frontmatter and cross-harness manifest specifications",
            mandatory=True,
        )
        gate_results.append(gate_spec)
        if not gate_spec.passed:
            reasons.append("Specification conformance gate failed (invalid frontmatter, missing SKILL.md, or active specification errors)")

        # Gate 2: Safety & Privacy Gate
        gate_safe = GateResult(
            gate_id="safety_privacy",
            display_name="Safety & Privacy Gate",
            passed=evidence.safety_passed and evidence.privacy_passed,
            details="No dangerous command patterns and zero workstation path leaks",
            mandatory=True,
        )
        gate_results.append(gate_safe)
        if not evidence.safety_passed:
            reasons.append("Critical safety violations detected in scripts or markdown")
        if not evidence.privacy_passed:
            reasons.append("Workstation path leaks (PII) detected")

        # Gate 3: Link Integrity Gate
        gate_links = GateResult(
            gate_id="link_integrity",
            display_name="Link Integrity Gate",
            passed=len(evidence.broken_links) == 0,
            details="All internal relative links resolve on disk",
            mandatory=True,
        )
        gate_results.append(gate_links)
        if not gate_links.passed:
            reasons.append(f"{len(evidence.broken_links)} broken relative link(s) detected")

        # Gate 4: SEG Quality Policy Gate
        gate_score = GateResult(
            gate_id="quality_policy",
            display_name="SEG Quality Policy Gate",
            passed=evidence.static_quality_score >= self.target_score,
            details=f"Score {evidence.static_quality_score}/100 >= target {self.target_score}",
            mandatory=True,
        )
        gate_results.append(gate_score)
        if not gate_score.passed:
            reasons.append(f"Composite score ({evidence.static_quality_score}/100) below target threshold ({self.target_score}/100)")

        # Oracle Verdict Determination
        all_passed = all(g.passed for g in gate_results if g.mandatory)

        if all_passed:
            verdict = OracleVerdict.ACCEPT
        elif iteration < self.max_iterations:
            verdict = OracleVerdict.REVISE
        else:
            verdict = OracleVerdict.ESCALATE
            reasons.append(f"Maximum iteration ceiling reached ({iteration}/{self.max_iterations})")

        return OracleDecision(
            verdict=verdict,
            reasons=reasons,
            gate_results=gate_results,
            iteration=iteration,
            max_iterations=self.max_iterations,
        )
