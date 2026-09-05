#!/usr/bin/env python3
"""
run_loop.py - Autonomous Workflow Graph & Evaluator Loop Runner for Agent Skills.

Implements the canonical 4-shape graph architecture:
  Chain:    Node 1 (Intake & Scope Verification)
  Diamond:  Node 2 (DAG Parallel Evaluator Execution)
  Join:     Node 3 (Evidence Join & Composite Scoring)
  Oracle:   Node 4 (Multi-Gate Evaluator Oracle)
  Branch:   Node 5A (Accept) | Node 5B/5C (Sandbox Repair & Verified Mutate) | Node 5D (Escalate)

Safety Policy:
  - Default: READ-ONLY analysis with unified diff preview.
  - Mutations: Require explicit opt-in via '--apply' or '--repair-apply'.
  - Isolation: All proposed patches are verified in a scratch sandbox before target mutation.
  - Rollback: Pre-mutation snapshots ensure rollback on any mutation failure.

Timeout Semantics:
  Static evaluator timeouts operate as a soft timeout status boundary (TIMED_OUT),
  not preemptive kernel thread cancellation. Downstream nodes are skipped and execution proceeds.

Usage:
    python run_loop.py <target_skill_dir> [options]

Options:
    --apply                  Apply verified repair patches to disk (default: read-only diffs)
    --repair-apply           Alias for --apply
    --target-score <int>     Target static quality score to pass oracle (default: 95)
    --max-iterations <int>   Maximum loop iterations before escalation (default: 3)
    --no-auto-fix            Disable automated repair proposals
    --dry-run                Simulate loop execution without modifying disk
    --receipt-dir <path>     Directory to save evaluation receipts (default: <skill>/.audit_receipts)
    --scorecard <path>       Save populated audit scorecard markdown on acceptance
    --json                   Print run receipt JSON to stdout
    --verbose, -v            Print detailed per-node logs
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure utf-8 stdout in Windows environments
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure src/ is importable
SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Ensure scripts/ is importable for audit_skill scorecard generator
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import seg
from seg.evaluators import build_default_evaluation_dag
from seg.models import GateResult, OracleVerdict, RunStatus
from seg.oracle import EvaluatorOracle, synthesize_joined_evidence
from seg.receipts import compute_tree_digest, generate_evaluation_receipt, sha256_digest
from seg.repair.isolator import RepairIsolator
from seg.repair.planner import plan_repairs

from audit_skill import audit_skill, generate_scorecard


class EvaluatorLoopEngine:
    def __init__(
        self,
        skill_dir: Path,
        target_score: int = 95,
        max_iterations: int = 3,
        apply_mutations: Optional[bool] = None,
        auto_fix: bool = True,
        dry_run: bool = False,
        receipt_dir: Optional[Path] = None,
        scorecard_path: Optional[Path] = None,
        verbose: bool = False,
    ):
        self.skill_dir = skill_dir.resolve()
        self.target_score = target_score
        self.max_iterations = max_iterations
        self.auto_fix = auto_fix
        # Read-only by default: apply_mutations strictly requires explicit authorization.
        # auto_fix derives and verifies candidates in sandbox; apply_mutations controls disk writes.
        self.apply_mutations = False if apply_mutations is None else bool(apply_mutations)
        self.dry_run = dry_run
        self.scorecard_path = scorecard_path
        self.verbose = verbose

        self.receipt_dir = (
            receipt_dir.resolve()
            if receipt_dir
            else (self.skill_dir / ".audit_receipts")
        )
        self.run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.skill_name = self.skill_dir.name
        self.run_id = f"audit-run-{self.skill_name}-{self.run_timestamp}"

        # State tracking
        self.iterations_log: List[Dict[str, Any]] = []
        self.repair_actions: List[Dict[str, Any]] = []
        self.final_status = "PENDING"
        self.final_score = 0
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None

    def log(self, msg: str, prefix: str = "[INFO]") -> None:
        if self.verbose or prefix in ["[ORACLE]", "[GRAPH]", "[ACCEPT]", "[REVISE]", "[ESCALATE]", "[NOTICE]", "[PATCH]"]:
            print(f"{prefix} {msg}")

    # -------------------------------------------------------------------------
    # Node 1: Intake & Scope Verification (Chain)
    # -------------------------------------------------------------------------
    def node_1_intake(self) -> Tuple[bool, Dict[str, Any]]:
        self.log(f"Entering Node 1: Intake & Scope Verification for '{self.skill_dir}'", "[GRAPH]")
        if not self.skill_dir.exists() or not self.skill_dir.is_dir():
            return False, {"error": f"Path '{self.skill_dir}' is not an existing directory"}

        skill_md = self.skill_dir / "SKILL.md"
        if not skill_md.exists():
            return False, {"error": f"Missing mandatory SKILL.md in '{self.skill_dir}'"}

        inventory: List[str] = []
        for p in sorted(self.skill_dir.rglob("*")):
            if p.is_file() and not any(part.startswith((".", "__")) for part in p.parts):
                inventory.append(str(p.relative_to(self.skill_dir)))

        return True, {
            "skill_dir": str(self.skill_dir),
            "file_count": len(inventory),
            "inventory": inventory,
        }

    # -------------------------------------------------------------------------
    # Main Loop Runner
    # -------------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        print("\n" + "=" * 70)
        print("SEG: SKILL EVALUATION GRAPH - AUTONOMOUS EVALUATOR LOOP")
        print(f"Run ID:        {self.run_id}")
        print(f"Target Skill:  {self.skill_name} ({self.skill_dir})")
        print(f"Target Score:  {self.target_score} / 100")
        print(f"Max Iterations: {self.max_iterations}")
        mode_str = "MUTATION ALLOWED (--apply)" if self.apply_mutations else "READ-ONLY (Default; pass --apply to commit)"
        print(f"Safety Mode:   {mode_str}")
        print("=" * 70 + "\n")

        # Step 1: Intake
        valid, intake_data = self.node_1_intake()
        if not valid:
            self.final_status = RunStatus.FAILED.value
            return {
                "run_id": self.run_id,
                "status": "FAILED",
                "error": intake_data.get("error"),
            }

        evaluated_tree_digest = compute_tree_digest(self.skill_dir)
        generated_artifacts: List[Dict[str, Any]] = []

        current_iteration = 0
        last_results: Optional[Dict[str, Any]] = None
        last_evidence: Optional[JoinedEvidence] = None
        last_decision: Optional[OracleDecision] = None
        terminal_result: Optional[Dict[str, Any]] = None

        while current_iteration < self.max_iterations:
            current_iteration += 1
            print(f"\n>>> ITERATION {current_iteration} / {self.max_iterations} START <<<")

            # Node 2: Execute modular parallel evaluation DAG
            self.log("Entering Node 2: Parallel Evaluator DAG Execution", "[GRAPH]")
            dag = build_default_evaluation_dag()
            node_results = dag.execute(self.skill_dir)
            last_results = node_results

            # Node 3: Synthesize joined evidence
            self.log("Entering Node 3: Joining Multi-Node Evidence", "[GRAPH]")
            evidence = synthesize_joined_evidence(node_results)
            last_evidence = evidence

            # Node 4: Multi-Gate Evaluator Oracle
            oracle = EvaluatorOracle(
                target_score=self.target_score,
                max_iterations=self.max_iterations,
            )
            decision = oracle.evaluate(evidence, iteration=current_iteration)
            last_decision = decision

            self.log(
                f"Oracle Evaluation (Iteration {current_iteration}/{self.max_iterations}): "
                f"Score={evidence.static_quality_score}/{self.target_score}, "
                f"Findings={len(evidence.total_findings)}, BrokenLinks={len(evidence.broken_links)}",
                "[ORACLE]",
            )

            iter_record: Dict[str, Any] = {
                "iteration": current_iteration,
                "target_tree_digest": compute_tree_digest(self.skill_dir),
                "score_before": evidence.static_quality_score,
                "broken_links": len(evidence.broken_links),
                "oracle_decision": decision.verdict.value,
                "oracle_verdict": decision.verdict.value,
                "reasons": decision.reasons,
                "node_results": [r.to_dict() for r in node_results.values()],
                "joined_evidence": evidence.to_dict(),
                "patches_applied": [],
            }

            # Branching Logic based on Oracle Decision
            if decision.verdict == OracleVerdict.ACCEPT:
                self.log(f"Oracle Verdict: ACCEPT (Score {evidence.static_quality_score} >= {self.target_score})", "[ACCEPT]")
                scorecard_out = None
                if self.scorecard_path:
                    out_file = self.scorecard_path
                    if not out_file.is_absolute():
                        out_file = self.skill_dir / out_file
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    report = audit_skill(self.skill_dir)
                    generate_scorecard(report, out_file)
                    scorecard_out = str(out_file)
                    self.log(f"Delivered Scorecard to: {scorecard_out}", "[ACCEPT]")
                    if out_file.exists():
                        sc_bytes = out_file.read_bytes()
                        try:
                            rel_path = str(out_file.resolve().relative_to(self.skill_dir))
                        except Exception:
                            rel_path = out_file.name
                        generated_artifacts.append({
                            "type": "scorecard",
                            "path": rel_path,
                            "digest": sha256_digest(sc_bytes),
                            "size_bytes": len(sc_bytes),
                        })

                status_val = RunStatus.MUTATED.value if self.repair_actions else RunStatus.COMPLETED.value
                terminal_result = {
                    "verdict": OracleVerdict.ACCEPT.value,
                    "status": status_val,
                    "score": evidence.static_quality_score,
                    "scorecard_path": scorecard_out,
                    "message": "Skill satisfies all quality gates and structural invariants.",
                }
                self.final_status = status_val
                self.final_score = evidence.static_quality_score
                self.iterations_log.append(iter_record)
                break

            elif decision.verdict == OracleVerdict.REVISE:
                self.log("Oracle Verdict: REVISE -> Planning deterministic repairs...", "[REVISE]")
                if not self.auto_fix:
                    self.log("Auto-fix disabled (--no-auto-fix). Halting automated repair loop.", "[REVISE]")
                    terminal_result = {
                        "verdict": OracleVerdict.REVISE.value,
                        "status": RunStatus.ABORTED.value,
                        "score": evidence.static_quality_score,
                        "message": "Automated patching disabled by user flag.",
                    }
                    self.final_status = RunStatus.ABORTED.value
                    self.final_score = evidence.static_quality_score
                    self.iterations_log.append(iter_record)
                    break

                proposals = plan_repairs(self.skill_dir, evidence.total_findings)
                if not proposals:
                    self.log("No automated repair proposals could be derived for current findings.", "[REVISE]")
                    iter_record["patches_applied"] = []
                    self.iterations_log.append(iter_record)
                    if current_iteration >= self.max_iterations:
                        terminal_result = {
                            "verdict": OracleVerdict.ESCALATE.value,
                            "status": RunStatus.ESCALATED.value,
                            "score": evidence.static_quality_score,
                            "reasons": decision.reasons,
                        }
                        self.final_status = RunStatus.ESCALATED.value
                        self.final_score = evidence.static_quality_score
                        break
                    continue

                # Stage proposals in scratch sandbox and verify before application
                isolator = RepairIsolator(self.skill_dir)
                try:
                    sandbox_path, diff_str = isolator.stage_in_sandbox(proposals)
                    if not diff_str:
                        self.log("Staged patches resulted in an empty diff. Skipping candidate.", "[REVISE]")
                        iter_record["patches_applied"] = []
                        self.iterations_log.append(iter_record)
                        continue

                    # Re-evaluate candidate inside sandbox using DAG and Oracle to verify improvement before exposing diff
                    self.log(f"Re-evaluating candidate repairs inside sandbox '{sandbox_path.name}'...", "[VERIFY]")
                    candidate_dag = build_default_evaluation_dag()
                    candidate_results = candidate_dag.execute(sandbox_path, max_workers=2)
                    candidate_evidence = synthesize_joined_evidence(candidate_results)
                    candidate_oracle = EvaluatorOracle(target_score=self.target_score, max_iterations=self.max_iterations)
                    candidate_decision = candidate_oracle.evaluate(candidate_evidence, iteration=current_iteration)

                    # Gate-Regression & Invariant Protection via Oracle:
                    # 1. Gate 0 Evaluation Integrity must pass
                    candidate_gate_0 = next((g for g in candidate_decision.gate_results if g.gate_id == "evaluation_integrity"), None)
                    integrity_ok = bool(candidate_gate_0 and candidate_gate_0.passed)

                    # 2. Mandatory gates that passed in baseline MUST NOT regress to FAIL
                    baseline_gates_by_id = {g.gate_id: g for g in decision.gate_results if g.mandatory}
                    candidate_gates_by_id = {g.gate_id: g for g in candidate_decision.gate_results if g.mandatory}
                    regressed_gates = [
                        gid for gid, bg in baseline_gates_by_id.items()
                        if bg.passed and not candidate_gates_by_id.get(gid, GateResult(gid, "", False, "")).passed and gid != "quality_policy"
                    ]
                    gates_preserved = integrity_ok and (len(regressed_gates) == 0)

                    # 3. Removing old errors must not hide a newly introduced error.
                    # Ignore line shifts but preserve rule, file, category and message identity.
                    orig_errors = Counter(
                        (f.rule_id, f.file, f.category, f.message)
                        for f in evidence.total_findings if f.severity == "ERROR"
                    )
                    cand_errors = Counter(
                        (f.rule_id, f.file, f.category, f.message)
                        for f in candidate_evidence.total_findings if f.severity == "ERROR"
                    )
                    new_errors = cand_errors - orig_errors
                    errors_ok = not new_errors

                    # 4. Static Quality Score or findings count must strictly improve without score regression
                    score_or_findings_improved = (
                        candidate_evidence.static_quality_score > evidence.static_quality_score
                        or (
                            len(candidate_evidence.total_findings) < len(evidence.total_findings)
                            and candidate_evidence.static_quality_score >= evidence.static_quality_score
                        )
                    )

                    is_improved = gates_preserved and errors_ok and score_or_findings_improved

                    if not is_improved:
                        rejection_reasons = []
                        if not integrity_ok:
                            rejection_reasons.append("integrity gate failed")
                        if regressed_gates:
                            rejection_reasons.append(f"mandatory gate(s) regressed: {', '.join(regressed_gates)}")
                        if not errors_ok:
                            rejection_reasons.append(f"{sum(new_errors.values())} new error finding(s) introduced")
                        if not score_or_findings_improved:
                            rejection_reasons.append(f"score/findings not improved ({evidence.static_quality_score} -> {candidate_evidence.static_quality_score})")

                        self.log(
                            f"Candidate repair failed sandbox verification ({', '.join(rejection_reasons)}): "
                            f"candidate score={candidate_evidence.static_quality_score} (was {evidence.static_quality_score}), "
                            f"findings={len(candidate_evidence.total_findings)} (was {len(evidence.total_findings)}). Discarding candidate.",
                            "[REVISE]",
                        )
                        iter_record["patches_applied"] = []
                        self.iterations_log.append(iter_record)
                        if current_iteration >= self.max_iterations:
                            terminal_result = {
                                "verdict": OracleVerdict.ESCALATE.value,
                                "status": RunStatus.ESCALATED.value,
                                "score": evidence.static_quality_score,
                                "reasons": decision.reasons + ["Candidate repairs failed sandbox verification"],
                            }
                            self.final_status = RunStatus.ESCALATED.value
                            self.final_score = evidence.static_quality_score
                            break
                        continue

                    self.log(
                        f"Candidate repair VERIFIED in sandbox via Oracle: score improved from {evidence.static_quality_score} "
                        f"to {candidate_evidence.static_quality_score} (findings: {len(evidence.total_findings)} -> {len(candidate_evidence.total_findings)}).",
                        "[VERIFY]",
                    )

                    print("\n" + "-" * 40 + " VERIFIED REPAIR DIFF " + "-" * 40)
                    print(diff_str)
                    print("-" * 102 + "\n")

                    if self.apply_mutations and not self.dry_run:
                        success = isolator.apply_to_target_with_rollback()
                        if success:
                            applied_list = [p.to_dict() for p in proposals]
                            iter_record["patches_applied"] = applied_list
                            self.repair_actions.extend(applied_list)
                            self.log(f"Applied {len(applied_list)} verified patch(es) with rollback protection to disk.", "[PATCH]")
                            evaluated_tree_digest = compute_tree_digest(self.skill_dir)
                        else:
                            self.log("Mutation aborted or failed; target was unchanged or restored from its snapshot.", "[NOTICE]")
                    else:
                        self.log(
                            "Default READ-ONLY mode: Staged repairs verified and previewed above. Target files untouched on disk.",
                            "[NOTICE]",
                        )
                        self.log(
                            "To commit verified repairs in-place with rollback protection, run: python scripts/run_loop.py . --apply",
                            "[NOTICE]",
                        )
                        terminal_result = {
                            "verdict": OracleVerdict.REVISE.value,
                            "status": RunStatus.PREVIEWED.value,
                            "score": evidence.static_quality_score,
                            "verified_candidate_score": candidate_evidence.static_quality_score,
                            "diff": diff_str,
                            "proposals": [p.to_dict() for p in proposals],
                            "message": "Repairs verified in sandbox and previewed. Pass --apply to mutate disk.",
                        }
                        self.final_status = RunStatus.PREVIEWED.value
                        self.final_score = evidence.static_quality_score
                        self.iterations_log.append(iter_record)
                        break
                finally:
                    isolator.cleanup()

                self.iterations_log.append(iter_record)

            elif decision.verdict == OracleVerdict.ESCALATE:
                self.log(f"Oracle Verdict: ESCALATE (Iteration ceiling or critical invariant failure)", "[ESCALATE]")
                blockers = [f"[{f.severity}][{f.category}] {f.message}" for f in evidence.total_findings if f.severity in ["ERROR", "WARNING"]]
                terminal_result = {
                    "verdict": OracleVerdict.ESCALATE.value,
                    "status": RunStatus.ESCALATED.value,
                    "score": evidence.static_quality_score,
                    "target_score": self.target_score,
                    "exhausted_iterations": current_iteration,
                    "blockers": blockers,
                    "reasons": decision.reasons,
                    "message": "Evaluator loop reached termination criteria without meeting passing threshold.",
                }
                self.final_status = RunStatus.ESCALATED.value
                self.final_score = evidence.static_quality_score
                self.iterations_log.append(iter_record)
                break

        if terminal_result is None and last_evidence:
            terminal_result = {
                "verdict": OracleVerdict.ESCALATE.value,
                "status": RunStatus.ESCALATED.value,
                "score": last_evidence.static_quality_score,
                "target_score": self.target_score,
                "exhausted_iterations": current_iteration,
                "reasons": last_decision.reasons if last_decision else [],
            }
            self.final_status = RunStatus.ESCALATED.value
            self.final_score = last_evidence.static_quality_score

        self.end_time = datetime.now(timezone.utc)
        duration_secs = round((self.end_time - self.start_time).total_seconds(), 2)

        # Generate tamper-evident canonical evaluation receipt
        receipt = generate_evaluation_receipt(
            run_id=self.run_id,
            target_skill_path=self.skill_dir,
            config={
                "target_score": self.target_score,
                "max_iterations": self.max_iterations,
                "apply_mutations": self.apply_mutations,
                "dry_run": self.dry_run,
                "duration_seconds": duration_secs,
            },
            node_results=[r.to_dict() for r in last_results.values()] if last_results else [],
            joined_evidence=last_evidence.to_dict() if last_evidence else {},
            oracle_decision=last_decision.to_dict() if last_decision else {},
            repair_actions=self.repair_actions,
            iterations_log=self.iterations_log,
            terminal_result=terminal_result,
            final_status=self.final_status,
            final_score=self.final_score,
            total_iterations=current_iteration,
            input_tree_digest=evaluated_tree_digest,
            generated_artifacts=generated_artifacts,
        )

        # Save receipt to disk
        try:
            self.receipt_dir.mkdir(parents=True, exist_ok=True)
            receipt_file = self.receipt_dir / f"{self.run_id}.json"
            receipt_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            receipt["receipt_file"] = str(receipt_file)
            self.log(f"Tamper-evident evaluation receipt saved to: {receipt_file}", "[RECEIPT]")
        except Exception as exc:
            self.log(f"Failed to write receipt file: {exc}", "[ERROR]")

        self.print_summary(receipt)
        return receipt

    def print_summary(self, receipt: Dict[str, Any]) -> None:
        sep = "=" * 70
        print("\n" + sep)
        print(f"EVALUATOR LOOP EXECUTION SUMMARY: {receipt['run_id']}")
        print(sep)
        print(f"Final Status:     {receipt['final_status']}")
        print(f"Final Score:      {receipt['final_score']} / 100 (Target: {self.target_score})")
        print(f"Iterations Executed:  {len(receipt.get('iterations_log', []))} / {self.max_iterations}")
        config = receipt.get("configuration", {}).get("values", {})
        print(f"Total Duration:   {config.get('duration_seconds', 0)}s")
        if "receipt_file" in receipt:
            print(f"Run Receipt:      {receipt['receipt_file']}")
        if "receipt_digest" in receipt:
            print(f"Receipt Digest:   sha256:{receipt['receipt_digest'][:16]}...")
        print(sep)

        # ASCII Graph Trace
        print("Workflow Graph Trace:")
        trace = ["[Node 1: Intake & Scope]"]
        for it in receipt.get("iterations_log", []):
            idx = it["iteration"]
            score = it["score_before"]
            decision = it["oracle_decision"]
            trace.append(f"[Iter {idx}: Parallel DAG Evaluators -> Evidence Join ({score}/100)]")
            if decision == "ACCEPT":
                trace.append("──► [Node 4: Oracle: ACCEPT] ──► [Node 5A: Accept & Scorecard Delivered]")
            elif decision == "REVISE":
                patch_count = len(it.get("patches_applied", []))
                mode = "Applied" if self.apply_mutations else "Previewed (Read-Only)"
                trace.append(f"──► [Node 4: Oracle: REVISE] ──► [Node 5B/5C: {mode} {patch_count} Patches] ──► (Iteration)")
            elif decision == "ESCALATE":
                trace.append("──► [Node 4: Oracle: ESCALATE] ──► [Node 5D: Escalate to Human]")

        print("  " + " \n   │\n   ▼\n  ".join(trace))
        print(sep + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SEG: Autonomous Evaluator Loop & Graph Orchestrator for Agent Skills."
    )
    parser.add_argument("target_dir", type=Path, help="Path to the skill directory")
    parser.add_argument(
        "--apply",
        "--repair-apply",
        action="store_true",
        dest="apply",
        help="Apply verified repair mutations to target skill files (default: read-only diffs)",
    )
    parser.add_argument(
        "--target-score",
        type=int,
        default=95,
        help="Target static quality score to pass oracle (default: 95)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum loop iterations before escalation (default: 3)",
    )
    parser.add_argument(
        "--no-auto-fix",
        action="store_true",
        help="Disable automatic deterministic patching in Node 5C",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate loop execution without writing changes to disk",
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        help="Custom directory to store run receipts (default: <target_dir>/.audit_receipts)",
    )
    parser.add_argument(
        "--scorecard",
        type=Path,
        help="Path to generate finalized audit scorecard markdown upon acceptance",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output raw receipt JSON to stdout",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed execution logs",
    )
    args = parser.parse_args()

    engine = EvaluatorLoopEngine(
        skill_dir=args.target_dir,
        target_score=args.target_score,
        max_iterations=args.max_iterations,
        apply_mutations=args.apply,
        auto_fix=not args.no_auto_fix,
        dry_run=args.dry_run,
        receipt_dir=args.receipt_dir,
        scorecard_path=args.scorecard,
        verbose=args.verbose,
    )

    receipt = engine.run()

    if args.json_mode:
        print(json.dumps(receipt, indent=2))

    return 0 if receipt.get("final_status") in [RunStatus.COMPLETED.value, RunStatus.MUTATED.value] else 1


if __name__ == "__main__":
    sys.exit(main())
