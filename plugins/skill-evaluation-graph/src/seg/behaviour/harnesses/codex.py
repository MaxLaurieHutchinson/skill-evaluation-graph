"""
codex.py - Live OpenAI Codex CLI harness adapter for SEG.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from seg.behaviour.harnesses.base import BaseHarnessAdapter, HarnessResponse


class CodexHarnessAdapter(BaseHarnessAdapter):
    """
    Drives the live OpenAI Codex CLI in an isolated harness configuration
    with explicitly bridged authentication.
    Requires 'codex' command to be installed and authenticated on the system.
    """

    def __init__(self, name: str = "codex"):
        super().__init__(name=name)

    def is_available(self) -> bool:
        """Check if 'codex' executable is available on PATH."""
        return shutil.which("codex") is not None

    def prepare_workspace(self, skill_dir: Path, workspace_root: Path, is_treated: bool) -> Path:
        ws = (workspace_root / f"codex_{'treated' if is_treated else 'control'}").resolve()
        ws.mkdir(parents=True, exist_ok=True)
        # Create isolated harness configuration directory so control doesn't see global skills
        isolated_home = ws / "_isolated_home"
        isolated_home.mkdir(parents=True, exist_ok=True)
        isolated_codex = isolated_home / ".codex"
        isolated_codex.mkdir(parents=True, exist_ok=True)

        # Minimum capability bridge: explicitly bridge only auth.json across the isolation seam
        # so authenticated runs can execute without exposing the user's global skills or config
        import os
        host_codex_home = os.environ.get("CODEX_HOME")
        candidate_auth_paths = []
        if host_codex_home:
            candidate_auth_paths.append(Path(host_codex_home) / "auth.json")
        candidate_auth_paths.append(Path.home() / ".codex" / "auth.json")
        for auth_candidate in candidate_auth_paths:
            if auth_candidate.exists() and auth_candidate.is_file():
                try:
                    shutil.copy2(auth_candidate, isolated_codex / "auth.json")
                    break
                except Exception:
                    pass

        if is_treated and skill_dir.exists():
            skill_target = ws / ".agents" / "skills" / skill_dir.name
            skill_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                skill_dir,
                skill_target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".git", ".audit_receipts", "__pycache__", "dist", ".seg_backup", "test_ws*"),
            )
        return ws

    def run_prompt(self, workspace_path: Path, prompt: str, timeout: int = 60) -> HarnessResponse:
        if not self.is_available():
            return HarnessResponse(
                response_text="",
                latency_sec=0.0,
                exit_code=127,
                error_message="Codex CLI ('codex') is not installed or not found on PATH.",
            )

        t0 = time.perf_counter()
        try:
            # Build hermetic environment variables
            import os
            env = os.environ.copy()
            isolated_home = (workspace_path / "_isolated_home").resolve()
            if isolated_home.exists():
                env["HOME"] = str(isolated_home)
                env["USERPROFILE"] = str(isolated_home)
                env["CODEX_HOME"] = str((isolated_home / ".codex").resolve())

            # Run codex exec inside the isolated workspace with clean environment
            codex_bin = shutil.which("codex") or "codex"
            proc = subprocess.run(
                [codex_bin, "exec", "--skip-git-repo-check", "--ephemeral", prompt],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                env=env,
                timeout=timeout,
                check=False,
            )
            t1 = time.perf_counter()
            return HarnessResponse(
                response_text=proc.stdout or "",
                latency_sec=t1 - t0,
                exit_code=proc.returncode,
                error_message=proc.stderr if proc.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            return HarnessResponse(
                response_text="",
                latency_sec=float(timeout),
                exit_code=124,
                error_message=f"Codex execution timed out after {timeout} seconds.",
            )
        except Exception as exc:
            return HarnessResponse(
                response_text="",
                latency_sec=time.perf_counter() - t0,
                exit_code=1,
                error_message=str(exc),
            )

    def cleanup(self, workspace_path: Path) -> None:
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
