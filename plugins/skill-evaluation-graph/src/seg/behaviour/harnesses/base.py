"""
base.py - Base HarnessAdapter abstract interface and response structures for SEG.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class HarnessResponse:
    response_text: str = ""
    latency_sec: float = 0.0
    exit_code: int = 0
    token_usage: Dict[str, int] = field(default_factory=dict)
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and self.error_message is None


class BaseHarnessAdapter(ABC):
    """Abstract interface for driving AI agent harnesses during behavioral evaluation."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def prepare_workspace(self, skill_dir: Path, workspace_root: Path, is_treated: bool) -> Path:
        """Set up an isolated workspace sandbox, optionally installing the target skill."""
        pass

    @abstractmethod
    def run_prompt(self, workspace_path: Path, prompt: str, timeout: int = 60) -> HarnessResponse:
        """Run an adversarial or discipline prompt inside the workspace and capture the response."""
        pass

    @abstractmethod
    def cleanup(self, workspace_path: Path) -> None:
        """Clean up temporary workspace assets."""
        pass
