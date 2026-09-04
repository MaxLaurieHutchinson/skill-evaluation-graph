"""
receipts.py - Tamper-evident canonical evaluation receipt generation for SEG.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data into deterministic sorted compact JSON bytes (compact separators, sorted keys)."""
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_digest(data_bytes: bytes) -> str:
    """Compute SHA256 hex digest for given bytes."""
    return hashlib.sha256(data_bytes).hexdigest()


def compute_tree_digest(root_path: Path) -> str:
    """
    Compute a deterministic sorted tree-content SHA256 digest of all files in root_path,
    including manifest directories (.codex-plugin, .claude-plugin, .agents, .github),
    while ignoring .git, caches, backups, and ephemeral audit receipts.
    """
    if not root_path.exists() or not root_path.is_dir():
        return ""

    ignored_dirs = {".git", ".audit_receipts", ".seg_backup", "__pycache__", ".pytest_cache", ".venv", "venv"}
    ignored_exts = {".pyc", ".pyo", ".swp", ".DS_Store"}

    file_hashes: List[str] = []
    for file_path in sorted(root_path.rglob("*")):
        if file_path.is_file():
            rel = file_path.relative_to(root_path)
            # Exclude files inside ignored directories
            if any(part in ignored_dirs for part in rel.parts):
                continue
            # Exclude ignored file extensions and temp hidden files
            if file_path.suffix in ignored_exts or file_path.name.startswith("._"):
                continue

            try:
                content = file_path.read_bytes()
                rel_path = str(rel).replace("\\", "/")
                file_hash = sha256_digest(content)
                file_hashes.append(f"{rel_path}:{file_hash}")
            except Exception as exc:
                raise IOError(f"Failed to read file '{file_path}' while computing tree digest: {exc}") from exc

    tree_str = "\n".join(file_hashes)
    return sha256_digest(tree_str.encode("utf-8"))


def generate_evaluation_receipt(
    run_id: str,
    target_skill_path: Path,
    seg_version: str = "1.0.0",
    config: Optional[Dict[str, Any]] = None,
    node_results: Optional[List[Dict[str, Any]]] = None,
    joined_evidence: Optional[Dict[str, Any]] = None,
    oracle_decision: Optional[Dict[str, Any]] = None,
    repair_actions: Optional[List[Dict[str, Any]]] = None,
    iterations_log: Optional[List[Dict[str, Any]]] = None,
    terminal_result: Optional[Dict[str, Any]] = None,
    final_status: Optional[str] = None,
    final_score: Optional[int] = None,
    total_iterations: Optional[int] = None,
    input_tree_digest: Optional[str] = None,
    generated_artifacts: Optional[List[Dict[str, Any]]] = None,
    sanitize_paths: bool = True,
) -> Dict[str, Any]:
    """
    Generate a canonical, tamper-evident evaluation receipt.
    Includes input tree digest, configuration digest, execution outcomes,
    and computed receipt digest over the entire finalized payload.
    """
    tree_digest = input_tree_digest if input_tree_digest is not None else compute_tree_digest(target_skill_path)
    config_dict = config or {}
    config_digest = sha256_digest(canonical_json_bytes(config_dict))

    if sanitize_paths:
        try:
            rel = target_skill_path.resolve().relative_to(Path.cwd().resolve())
            clean_path = f"./{rel.as_posix()}"
        except Exception:
            clean_path = f"./{target_skill_path.name}"
    else:
        clean_path = str(target_skill_path.resolve())

    receipt: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "seg_version": seg_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": {
            "name": target_skill_path.name,
            "path": clean_path,
            "input_tree_digest": tree_digest,
        },
        "configuration": {
            "digest": config_digest,
            "values": config_dict,
        },
        "node_results": node_results or [],
        "joined_evidence": joined_evidence or {},
        "oracle_decision": oracle_decision or {},
        "repair_actions": repair_actions or [],
        "iterations_log": iterations_log or [],
        "generated_artifacts": generated_artifacts or [],
        "terminal_result": terminal_result or {},
        "final_status": final_status or "UNKNOWN",
        "final_score": final_score if final_score is not None else 0,
        "total_iterations": total_iterations if total_iterations is not None else 1,
    }

    # Compute tamper-evident receipt digest over complete canonical content
    receipt_bytes = canonical_json_bytes(receipt)
    receipt["receipt_digest"] = sha256_digest(receipt_bytes)
    return receipt


def save_receipt(receipt: Dict[str, Any], output_dir: Path) -> Path:
    """Save evaluation receipt to disk as JSON with canonical formatting."""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = receipt.get("run_id", "audit-run")
    receipt_file = output_dir / f"{run_id}.json"
    receipt_file.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt_file
