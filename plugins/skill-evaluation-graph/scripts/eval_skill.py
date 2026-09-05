#!/usr/bin/env python3
"""
eval_skill.py - Behavioral Pressure-Testing & Loophole Evaluation for Agent Skills.

Supports two evaluation modes:
  1. Static Policy Mode (Default): Analyzes skill documentation deterministically to verify
     that completion invariants, red flag checklists, and anti-rationalization tables are bound.
  2. Live Benchmark Mode (--live): Runs repeated Control vs. Treatment trials against an agent harness
     (FakeHarnessAdapter or live CodexHarnessAdapter) to measure behavioral compliance uplift and variance.

Usage:
    python eval_skill.py <path_to_skill> [options]

Options:
    --live                    Run live multi-trial behavioral evaluation against an agent harness
    --harness <name>          Harness adapter for live mode: 'fake' (default) or 'codex'
    --scenarios <path>        Path to custom scenario JSON file or directory containing scenarios
    --trials <int>            Number of evaluation repetitions per scenario arm (default: 3)
    --timeout <int>           Per-trial timeout in seconds (default: 60)
    --receipt-dir <path>      Directory to save tamper-evident evaluation receipt
    --json                    Print evaluation receipt JSON to stdout
    --verbose, -v             Verbose diagnostic logs
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
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

from seg.behaviour.harnesses.base import BaseHarnessAdapter
from seg.behaviour.harnesses.codex import CodexHarnessAdapter
from seg.behaviour.harnesses.fake import FakeHarnessAdapter
from seg.behaviour.runner import BehavioralTrialRunner
from seg.behaviour.scenarios import load_scenarios_from_dir, validate_scenario_schema
from seg.receipts import canonical_json_bytes, generate_evaluation_receipt, sha256_digest

# Compatibility API: defaults come from the distributed versioned catalogue.
DEFAULT_SCENARIOS = load_scenarios_from_dir(SRC_DIR.parent / "evaluations" / "scenarios")


def resolve_scenarios(scenarios_arg: Optional[Path], skill_dir: Path) -> List[Dict[str, Any]]:
    """Resolve scenarios from explicit argument, repository catalog, or built-in defaults."""
    if scenarios_arg:
        if scenarios_arg.is_dir():
            scs = load_scenarios_from_dir(scenarios_arg)
        elif scenarios_arg.is_file():
            try:
                data = json.loads(scenarios_arg.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"Cannot load scenarios {scenarios_arg}: {exc}") from exc
            scs = data if isinstance(data, list) else [data]
        else:
            raise ValueError(f"Scenario path does not exist: {scenarios_arg}")
        if not scs or not all(validate_scenario_schema(s) for s in scs):
            raise ValueError(f"Empty or invalid scenario catalogue: {scenarios_arg}")
        if len({s["id"] for s in scs}) != len(scs):
            raise ValueError(f"Duplicate scenario IDs: {scenarios_arg}")
        return scs

    # Check repository evaluation directory
    repo_scenarios_dir = skill_dir / "evaluations" / "scenarios"
    if repo_scenarios_dir.exists():
        return resolve_scenarios(repo_scenarios_dir, skill_dir)
    return resolve_scenarios(SRC_DIR.parent / "evaluations" / "scenarios", skill_dir)


class BehavioralEvaluationEngine:
    """Compatibility class wrapping SEG static policy evaluation and response scoring."""

    def __init__(
        self,
        skill_dir: Path,
        scenarios: Optional[List[Dict[str, Any]]] = None,
        trials: int = 3,
        receipt_dir: Optional[Path] = None,
        verbose: bool = False,
    ):
        self.skill_dir = skill_dir.resolve() if isinstance(skill_dir, Path) else Path(skill_dir).resolve()
        self.scenarios = scenarios or DEFAULT_SCENARIOS
        self.trials = trials
        self.receipt_dir = receipt_dir.resolve() if receipt_dir else (self.skill_dir / ".audit_receipts")
        self.verbose = verbose

    def evaluate_response(self, text: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Score text response against scenario compliance and violation markers."""
        comp_hits = [p for p in scenario.get("compliance_markers", []) if re.search(p, text, re.IGNORECASE)]
        viol_hits = [p for p in scenario.get("violation_markers", []) if re.search(p, text, re.IGNORECASE)]

        rat_hits: List[str] = []
        for r in scenario.get("known_rationalizations", []):
            words = r.lower().split()
            if sum(1 for w in words if w in text.lower()) >= max(2, len(words) // 2):
                rat_hits.append(r)

        is_compliant = len(comp_hits) > 0 and len(viol_hits) == 0
        return {
            "compliant": is_compliant,
            "compliance_hits": comp_hits,
            "violation_hits": viol_hits,
            "rationalization_hits": rat_hits,
        }

    def run_synthetic_benchmark(self) -> Dict[str, Any]:
        return run_static_policy_evaluation(
            skill_dir=self.skill_dir,
            scenarios=self.scenarios,
            receipt_dir=self.receipt_dir,
            verbose=self.verbose,
        )


def run_static_policy_evaluation(
    skill_dir: Path,
    scenarios: List[Dict[str, Any]],
    receipt_dir: Path,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates whether the skill's text deterministically addresses known rationalizations
    and binds explicit behavioral directives.
    """
    skill_dir = skill_dir.resolve()
    skill_name = skill_dir.name
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    eval_id = f"eval-static-{skill_name}-{run_timestamp}"

    skill_md = skill_dir / "SKILL.md"
    skill_text = ""
    if skill_md.exists():
        skill_text = skill_md.read_text(encoding="utf-8-sig", errors="ignore")

    refs_dir = skill_dir / "references"
    all_context = skill_text
    if refs_dir.exists():
        for ref_file in refs_dir.glob("*.md"):
            try:
                all_context += "\n" + ref_file.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                pass

    results: List[Dict[str, Any]] = []
    passed_scenarios = 0

    for sc in scenarios:
        sc_id = sc["id"]
        sc_name = sc["name"]
        baseline_violations = sc.get("known_rationalizations", [])

        covered_counters: List[str] = []
        uncovered_counters: List[str] = []

        for rat in baseline_violations:
            key_terms = [w for w in rat.lower().split() if len(w) > 3]
            found_counter = any(term in all_context.lower() for term in key_terms)
            if found_counter:
                covered_counters.append(rat)
            else:
                uncovered_counters.append(rat)

        rule_bound = any(re.search(p, all_context, re.IGNORECASE) for p in sc["compliance_markers"])
        scenario_passed = rule_bound or len(covered_counters) >= max(1, len(baseline_violations) // 2)

        if scenario_passed:
            passed_scenarios += 1
            verdict = "PASS"
        else:
            verdict = "GAP_DETECTED"

        if verbose:
            print(f"[STATIC] Scenario '{sc_name}': {verdict} (Countered {len(covered_counters)}/{len(baseline_violations)} rationalizations)")

        results.append({
            "scenario_id": sc_id,
            "scenario_name": sc_name,
            "category": sc.get("category", "GENERAL"),
            "verdict": verdict,
            "rule_explicitly_bound": rule_bound,
            "covered_rationalizations": covered_counters,
            "uncovered_rationalizations": uncovered_counters,
        })

    compliance_rate = round((passed_scenarios / len(scenarios)) * 100, 1) if scenarios else 0.0
    overall_verdict = "ACCEPTED" if compliance_rate >= 66.0 else "REVISE"

    receipt = generate_evaluation_receipt(
        run_id=eval_id,
        target_skill_path=skill_dir,
        config={
            "mode": "static_policy",
            "scenarios_count": len(scenarios),
        },
        joined_evidence={
            "compliance_rate_percent": compliance_rate,
            "passed_scenarios": passed_scenarios,
            "total_scenarios": len(scenarios),
            "scenarios_evaluated": results,
        },
        oracle_decision={
            "verdict": overall_verdict,
            "reasons": [] if overall_verdict == "ACCEPTED" else ["Static compliance rate below 66% threshold"],
        },
    )

    receipt["verdict"] = overall_verdict
    receipt["compliance_rate_percent"] = compliance_rate
    # Compatibility fields are part of the saved payload and must be hashed too.
    del receipt["receipt_digest"]
    receipt["receipt_digest"] = sha256_digest(canonical_json_bytes(receipt))

    # Save receipt to disk
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{eval_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt["receipt_file"] = str(receipt_path)

    # Print summary
    print("\n" + "=" * 70)
    print(f"SKILL BEHAVIORAL POLICY EVALUATION (STATIC): {eval_id}")
    print("=" * 70)
    print(f"Target Skill:      {skill_name}")
    print(f"Evaluation Mode:   Static Policy Analysis")
    print(f"Overall Verdict:   {overall_verdict}")
    print(f"Compliance Rate:   {compliance_rate}% ({passed_scenarios}/{len(scenarios)} scenarios passed)")
    print(f"Receipt Digest:    sha256:{receipt['receipt_digest'][:16]}...")
    print("=" * 70)
    for s in results:
        sym = "[x]" if s["verdict"] == "PASS" else "[ ]"
        print(f"  {sym} [{s['category']}] {s['scenario_name']}: {s['verdict']}")
        if s["uncovered_rationalizations"]:
            print(f"      Remaining rationalization gaps: {', '.join(s['uncovered_rationalizations'][:2])}")
    print("=" * 70 + "\n")

    return receipt


def run_live_behavioral_benchmark(
    skill_dir: Path,
    harness: BaseHarnessAdapter,
    scenarios: List[Dict[str, Any]],
    trials: int,
    timeout: int,
    receipt_dir: Path,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Executes live multi-trial behavioral evaluation (Control vs Treatment)
    using the specified harness adapter.
    """
    skill_dir = skill_dir.resolve()
    skill_name = skill_dir.name
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    eval_id = f"eval-live-{harness.name}-{skill_name}-{run_timestamp}"

    def log_cb(msg: str, prefix: str = "[BEHAVIOUR]") -> None:
        if verbose or prefix in ["[BEHAVIOUR]", "[RESULT]", "[VERDICT]"]:
            print(f"{prefix} {msg}")

    runner = BehavioralTrialRunner(
        skill_dir=skill_dir,
        harness=harness,
        scenarios=scenarios,
        trials=trials,
        timeout=timeout,
        log_callback=log_cb,
    )

    suite_result = runner.run_suite()

    receipt = generate_evaluation_receipt(
        run_id=eval_id,
        target_skill_path=skill_dir,
        config={
            "mode": "live_trial_benchmark",
            "harness": harness.name,
            "trials_per_arm": trials,
            "timeout_sec": timeout,
            "scenarios_count": len(scenarios),
        },
        joined_evidence=suite_result,
        oracle_decision={
            "verdict": suite_result["verdict"],
            "reasons": [] if suite_result["verdict"] == "PASS" else ["Treatment compliance or uplift below threshold"],
        },
    )

    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{eval_id}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt["receipt_file"] = str(receipt_path)

    # Print summary
    print("\n" + "=" * 70)
    print(f"SKILL BEHAVIORAL TRIAL BENCHMARK (LIVE): {eval_id}")
    print("=" * 70)
    print(f"Target Skill:          {skill_name}")
    print(f"Harness Adapter:       {harness.name}")
    print(f"Trials per Scenario:   {trials} per arm (Control vs. Treatment)")
    print(f"Control Compliance:    {round(suite_result['overall_control_compliance'] * 100, 1)}%")
    print(f"Treated Compliance:    {round(suite_result['overall_treated_compliance'] * 100, 1)}%")
    print(f"Measured Uplift (Δ):   +{round(suite_result['overall_uplift'] * 100, 1)}%")
    print(f"Overall Verdict:       {suite_result['verdict']}")
    print(f"Receipt Digest:        sha256:{receipt['receipt_digest'][:16]}...")
    print("=" * 70)
    for sc in suite_result.get("scenarios", []):
        c_rate = round(sc["control_compliance_rate"] * 100, 1)
        t_rate = round(sc["treated_compliance_rate"] * 100, 1)
        lat = sc["mean_latency_sec"]
        print(f"  * {sc['scenario_name']}: Control={c_rate}% -> Treatment={t_rate}% (Latency: {lat:.2f}s)")
    print("=" * 70 + "\n")

    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SEG: Behavioral Pressure-Testing & Loophole Evaluation for Agent Skills."
    )
    parser.add_argument("skill_dir", type=Path, help="Path to skill directory")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute live multi-trial behavioral evaluation against an agent harness",
    )
    parser.add_argument(
        "--harness",
        choices=["fake", "codex"],
        default="fake",
        help="Harness adapter for live mode: 'fake' (default, deterministic offline) or 'codex' (live Codex CLI)",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        help="Path to custom scenario JSON file or directory containing scenarios",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Number of repetitions per scenario arm in live mode (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-trial timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        help="Custom directory to store tamper-evident evaluation receipts",
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
        help="Enable detailed diagnostic logs",
    )
    args = parser.parse_args()

    skill_path = args.skill_dir.resolve()
    if not skill_path.exists() or not skill_path.is_dir():
        print(f"Error: Target path '{skill_path}' does not exist or is not a directory.", file=sys.stderr)
        return 1

    receipt_dir = args.receipt_dir.resolve() if args.receipt_dir else (skill_path / ".audit_receipts")
    try:
        scenarios = resolve_scenarios(args.scenarios, skill_path)
    except ValueError as exc:
        parser.error(str(exc))

    if args.live:
        # Live multi-trial benchmark mode
        if args.harness == "codex":
            harness = CodexHarnessAdapter()
        else:
            harness = FakeHarnessAdapter()

        receipt = run_live_behavioral_benchmark(
            skill_dir=skill_path,
            harness=harness,
            scenarios=scenarios,
            trials=args.trials,
            timeout=args.timeout,
            receipt_dir=receipt_dir,
            verbose=args.verbose,
        )
        verdict = receipt.get("oracle_decision", {}).get("verdict")
        success = verdict == "PASS"
    else:
        # Static policy mode (default)
        receipt = run_static_policy_evaluation(
            skill_dir=skill_path,
            scenarios=scenarios,
            receipt_dir=receipt_dir,
            verbose=args.verbose,
        )
        verdict = receipt.get("oracle_decision", {}).get("verdict")
        success = verdict == "ACCEPTED"

    if args.json_mode:
        print(json.dumps(receipt, indent=2))

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
