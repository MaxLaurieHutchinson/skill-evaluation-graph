"""
scenarios.py - Scenario catalog loader and schema validator for SEG behavioral evaluations.
"""

from __future__ import annotations

import json
import re
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
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot load scenario {json_path}: {exc}") from exc
        if not validate_scenario_schema(data):
            raise ValueError(f"Invalid scenario schema: {json_path}")
        if any(s["id"] == data["id"] for s in scenarios):
            raise ValueError(f"Duplicate scenario id: {data['id']}")
        scenarios.append(data)

    return scenarios


def validate_scenario_schema(scenario: Dict[str, Any]) -> bool:
    """Validate that a scenario dictionary complies with the required schema."""
    if not isinstance(scenario, dict):
        return False
    required_fields = [
        "id",
        "name",
        "category",
        "prompt",
        "expected_action",
    ]
    for rf in required_fields:
        if not isinstance(scenario.get(rf), str) or not scenario[rf].strip():
            return False
    for field in ("compliance_markers", "violation_markers"):
        markers = scenario.get(field)
        if not isinstance(markers, list) or (field == "compliance_markers" and not markers):
            return False
        for marker in markers:
            if not isinstance(marker, str) or not marker:
                return False
            try:
                re.compile(marker)
            except re.error:
                return False
    for field in ("version", "minimum_trials"):
        if field in scenario and (type(scenario[field]) is not int or scenario[field] < 1):
            return False
    for field in ("known_rationalizations", "pressures"):
        values = scenario.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            return False
    return True
