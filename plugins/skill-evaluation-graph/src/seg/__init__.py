"""
SEG - Skill Evaluation Graph
An evidence-driven evaluation graph for AI Agent Skills.
"""

__version__ = "1.0.2"  # x-release-please-version

from seg.models import (
    Finding,
    NodeResult,
    NodeStatus,
    JoinedEvidence,
    GateResult,
    OracleDecision,
    OracleVerdict,
    FileProfile,
)
from seg.graph import DAG, BaseNode
from seg.evaluators import build_default_evaluation_dag
from seg.oracle import EvaluatorOracle, synthesize_joined_evidence
from seg.receipts import generate_evaluation_receipt, save_receipt, compute_tree_digest
