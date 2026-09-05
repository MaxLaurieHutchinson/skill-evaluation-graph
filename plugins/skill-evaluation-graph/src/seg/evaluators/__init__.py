"""
__init__.py - Evaluators package for SEG.
"""

from seg.evaluators.base import BaseEvaluatorNode, parse_frontmatter, estimate_tokens
from seg.evaluators.schema import SchemaEvaluatorNode
from seg.evaluators.trigger_routing import TriggerRoutingEvaluatorNode
from seg.evaluators.links_syntax import LinksSyntaxEvaluatorNode, extract_markdown_links
from seg.evaluators.tokens import TokensEvaluatorNode
from seg.evaluators.safety_privacy import SafetyPrivacyEvaluatorNode
from seg.evaluators.portability import PortabilityEvaluatorNode
from seg.evaluators.behaviour_policy import BehaviourPolicyEvaluatorNode
from seg.graph import DAG


def build_default_evaluation_dag() -> DAG:
    """
    Construct the canonical SEG evaluation DAG with explicit nodes and dependencies:
    - Wave 1 (Root parallel diamond): schema, links_syntax, safety_privacy
    - Wave 2 (Dependent nodes): portability, trigger_routing, token_economics, behaviour_policy
    """
    dag = DAG("SEG Default Evaluation DAG")

    # Independent leaf nodes (Wave 1)
    dag.add_node(SchemaEvaluatorNode("schema"))
    dag.add_node(LinksSyntaxEvaluatorNode("links_syntax"))
    dag.add_node(SafetyPrivacyEvaluatorNode("safety_privacy"))

    # Dependent nodes (Wave 2)
    dag.add_node(PortabilityEvaluatorNode("portability"))         # depends on schema
    dag.add_node(TriggerRoutingEvaluatorNode("trigger_routing"))  # depends on schema
    dag.add_node(TokensEvaluatorNode("token_economics"))          # depends on schema
    dag.add_node(BehaviourPolicyEvaluatorNode("behaviour_policy"))# depends on schema

    return dag
