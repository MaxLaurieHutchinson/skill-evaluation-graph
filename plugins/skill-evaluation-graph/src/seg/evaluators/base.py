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
    """Parse YAML frontmatter from markdown content with standard library fallback."""
    if not content.startswith("---"):
        return None, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    fm_text = parts[1]
    body = parts[2]

    try:
        import yaml
        data = yaml.safe_load(fm_text)
        if isinstance(data, dict):
            return data, body
    except Exception:
        pass

    # Regex fallback parser
    data = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
        if match:
            key, val = match.group(1), match.group(2).strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            data[key] = val

    return data if data else None, body


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
