"""
base.py - Base evaluator node interface and shared evaluation utilities for SEG.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from seg.graph import BaseNode
from seg.models import Finding, NodeResult, NodeStatus
from seg.receipts import compute_tree_digest, sha256_digest


def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Parse YAML frontmatter, failing closed when YAML cannot be validated."""
    match = re.match(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|\Z)", content, re.MULTILINE | re.DOTALL)
    if match is None:
        return None, content
    body = content[match.end():]
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required: install the package's requirements.txt") from exc
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, body
    return (data if isinstance(data, dict) else None), body


def estimate_tokens(text: str) -> int:
    """Fast approximation of token count based on character and word ratio."""
    chars = len(text)
    words = len(text.split())
    by_chars = chars / 4.0
    by_words = words * 1.3
    return int((by_chars + by_words) / 2.0)


class BaseEvaluatorNode(BaseNode):
    """Base class for all discrete skill evaluators."""

    def __init__(self, node_id: str, dependencies: Optional[List[str]] = None):
        super().__init__(node_id=node_id, dependencies=dependencies)

    def compute_input_digest(self, paths: List[Path]) -> str:
        """Compute SHA256 digest over the set of files inspected by this evaluator."""
        hashes: List[str] = []
        for p in sorted(paths):
            if p.exists() and p.is_file():
                try:
                    h = sha256_digest(p.read_bytes())
                    hashes.append(f"{p.name}:{h}")
                except Exception:
                    pass
        return sha256_digest("\n".join(hashes).encode("utf-8")) if hashes else ""
