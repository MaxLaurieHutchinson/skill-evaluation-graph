---
name: skill-evaluation-graph
description: Deeply analyze, audit, score, and optimize agent skills conforming to the Agent Skills standard or Antigravity/Codex/Claude formats. Use when reviewing an existing skill, diagnosing why an agent misfires or burns context, pruning skill bloat, refactoring monolithic instructions into progressive disclosure, or benchmarking skill quality. Do not use for creating skills from scratch without an existing procedure (use workflow-skill-creator).
---

# SEG: Skill Evaluation Graph: Procedural Driver for Agent Skill Audit & Optimization

Turn agent skills into reliable, token-efficient, production-grade engineering assets. Evaluates trigger precision, progressive disclosure architecture, behavioral steering, execution determinism, operational safety, and token economics.

---

## Quick Reference Matrix

| Concern | Purpose | Authoritative Resource |
|:---|:---|:---|
| **Canonical Terminology** | Authoritative vocabulary & domain definitions | [references/terminology.md](references/terminology.md) |
| **6-Pillar Audit Rubric** | Objective 1–5 scoring definitions | [references/audit-rubric.md](references/audit-rubric.md) |
| **Anti-Pattern Catalog** | Diagnostic guide for 14 recurring skill defects | [references/anti-patterns.md](references/anti-patterns.md) |
| **Context Engineering** | Multi-tier progressive disclosure patterns | [references/progressive-disclosure-patterns.md](references/progressive-disclosure-patterns.md) |
| **Evaluation Graph & Loop** | Autonomous Evaluator Loop Engine runbook | [references/workflow-graph-and-evaluator-loop.md](references/workflow-graph-and-evaluator-loop.md) |
| **Harness Compatibility** | Cross-platform tool mappings (Antigravity/Claude/Codex) | [references/harness-tool-matrix.md](references/harness-tool-matrix.md) |
| **Behavioral Trial Runner** | Control vs. Treatment evaluation & live trials | [scripts/eval_skill.py](scripts/eval_skill.py) |
| **Capability Claim Audit** | Technical reality & evidence classification | [references/claim-audit.md](references/claim-audit.md) |
| **Scorecard Template** | Standardized evaluation report template | [assets/skill-audit-scorecard-template.md](assets/skill-audit-scorecard-template.md) |
| **Example Scorecard** | Exemplary completed evaluation report | [assets/example-scorecard.md](assets/example-scorecard.md) |
| **Self-Audit Scorecard** | SEG self-audit baseline scorecard | [assets/self-audit-scorecard.md](assets/self-audit-scorecard.md) |
| **Standards Alignment** | Applied AI Wiki 14-step framework | [references/wiki-standard-alignment.md](references/wiki-standard-alignment.md) |
| **Agent Protection** | Anti-hallucination contributor contract | [assets/agent-contributor-contract-template.md](assets/agent-contributor-contract-template.md) |

> [!IMPORTANT]
> **Canonical Terminology**: Use [references/terminology.md](references/terminology.md) as SEG's canonical vocabulary. Do not introduce synonyms for defined concepts without updating the glossary.

---

## Workflow Graph Architecture

```text
[Node 1: Intake & Scope]
          │
          ▼
[Node 2: Parallel Evaluator DAG Execution]
  (Schema, Links, Tokens, Safety/Privacy, Portability, Trigger Routing, Behaviour Policy)
          │
          ▼
[Node 3: Joining Multi-Node Evidence]
          │
          ▼
[Node 4: Multi-Gate Evaluator Oracle]
          │
  ┌───────┼───────────────────────────────┐
  ▼       ▼                               ▼
[Node 5A: ACCEPT]              [Node 5B/5C: REVISE]            [Node 5D: ESCALATE]
(Scorecard & Receipt)  (Sandbox Verify -> Preview/Mutate)   (Human Attention Required)
```

---

## Procedural Execution Driver

Follow these steps in sequence when auditing or optimizing an agent skill:

### Step 1: Identify Target Skill & Verify Scope
1. Locate the target directory containing `SKILL.md`.
2. Inspect package inventory across `SKILL.md`, `references/`, `scripts/`, and `assets/`.
3. Verify host harness compatibility manifests (`.codex-plugin/plugin.json`, `CLAUDE.md`, `AGENTS.md`, `.agents/plugins/marketplace.json`).

### Step 2: Read Canonical Terminology
Consult [references/terminology.md](references/terminology.md) before logging findings. Ensure all feedback and reporting use exact canonical names (e.g. `Static Quality Score`, `Oracle Verdict`, `Evaluation Integrity Gate`, `Pre-mutation Snapshot`).

### Step 3: Execute Evaluation Graph
Run the modular parallel evaluation DAG via [scripts/run_loop.py](scripts/run_loop.py):
```powershell
# Read-only evaluation and diff preview (default)
python "<skill-dir>/scripts/run_loop.py" "<target-skill-path>" --target-score 95 --max-iterations 3

# With scorecard delivery upon acceptance
python "<skill-dir>/scripts/run_loop.py" "<target-skill-path>" --scorecard "<target-skill-path>/scorecard.md"
```

Evaluator nodes execute across parallel dependency waves:
- `schema`: Validates YAML frontmatter, naming, and required fields.
- `links_syntax`: Resolves relative links, single-hop rules, and code fences.
- `tokens`: Profiles token budget across the 5 progressive disclosure tiers.
- `safety_privacy`: Detects destructive commands and workstation path exposures.
- `portability`: Validates OpenAI Codex plugin and marketplace manifests.
- `trigger_routing`: Checks frontmatter description triggers and negative boundaries.
- `behaviour_policy`: Enforces anti-rationalization guidelines.

### Step 4: Join Evidence & Evaluate Gates
Evidence from all nodes is synthesized into `JoinedEvidence`. The `EvaluatorOracle` enforces 5 mandatory gates:
1. **Evaluation Integrity Gate (Gate 0)**: Fails closed if any evaluator encounters an unhandled error, times out, or skips unexpectedly.
2. **Specification Conformance Gate**: Fails if any node reports a `SPECIFICATION_ERROR` (e.g. invalid marketplace schema or broken frontmatter).
3. **Safety & Privacy Gate**: Fails on destructive commands or workstation path leaks.
4. **Link Integrity Gate**: Fails on broken relative markdown links.
5. **Static Quality Score Policy Gate**: Verifies overall score meets `--target-score` (default: 95).

### Step 5: Process Oracle Verdict
- **`ACCEPT` (Node 5A)**: All mandatory gates passed and static quality score $\ge 95$. Generate scorecard and evaluation receipt. Status: `COMPLETED` (or `MUTATED` if repairs were applied).
- **`REVISE` (Node 5B/5C)**: Fixable defects detected. Proceed to Step 6.
- **`ESCALATE` (Node 5D)**: Unresolvable blockers or iteration ceiling reached. Halts for human intervention with detailed blocker list. Status: `ESCALATED`.

### Step 6: Derive Repair, Verify in Sandbox, and Mutate With Authority
When the verdict is `REVISE`:
1. `plan_repairs()` derives deterministic patch proposals from findings.
2. `RepairIsolator` stages proposals in an isolated scratch sandbox (`tempfile.TemporaryDirectory`).
3. Candidate is re-evaluated inside the sandbox using the DAG and Oracle to verify:
   - Evaluation Integrity Gate passes.
   - Mandatory gates do not regress.
   - No new `ERROR` findings are introduced.
   - Static quality score or finding counts strictly improve.
4. If candidate passes verification:
   - **Default (Read-Only)**: Unified diff is displayed for human review. Target skill on disk remains untouched. Status: `PREVIEWED`.
   - **With `--apply`**: Verified patches are written to disk with pre-mutation snapshot protection (a uniquely named sibling recovery directory). Status: `MUTATED`.
5. The loop resumes for the next iteration until `ACCEPT` or max iterations exhausted.

### Step 7: Optionally Run Behavioral Trials
The bundled versioned catalogue is in `evaluations/scenarios/`. Install Python dependencies from `requirements.txt` before running SEG.

For dynamic validation of skill execution, run [scripts/eval_skill.py](scripts/eval_skill.py):
```powershell
# Offline simulation of anti-rationalization scenarios
python "<skill-dir>/scripts/eval_skill.py" "<target-skill-path>"

# Live authenticated Codex CLI trial with isolated home directory
python "<skill-dir>/scripts/eval_skill.py" "<target-skill-path>" --live --harness codex --trials 1 --timeout 90
```

### Step 8: Produce Evidence-Backed Scorecard
Generate the finalized audit scorecard via [scripts/audit_skill.py](scripts/audit_skill.py):
```powershell
python "<skill-dir>/scripts/audit_skill.py" "<target-skill-path>" --scorecard "<output-scorecard.md>"
```
The scorecard strictly projects measured evidence from the DAG and Oracle:
- Recommendation matches Oracle Verdict (`ACCEPT`, `REVISE`, `ESCALATE`).
- Measured rubric pillars project evaluator metrics.
- Unmeasured pillars explicitly report `NOT EVALUATED`.
- A tamper-evident evaluation receipt is saved with SHA256 digest over the finalized execution state.

---

## Quality Invariants

- **Zero Broken Links:** Every relative markdown link must resolve within the skill directory.
- **Strict Single-Hop:** No reference file may link to a secondary reference file.
- **Budget Compliance:** `SKILL.md` must not exceed 300 lines or 2500 tokens.
- **Self-Contained Portability:** Zero hardcoded machine paths or user home directories.
- **Evidence Integrity:** Scorecards and receipts must reflect verifiable evidence without fabricated scores.
