# SEG Canonical Engineering Vocabulary & Domain Reference

This document establishes the official, authoritative terminology for the **Skill Evaluation Graph (SEG)** project.

> [!IMPORTANT]
> **Contributor Directive**: Use this document as SEG's canonical vocabulary. Do not introduce synonyms for defined concepts without updating this glossary. When creating or refactoring code, comments, docstrings, or documentation, adhere strictly to the canonical terms.

---

## 1. Canonical Vocabulary Table

| Canonical Term | Meaning | Avoid Using Interchangeably |
|:---|:---|:---|
| **SEG** | The product, evaluation method, and autonomous evaluator loop architecture. | Skill Auditor (historical repo name only) |
| **Evaluation Run** | One complete invocation of SEG from intake to terminal scorecard/receipt. | audit run, job, execution session |
| **Evaluation Pass** | One execution of the evaluation DAG against one discrete target state. | cycle, phase, stage |
| **Evaluation Graph** | The acyclic graph of evaluator dependencies executed during an Evaluation Pass. | workflow, pipeline, flow |
| **Evaluator** | One independently attributable evaluation node assessing a single concern. | checker, validator, sub-audit, inspection script |
| **Node Result** | Structured output (`NodeResult`) produced by an Evaluator node. | report, check output |
| **Evidence** | Observable, verifiable, or measured facts extracted from target files or trials. | finding, conclusion |
| **Finding** | An interpretation of evidence identifying a defect, risk, or recommendation (`Finding`). | evidence, error loosely |
| **Evidence Join** | Deterministic aggregation of required Node Results into `JoinedEvidence`. | merge, synthesis node, aggregator |
| **Gate** | One explicit, deterministic pass/fail predicate evaluated over joined evidence. | oracle, check |
| **Oracle** | The decision component that evaluates all Gates to return an authoritative Verdict. | Oracle Gate, decider, judge |
| **Verdict** | An authoritative Oracle decision: `ACCEPT`, `REVISE`, or `ESCALATE`. | pass, fail, reject used ad hoc |
| **Invariant** | A non-negotiable rule or structural gate that may never be violated regardless of score. | recommendation, soft rule |
| **Static Quality Score** | A heuristic numerical quality signal ($0\text{--}100$) derived from static evaluator findings. | structural score (deprecated alias), validity, grade |
| **Repair Proposal** | A discrete, deterministic proposed modification derived from findings (`PatchProposal`). | patch loosely |
| **Repair Sandbox** | An isolated temporary staging workspace where candidate repairs are exercised. | temp dir, scratch space |
| **Repair Candidate** | The modified skill state resulting from applying proposals inside the Repair Sandbox. | patched skill, draft |
| **Repair Verification** | Re-evaluation of a Repair Candidate using the DAG and Oracle before authorizing mutation. | validation, check |
| **Repair Iteration** | One complete sequence: propose $\rightarrow$ stage in sandbox $\rightarrow$ verify $\rightarrow$ optional apply $\rightarrow$ re-evaluate. | phase, retry loop |
| **Behavioural Scenario** | A versioned behavioural stimulus prompt and its observable expectations. | test prompt, synthetic query |
| **Trial** | One execution of one scenario in one arm (Control or Treatment). | evaluation, run |
| **Control Arm** | A trial executed without the target skill active (baseline agent behavior). | baseline loosely |
| **Treatment Arm** | A trial executed with the target skill loaded and active in the agent workspace. | test run, experiment |
| **Uplift** | The difference in compliance rate between Treatment and Control arms ($\text{Uplift} = \text{Treated} - \text{Control}$). | improvement generally |
| **Invalid Trial** | A trial invalidated by infrastructure, harness, or timeout failure (excluded from compliance rates). | behavioural failure, test failure |
| **Harness** | The host execution environment running the agent (e.g. OpenAI Codex, Claude Code, Antigravity). | model, runtime |
| **Harness Interface** | The abstract contract (`BaseHarnessAdapter`) required for harness integration. | API loosely, driver contract |
| **Harness Seam** | The precise boundary at which harness execution can be substituted without altering core logic. | adapter boundary |
| **Adapter** | Concrete implementation of the Harness Interface (e.g. `CodexHarnessAdapter`, `FakeHarnessAdapter`). | plugin, integration |
| **Specification Conformance** | Whether external authoritative format and schema requirements pass (e.g. YAML, JSON schemas). | quality, score |
| **Static Quality** | Deterministic heuristics and code hygiene measured by static evaluators. | compliance, score |
| **Behavioural Reliability** | Empirical agent compliance observed across live, repeated behavioural trials. | static coverage |
| **Portability Evidence** | Verifiable proof of support across host harnesses (Packaging, Manifests, Adapters). | universal compatibility |

---

## 2. Seam vs. Boundary: Precise Distinction

SEG adopts **Michael Feathers'** definition of a **Seam**:
> *A seam is a place where you can alter behavior in your program without editing in that place.*

In SEG, the word **Seam** is reserved for substitutable and observable interfaces:
1. **Harness Seam**: The interface where concrete execution hosts (Codex, Claude, Antigravity, Fake) can be swapped without touching the behavioral trial runner or DAG engine.
2. **Behavioural Test Seam**: The public boundary where scenario prompts enter and observable agent artifacts/stdout exit. Behavioral trials test observable outputs across this seam—they never inspect internal model hidden states or chain-of-thought tokens.

In contrast, the word **Boundary** is reserved for non-substitutable security, authority, and scope limits:
- **Authority Boundary**: What SEG is authorized to do (e.g. read-only analysis vs. disk mutation).
- **Trust Boundary**: The line separating local repository execution from external network or subagent execution.
- **Mutation Boundary**: The boundary between isolated scratch staging and the live target skill on disk.
- **Scope Boundary**: The filesystem boundary enclosing the target skill package (`<skill-dir>`).

---

## 3. Multi-Axis Evaluation Model

Rather than collapsing all evaluation dimensions into a single heuristic score, SEG evaluates skills along independent, orthogonal axes.

```text
┌─────────────────────────────────────────────────────────────┐
│                 SEG EVALUATION REPORT                       │
├──────────────────────────────┬──────────────────────────────┤
│ Specification Conformance    │ PASS (Gate 1)                │
│ Evaluation Integrity         │ PASS (Gate 0)                │
│ Safety & Authority           │ PASS (Gate 2)                │
│ Link & Asset Integrity       │ PASS (Gate 3)                │
│ Static Quality Score         │ 98 / 100 (Supporting Signal) │
│ Behavioural Reliability      │ 100% Treatment Compliance    │
│ Behavioural Uplift           │ +83.3% vs Control Arm        │
│ Portability Evidence         │ Codex: Manifest Validated    │
│                              │ Claude: Manifest Validated   │
│                              │ Antigravity: Agent Skill Compatible │
├──────────────────────────────┼──────────────────────────────┤
│ Authoritative Verdict        │ ACCEPT                       │
└──────────────────────────────┴──────────────────────────────┘
```

### Core Principle: The Gates Own Acceptance
- A score of $100/100$ does **not** grant acceptance if an Invariant or mandatory Gate fails.
- Score is a supporting heuristic signal; Gates define the non-negotiable floor of engineering integrity.

---

## 4. Finding Provenance Categories

Every finding generated by an Evaluator belongs to one of three provenance categories (`FindingKind`), tracked with optional citation metadata (`authority`, `source_url`, `source_version`):

1. **`SPECIFICATION_ERROR`**:
   - Violation of an authoritative external standard (e.g. Agent Skills specification, OpenAI Plugin Marketplace schema, valid YAML syntax, RFC-compliant relative links).
   - These are non-negotiable structural defects that fail mandatory Gates.

2. **`SEG_RECOMMENDATION`**:
   - Opinionated best practices and conventions established by SEG (e.g. keeping `SKILL.md` under 300 lines, organizing reference manuals in `references/`, isolating templates in `assets/`, including anti-rationalization tables for active discipline skills).
   - These represent design guidelines that deduct points from the Static Quality Score rather than failing specification gates.

3. **`OBSERVED_FAILURE`**:
   - Empirical, measured failures during execution (e.g. a broken relative link target that does not exist on disk, a timeout during a behavioral trial, a command execution error).

---

## 5. Stable Gate Identifiers

SEG defines 5 canonical, machine-readable Gate IDs evaluated by the Oracle in sequence:

| Stable Gate ID | Display Name | Purpose & Invariant | Requirement Level |
|:---|:---|:---|:---|
| `evaluation_integrity` | Evaluation Integrity Gate | Evaluates that all evaluator nodes succeeded with `NodeStatus.SUCCESS` (zero crashes, timeouts, or unexpected skips). | Mandatory (Gate 0) |
| `specification_conformance` | Specification Conformance Gate | Evaluates that no evaluator emitted a finding of kind `SPECIFICATION_ERROR` (frontmatter, naming, schemas, manifests). | Mandatory (Gate 1) |
| `safety_privacy` | Operational Safety & Privacy Gate | Evaluates zero API secrets, workstation path leaks (`C:\Users`), or unshielded shell injection/destructors. | Mandatory (Gate 2) |
| `link_integrity` | Relative Link Integrity Gate | Evaluates that all local relative Markdown links and assets resolve to existing files on disk. | Mandatory (Gate 3) |
| `quality_policy` | SEG Quality Policy Gate | Evaluates that the heuristic Static Quality Score meets or exceeds the configured target score (default: 95/100). | Threshold (Gate 4) |
