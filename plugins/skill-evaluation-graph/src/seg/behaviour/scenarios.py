"""
scenarios.py - Scenario catalog loader and schema validator for SEG behavioral evaluations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_scenarios_from_dir(scenarios_dir: Path) -> List[Dict[str, Any]]:
    """Load and validate all scenario JSON files from a directory."""
    scenarios: List[Dict[str, Any]] = []
    if not scenarios_dir.exists() or not scenarios_dir.is_dir():
        return scenarios

    for json_path in sorted(scenarios_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8-sig"))
            if validate_scenario_schema(data):
                scenarios.append(data)
        except Exception:
            pass

    return scenarios


def validate_scenario_schema(scenario: Dict[str, Any]) -> bool:
    """Validate that a scenario dictionary complies with the required schema."""
    required_fields = [
        "id",
        "name",
        "category",
        "prompt",
        "expected_action",
        "compliance_markers",
        "violation_markers",
    ]
    for rf in required_fields:
        if rf not in scenario:
            return False
    if not isinstance(scenario["compliance_markers"], list) or not isinstance(scenario["violation_markers"], list):
        return False
    return True
