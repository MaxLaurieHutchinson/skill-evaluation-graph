"""
runner.py - Control vs Treatment behavioral trial runner and statistical analyzer for SEG.
"""

from __future__ import annotations

import re
import statistics
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from seg.behaviour.harnesses.base import BaseHarnessAdapter, HarnessResponse


class BehavioralTrialRunner:
    """
    Executes repeated Control vs. Treatment trials against an AI agent harness.
    Measures compliance rates, uplift (delta), rationalization resistance, and variance.
    """

    def __init__(
        self,
        skill_dir: Path,
        harness: BaseHarnessAdapter,
        scenarios: List[Dict[str, Any]],
        trials: int = 3,
        timeout: int = 60,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.skill_dir = skill_dir.resolve()
        self.harness = harness
        self.scenarios = scenarios
        self.trials = max(1, trials)
        self.timeout = timeout
        self.log_callback = log_callback

    def _log(self, msg: str, prefix: str = "[BEHAVIOUR]") -> None:
        if self.log_callback:
            self.log_callback(msg, prefix)

    def evaluate_response(self, text: Optional[str], scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Classify harness response against scenario compliance and violation markers."""
        safe_text = text or ""
        comp_hits = [p for p in scenario.get("compliance_markers", []) if re.search(p, safe_text, re.IGNORECASE)]
        viol_hits = [p for p in scenario.get("violation_markers", []) if re.search(p, safe_text, re.IGNORECASE)]

        rat_hits: List[str] = []
        for r in scenario.get("known_rationalizations", []):
            words = r.lower().split()
            if sum(1 for w in words if w in safe_text.lower()) >= max(2, len(words) // 2):
                rat_hits.append(r)

        is_compliant = len(comp_hits) > 0 and len(viol_hits) == 0
        return {
            "compliant": is_compliant,
            "compliance_hits": comp_hits,
            "violation_hits": viol_hits,
            "rationalization_hits": rat_hits,
        }

    def run_suite(self) -> Dict[str, Any]:
        """Execute the full battery of scenarios across Control and Treatment arms."""
        self._log(f"Starting behavioral evaluation: {len(self.scenarios)} scenarios, {self.trials} trial(s) per arm")

        temp_root = Path(tempfile.mkdtemp(prefix="seg_eval_suite_"))
        scenario_results: List[Dict[str, Any]] = []

        try:
            # Prepare workspaces for Control and Treatment
            control_ws = self.harness.prepare_workspace(self.skill_dir, temp_root, is_treated=False)
            treated_ws = self.harness.prepare_workspace(self.skill_dir, temp_root, is_treated=True)

            for sc_idx, sc in enumerate(self.scenarios, 1):
                sc_id = sc.get("id", f"scenario_{sc_idx}")
                sc_name = sc.get("name", sc_id)
                self._log(f"Running Scenario {sc_idx}/{len(self.scenarios)}: '{sc_name}'")

                control_runs: List[Dict[str, Any]] = []
                treated_runs: List[Dict[str, Any]] = []

                # 1. Control Trials
                for t in range(1, self.trials + 1):
                    resp = self.harness.run_prompt(control_ws, sc["prompt"], timeout=self.timeout)
                    is_infra_error = (resp.exit_code != 0 or resp.error_message is not None)
                    eval_res = self.evaluate_response(resp.response_text, sc) if not is_infra_error else {
                        "compliant": False,
                        "compliance_hits": [],
                        "violation_hits": [],
                        "rationalization_hits": [],
                    }
                    control_runs.append({
                        "trial": t,
                        "status": "INVALID_TRIAL" if is_infra_error else "VALID",
                        "compliant": eval_res["compliant"] if not is_infra_error else False,
                        "latency_sec": resp.latency_sec,
                        "token_usage": resp.token_usage,
                        "exit_code": resp.exit_code,
                        "error_message": resp.error_message,
                        "raw_response": resp.response_text,
                        "rationalizations": eval_res["rationalization_hits"],
                    })

                # 2. Treatment Trials
                for t in range(1, self.trials + 1):
                    resp = self.harness.run_prompt(treated_ws, sc["prompt"], timeout=self.timeout)
                    is_infra_error = (resp.exit_code != 0 or resp.error_message is not None)
                    eval_res = self.evaluate_response(resp.response_text, sc) if not is_infra_error else {
                        "compliant": False,
                        "compliance_hits": [],
                        "violation_hits": [],
                        "rationalization_hits": [],
                    }
                    treated_runs.append({
                        "trial": t,
                        "status": "INVALID_TRIAL" if is_infra_error else "VALID",
                        "compliant": eval_res["compliant"] if not is_infra_error else False,
                        "latency_sec": resp.latency_sec,
                        "token_usage": resp.token_usage,
                        "exit_code": resp.exit_code,
                        "error_message": resp.error_message,
                        "raw_response": resp.response_text,
                        "rationalizations": eval_res["rationalization_hits"],
                    })

                # Compute statistics over valid trials only to prevent manufactured uplift
                v_control = [r for r in control_runs if r["status"] == "VALID"]
                v_treated = [r for r in treated_runs if r["status"] == "VALID"]

                c_comp_rate = (sum(1 for r in v_control if r["compliant"]) / float(len(v_control))) if v_control else 0.0
                t_comp_rate = (sum(1 for r in v_treated if r["compliant"]) / float(len(v_treated))) if v_treated else 0.0
                uplift = (t_comp_rate - c_comp_rate) if (v_control and v_treated) else 0.0

                t_latencies = [r["latency_sec"] for r in v_treated]
                mean_latency = statistics.mean(t_latencies) if t_latencies else 0.0
                std_latency = statistics.stdev(t_latencies) if len(t_latencies) > 1 else 0.0

                scenario_results.append({
                    "scenario_id": sc_id,
                    "scenario_name": sc_name,
                    "trials": self.trials,
                    "valid_control_trials": len(v_control),
                    "valid_treated_trials": len(v_treated),
                    "control_compliance_rate": round(c_comp_rate, 4),
                    "treated_compliance_rate": round(t_comp_rate, 4),
                    "uplift": round(uplift, 4),
                    "mean_latency_sec": round(mean_latency, 4),
                    "std_latency_sec": round(std_latency, 4),
                    "control_runs": control_runs,
                    "treated_runs": treated_runs,
                })

        finally:
            self.harness.cleanup(temp_root)

        # Compute overall suite statistics
        overall_c_rate = statistics.mean([s["control_compliance_rate"] for s in scenario_results]) if scenario_results else 0.0
        overall_t_rate = statistics.mean([s["treated_compliance_rate"] for s in scenario_results]) if scenario_results else 0.0
        overall_uplift = overall_t_rate - overall_c_rate

        total_invalid = sum(
            (s["trials"] - s["valid_control_trials"]) + (s["trials"] - s["valid_treated_trials"])
            for s in scenario_results
        )

        verdict = "PASS" if overall_t_rate >= 0.8 and overall_uplift >= 0.0 and total_invalid == 0 else "FAIL"

        return {
            "harness": self.harness.name,
            "scenarios_evaluated": len(scenario_results),
            "trials_per_scenario": self.trials,
            "total_infrastructure_failures": total_invalid,
            "overall_control_compliance": round(overall_c_rate, 4),
            "overall_treated_compliance": round(overall_t_rate, 4),
            "overall_uplift": round(overall_uplift, 4),
            "verdict": verdict,
            "scenarios": scenario_results,
        }
