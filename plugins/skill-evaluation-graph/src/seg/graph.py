"""
graph.py - Directed Acyclic Graph (DAG) runtime engine & parallel scheduler for SEG.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path
import time

from seg.models import Finding, NodeResult, NodeStatus
from seg.receipts import sha256_digest, canonical_json_bytes


class BaseNode:
    """Abstract base class for all DAG evaluation nodes."""

    def __init__(
        self,
        node_id: str,
        dependencies: Optional[List[str]] = None,
        timeout_sec: Optional[float] = None,
    ):
        self.node_id = node_id
        self.dependencies: List[str] = dependencies or []
        self.timeout_sec: Optional[float] = timeout_sec

    def execute(self, skill_path: Path, context: Dict[str, Any]) -> NodeResult:
        """Execute node evaluation logic. Must be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement execute()")


class DAG:
    """
    Executable Directed Acyclic Graph supporting dependency resolution,
    parallel wave execution, cycle detection, and Mermaid/Text rendering.
    """

    def __init__(self, name: str = "Skill Evaluation Graph"):
        self.name = name
        self.nodes: Dict[str, BaseNode] = {}
        self.edges: List[tuple[str, str]] = []  # (from_node, to_node)

    def add_node(self, node: BaseNode) -> None:
        """Register a node and wire its explicit dependency edges, rejecting duplicate node IDs."""
        if node.node_id in self.nodes:
            raise ValueError(f"Malformed graph: duplicate node ID '{node.node_id}' already registered")
        self.nodes[node.node_id] = node
        for dep in node.dependencies:
            if (dep, node.node_id) not in self.edges:
                self.edges.append((dep, node.node_id))

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Manually add a dependency edge, rejecting unregistered nodes."""
        if from_node not in self.nodes:
            raise ValueError(f"Malformed graph: cannot add edge from unregistered node '{from_node}'")
        if to_node not in self.nodes:
            raise ValueError(f"Malformed graph: cannot add edge to unregistered node '{to_node}'")
        if (from_node, to_node) not in self.edges:
            self.edges.append((from_node, to_node))
        if from_node not in self.nodes[to_node].dependencies:
            self.nodes[to_node].dependencies.append(from_node)

    def topological_sort(self) -> List[str]:
        """
        Kahn's algorithm for topological sorting and cycle detection.
        Validates graph well-formedness: rejects unregistered node dependencies.
        Returns ordered list of node IDs.
        """
        # Reject malformed graphs referencing unregistered nodes
        for node_id, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise ValueError(f"Malformed graph: node '{node_id}' depends on unregistered node '{dep}'")

        for u, v in self.edges:
            if u not in self.nodes:
                raise ValueError(f"Malformed graph: edge references unregistered source node '{u}'")
            if v not in self.nodes:
                raise ValueError(f"Malformed graph: edge references unregistered target node '{v}'")

        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        adj_list: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes}

        for u, v in self.edges:
            if u in in_degree and v in in_degree:
                adj_list[u].append(v)
                in_degree[v] += 1

        queue = [node_id for node_id, deg in in_degree.items() if deg == 0]
        ordered: List[str] = []

        while queue:
            curr = queue.pop(0)
            ordered.append(curr)
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(self.nodes):
            unvisited = set(self.nodes.keys()) - set(ordered)
            raise ValueError(f"Cycle detected in evaluation graph. Unvisited nodes: {unvisited}")

        return ordered

    def get_execution_waves(self) -> List[List[str]]:
        """
        Group nodes into parallel execution waves where all dependencies
        of wave[i] are satisfied by wave[0...i-1].
        """
        # Ensure graph is acyclic before computing waves
        self.topological_sort()

        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        adj_list: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes}

        for u, v in self.edges:
            if u in in_degree and v in in_degree:
                adj_list[u].append(v)
                in_degree[v] += 1

        ready = [node_id for node_id, deg in in_degree.items() if deg == 0]
        waves: List[List[str]] = []

        while ready:
            waves.append(ready)
            next_ready: List[str] = []
            for curr in ready:
                for neighbor in adj_list[curr]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_ready.append(neighbor)
            ready = next_ready

        return waves

    def execute(
        self,
        skill_path: Path,
        context: Optional[Dict[str, Any]] = None,
        max_workers: int = 4,
        default_timeout_sec: Optional[float] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, NodeResult]:
        """
        Execute the DAG in parallel waves. Nodes in the same wave execute concurrently.

        Timeout Semantics:
            Evaluator timeouts operate as a soft timeout / status boundary. When a node exceeds
            its allocated timeout (node.timeout_sec or default_timeout_sec), the scheduler
            records NodeStatus.TIMED_OUT, downstream dependent nodes are skipped, and the
            scheduler proceeds to subsequent waves. Because standard Python threads cannot be
            forcibly killed, the underlying thread completes cooperatively in the background.
        """
        ctx = context.copy() if context else {}
        results: Dict[str, NodeResult] = {}
        waves = self.get_execution_waves()

        def _log(msg: str, prefix: str = "[GRAPH]") -> None:
            if log_callback:
                log_callback(msg, prefix)

        _log(f"Executing DAG '{self.name}' across {len(waves)} wave(s) ({len(self.nodes)} nodes total)")

        for wave_idx, wave in enumerate(waves, 1):
            _log(f"Wave {wave_idx}/{len(waves)}: executing [{', '.join(wave)}]")

            # Worker function for thread pool
            def _run_node(nid: str) -> tuple[str, NodeResult]:
                node = self.nodes[nid]
                start_iso = datetime.now(timezone.utc).isoformat()
                t0 = time.perf_counter()
                node_timeout = node.timeout_sec if node.timeout_sec is not None else default_timeout_sec
                # Check dependencies before running
                failed_deps = [
                    dep for dep in node.dependencies
                    if dep in results and results[dep].status != NodeStatus.SUCCESS
                ]
                if failed_deps:
                    res = NodeResult(
                        node_id=nid,
                        status=NodeStatus.SKIPPED,
                        error_message=f"Prerequisite dependency '{failed_deps[0]}' did not succeed",
                    )
                else:
                    if node_timeout is not None and node_timeout > 0:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as single_exec:
                            fut = single_exec.submit(node.execute, skill_path, ctx)
                            try:
                                res = fut.result(timeout=node_timeout)
                                if res.status in (None, NodeStatus.PENDING):
                                    res.status = NodeStatus.SUCCESS
                            except concurrent.futures.TimeoutError:
                                res = NodeResult(
                                    node_id=nid,
                                    status=NodeStatus.TIMED_OUT,
                                    error_message=f"Node '{nid}' execution timed out after {node_timeout}s",
                                )
                            except Exception as exc:
                                res = NodeResult(
                                    node_id=nid,
                                    status=NodeStatus.FAILED,
                                    error_message=str(exc),
                                )
                    else:
                        try:
                            res = node.execute(skill_path, ctx)
                            if res.status in (None, NodeStatus.PENDING):
                                res.status = NodeStatus.SUCCESS
                        except Exception as exc:
                            res = NodeResult(
                                node_id=nid,
                                status=NodeStatus.FAILED,
                                error_message=str(exc),
                            )
                t1 = time.perf_counter()
                res.start_time = start_iso
                res.end_time = datetime.now(timezone.utc).isoformat()
                res.duration_sec = t1 - t0

                # Compute complete output digest over node result
                digest_content = {
                    "node_id": res.node_id,
                    "status": res.status.value if isinstance(res.status, NodeStatus) else str(res.status),
                    "evidence": res.evidence,
                    "findings": [f.to_dict() for f in res.findings],
                    "metrics": res.metrics,
                    "error_message": res.error_message,
                }
                res.output_digest = sha256_digest(canonical_json_bytes(digest_content))
                return nid, res

            if len(wave) == 1 or max_workers <= 1:
                for nid in wave:
                    nid, res = _run_node(nid)
                    results[nid] = res
                    ctx[nid] = res
                    ctx[f"node_{nid}"] = res
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(wave))) as executor:
                    future_to_nid = {executor.submit(_run_node, nid): nid for nid in wave}
                    for future in concurrent.futures.as_completed(future_to_nid):
                        nid, res = future.result()
                        results[nid] = res
                        ctx[nid] = res
                        ctx[f"node_{nid}"] = res

        return results

    def get_execution_plan(self) -> List[List[str]]:
        """Alias for get_execution_waves."""
        return self.get_execution_waves()

    def render_mermaid(self) -> str:
        """Render the DAG structure in valid GitHub Mermaid flowchart format."""
        lines = ["flowchart TD", "    classDef default fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;"]
        for node_id, node in self.nodes.items():
            label = node_id.replace("_", " ").title()
            lines.append(f'    {node_id}["{label}"]')
        for u, v in self.edges:
            lines.append(f"    {u} --> {v}")
        return "\n".join(lines)

    def render_text(self) -> str:
        """Render a text representation of the DAG waves."""
        waves = self.get_execution_waves()
        lines = [f"=== DAG: {self.name} ==="]
        for idx, wave in enumerate(waves, 1):
            lines.append(f"  [Wave {idx}] -> {', '.join(wave)}")
        return "\n".join(lines)
