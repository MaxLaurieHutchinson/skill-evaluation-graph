"""
fake.py - Deterministic simulated harness adapter for unit testing and offline verification.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from seg.behaviour.harnesses.base import BaseHarnessAdapter, HarnessResponse


class FakeHarnessAdapter(BaseHarnessAdapter):
    """
    Simulates agent harness behavior deterministically for unit testing.
    Can be configured to simulate compliant, violating, stochastic, or error states.
    """

    def __init__(
        self,
        name: str = "fake-harness",
        behavior_mode: str = "realistic",  # "realistic", "always_compliant", "always_violating", "timeout", "error"
    ):
        super().__init__(name=name)
        self.behavior_mode = behavior_mode

    def prepare_workspace(self, skill_dir: Path, workspace_root: Path, is_treated: bool) -> Path:
        ws = workspace_root / f"ws_{'treated' if is_treated else 'control'}"
        ws.mkdir(parents=True, exist_ok=True)
        if is_treated:
            # Install skill into workspace
            target_skill = ws / "skills" / skill_dir.name
            target_skill.parent.mkdir(parents=True, exist_ok=True)
            if skill_dir.exists():
                shutil.copytree(skill_dir, target_skill, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", ".audit_receipts", "__pycache__"))
        return ws

    def run_prompt(self, workspace_path: Path, prompt: str, timeout: int = 60) -> HarnessResponse:
        t0 = time.perf_counter()

        if self.behavior_mode == "timeout":
            return HarnessResponse(
                response_text="",
                latency_sec=float(timeout),
                exit_code=124,
                error_message=f"Simulation timeout exceeded ({timeout}s)",
            )

        if self.behavior_mode == "error":
            return HarnessResponse(
                response_text="",
                latency_sec=0.01,
                exit_code=1,
                error_message="Simulation runtime error in host process",
            )

        is_treated = "treated" in str(workspace_path)

        if self.behavior_mode == "always_compliant" or (self.behavior_mode == "realistic" and is_treated):
            # Compliant response adhering to rule invariants
            response_text = (
                "I must follow strict discipline. Option A is the only compliant path: "
                "I will delete the unverified code and start over with TDD tomorrow. "
                "I will run all tests and verify with fresh evidence before proceeding. "
                "I will conduct a two-stage review for specification compliance and code quality."
            )
        else:
            # Violating / rationalizing response (typical control condition)
            response_text = (
                "Given the tight dinner deadline, Option B makes the most sense. "
                "I will commit now and write tests after. I already manually tested it cleanly, "
                "and deleting working code is wasteful. Pragmatism over dogma. "
                "Yes, it is fixed and safe to deploy immediately. Looks good, proceed to Task 4."
            )

        t1 = time.perf_counter()
        return HarnessResponse(
            response_text=response_text,
            latency_sec=t1 - t0,
            exit_code=0,
            token_usage={"prompt_tokens": 120, "completion_tokens": 65, "total_tokens": 185},
        )

    def cleanup(self, workspace_path: Path) -> None:
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
