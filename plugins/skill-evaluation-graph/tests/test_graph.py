"""
test_graph.py - Tests for DAG orchestration, topological sort, and rendering.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from typing import Any, Dict, List

SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seg.graph import BaseNode, DAG
from seg.models import Finding, NodeResult, NodeStatus


class MockNode(BaseNode):
    def __init__(self, node_id: str, dependencies: List[str] = None, delay: float = 0.0):
        super().__init__(node_id=node_id, dependencies=dependencies or [])
        self.delay = delay
        self.executed = False

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        import time
        if self.delay > 0:
            time.sleep(self.delay)
        self.executed = True
        return NodeResult(
            node_id=self.node_id,
            findings=[Finding(severity="INFO", category="TEST", message=f"Executed {self.node_id}")],
            metrics={"executed": True, "deps_received": list(context.keys())},
        )


class FailingNode(BaseNode):
    def __init__(self, node_id: str, dependencies: List[str] = None, error_msg: str = "Simulated node crash"):
        super().__init__(node_id=node_id, dependencies=dependencies or [])
        self.error_msg = error_msg

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        raise RuntimeError(self.error_msg)


class TestDAGOrchestration(unittest.TestCase):
    def test_soft_timeout_does_not_wait_for_worker_before_next_wave(self):
        import threading
        release = threading.Event()
        finished = threading.Event()

        class BlockedNode(BaseNode):
            def execute(self, skill_path, context):
                release.wait(2)
                finished.set()
                return NodeResult(node_id=self.node_id)

        class ReleaseNode(BaseNode):
            def execute(self, skill_path, context):
                blocked_still_running = not finished.is_set()
                release.set()
                return NodeResult(node_id=self.node_id, metrics={"blocked_still_running": blocked_still_running})

        dag = DAG("soft-timeout")
        slow = BlockedNode("slow")
        slow.timeout_sec = 0.01
        dag.add_node(slow)
        dag.add_node(MockNode("ready"))
        dag.add_node(ReleaseNode("release", dependencies=["ready"]))
        try:
            results = dag.execute(Path("."))
            self.assertEqual(results["slow"].status, NodeStatus.TIMED_OUT)
            self.assertTrue(results["release"].metrics["blocked_still_running"])
        finally:
            release.set()
            finished.wait(2)

    def test_topological_sort_kahn(self):
        dag = DAG(name="test-kahn")
        n_a = MockNode("A", [])
        n_b = MockNode("B", ["A"])
        n_c = MockNode("C", ["A"])
        n_d = MockNode("D", ["B", "C"])

        dag.add_node(n_d)
        dag.add_node(n_c)
        dag.add_node(n_b)
        dag.add_node(n_a)

        waves = dag.get_execution_plan()
        self.assertEqual(len(waves), 3)
        self.assertEqual(waves[0], ["A"])
        self.assertEqual(sorted(waves[1]), ["B", "C"])
        self.assertEqual(waves[2], ["D"])

    def test_cycle_detection(self):
        dag = DAG(name="test-cycle")
        n1 = MockNode("node1", ["node2"])
        n2 = MockNode("node2", ["node1"])
        dag.add_node(n1)
        dag.add_node(n2)

        with self.assertRaises(ValueError) as ctx:
            dag.get_execution_plan()
        self.assertIn("Cycle detected", str(ctx.exception))

    def test_parallel_execution_and_context_passing(self):
        dag = DAG(name="test-exec")
        n1 = MockNode("init", [])
        n2a = MockNode("branch_a", ["init"], delay=0.02)
        n2b = MockNode("branch_b", ["init"], delay=0.02)
        n3 = MockNode("join", ["branch_a", "branch_b"])

        dag.add_node(n1)
        dag.add_node(n2a)
        dag.add_node(n2b)
        dag.add_node(n3)

        results = dag.execute(Path("."), max_workers=2)
        self.assertEqual(len(results), 4)
        self.assertTrue(n1.executed)
        self.assertTrue(n2a.executed)
        self.assertTrue(n2b.executed)
        self.assertTrue(n3.executed)

        # Verify n3 received contexts from its dependencies
        join_metrics = results["join"].metrics
        self.assertIn("branch_a", join_metrics["deps_received"])
        self.assertIn("branch_b", join_metrics["deps_received"])

    def test_mermaid_rendering(self):
        dag = DAG(name="test-mermaid")
        dag.add_node(MockNode("schema", []))
        dag.add_node(MockNode("links", ["schema"]))
        mermaid = dag.render_mermaid()

        self.assertIn("flowchart TD", mermaid)
        self.assertIn("schema --> links", mermaid)

    def test_text_rendering(self):
        dag = DAG(name="test-text")
        dag.add_node(MockNode("root", []))
        dag.add_node(MockNode("leaf", ["root"]))
        text = dag.render_text()

        self.assertIn("Wave 1", text)
        self.assertIn("Wave 2", text)
        self.assertIn("leaf", text)

    def test_prerequisite_failure_skips_dependent_nodes(self):
        dag = DAG(name="test-skip")
        n_fail = FailingNode("crasher", [])
        n_dep = MockNode("dependent", ["crasher"])
        n_indep = MockNode("independent", [])

        dag.add_node(n_fail)
        dag.add_node(n_dep)
        dag.add_node(n_indep)

        results = dag.execute(Path("."))
        self.assertEqual(results["crasher"].status, NodeStatus.FAILED)
        self.assertIn("Simulated node crash", results["crasher"].error_message)

        # Dependent node must be marked SKIPPED fail-closed
        self.assertEqual(results["dependent"].status, NodeStatus.SKIPPED)
        self.assertIn("crasher", results["dependent"].error_message)
        self.assertFalse(n_dep.executed)

        # Independent node executes normally
        self.assertEqual(results["independent"].status, NodeStatus.SUCCESS)
        self.assertTrue(n_indep.executed)

    def test_malformed_graph_rejection(self):
        dag = DAG(name="test-malformed")
        n_orphan = MockNode("orphan", ["unregistered_node"])
        dag.add_node(n_orphan)

        # Execution planning must reject unregistered dependency
        with self.assertRaises(ValueError) as ctx:
            dag.get_execution_plan()
        self.assertIn("unregistered node 'unregistered_node'", str(ctx.exception))

        # add_edge with unregistered nodes must be rejected
        with self.assertRaises(ValueError):
            dag.add_edge("ghost", "orphan")
        with self.assertRaises(ValueError):
            dag.add_edge("orphan", "ghost")

    def test_duplicate_node_id_rejection(self):
        dag = DAG(name="test-duplicate")
        dag.add_node(MockNode("node_x", []))
        with self.assertRaises(ValueError) as ctx:
            dag.add_node(MockNode("node_x", []))
        self.assertIn("already registered", str(ctx.exception))

    def test_node_execution_timeout(self):
        dag = DAG(name="test-timeout")
        slow_node = MockNode("slow", [], delay=0.2)
        slow_node.timeout_sec = 0.05
        dag.add_node(slow_node)

        results = dag.execute(Path("."))
        self.assertEqual(results["slow"].status, NodeStatus.TIMED_OUT)
        self.assertIn("timed out after 0.05s", results["slow"].error_message)

    def test_complete_node_result_digest(self):
        dag = DAG(name="test-digest")
        node = MockNode("digested", [])
        dag.add_node(node)

        results = dag.execute(Path("."))
        res = results["digested"]
        self.assertEqual(len(res.output_digest), 64)

        from seg.receipts import canonical_json_bytes, sha256_digest
        digest_content_1 = {
            "node_id": res.node_id,
            "status": res.status.value,
            "evidence": res.evidence,
            "findings": [f.to_dict() for f in res.findings],
            "metrics": res.metrics,
            "error_message": res.error_message,
        }
        self.assertEqual(res.output_digest, sha256_digest(canonical_json_bytes(digest_content_1)))


if __name__ == "__main__":
    unittest.main()
