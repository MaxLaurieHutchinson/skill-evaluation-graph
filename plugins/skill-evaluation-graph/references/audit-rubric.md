# The 6-Pillar Agent Skill Audit Rubric

This rubric defines the objective evaluation standard for assessing, scoring, and improving agent skills. Every evaluated skill is rated on a 1–5 scale across each of the six core architectural pillars.

---

## Pillar 1: Trigger & Routing Precision

Evaluates how accurately the host harness routes user requests to the skill without misfiring on adjacent tasks or failing to trigger when intended.

| Score | Rating | Characteristic Behaviors |
|:---:|:---|:---|
| **1** | **Failing / Unusable** | Missing frontmatter description or empty trigger; vague phrases like "helps with coding"; semantic black hole that triggers on almost any prompt; or so obscure that no agent ever selects it. |
| **2** | **Weak / Risky** | Description states what the skill does in vague terms, but lacks explicit "Use when..." conditions; no negative boundary ("Do not use for..."); easily confused with 2+ adjacent skills; excessive length (>1024 chars) causing host truncation. |
| **3** | **Acceptable** | Contains explicit "Use when..." condition; covers the primary happy path; may occasionally trigger on closely related adjacent tasks; lacks crisp negative boundaries or exclusions. |
| **4** | **Strong** | Front-loaded action verbs; clear primary and secondary triggers; includes negative boundary ("Do not use for X; use Y instead"); resistant to host truncation; separates explicit command mode from implicit routing. |
| **5** | **Exemplary / Production** | Discriminating, laser-focused description (<150 words); crisp positive triggers with specific vocabulary; exhaustive negative boundaries covering known confusing neighbors; verified via a synthetic routing test suite across discriminatory positive, adjacent, and negative test prompts. |

---

## Pillar 2: Progressive Disclosure Architecture

Evaluates how effectively the skill partitions its information across tiers to minimize context consumption during model execution.

| Score | Rating | Characteristic Behaviors |
|:---:|:---|:---|
| **1** | **Monolithic Bloat** | Single massive `SKILL.md` (>600 lines / >3500 tokens) dumping all reference manuals, scripts, API docs, and edge-case guides directly into context on every trigger. |
| **2** | **Partial Partitioning** | Some external files created, but unorganized; broken relative markdown links; or circular/nested link chains (A links to B which links to C). |
| **3** | **Structured Baseline** | `SKILL.md` serves as main workflow; distinct sections split into `references/`; all relative links resolve; some branch-specific detail still leaks into `SKILL.md`. |
| **4** | **Clean Tiers** | `SKILL.md` is strictly an orchestration runbook (<300 lines); branch-specific knowledge is isolated in `references/` with single-level, condition-bearing pointers; templates reside in `assets/`. |
| **5** | **Optimal Progressive Disclosure** | Aligned with the SEG Context Tier Model: System metadata -> Orchestration runbook (`SKILL.md`) -> Domain reference manuals (`references/` read on demand) -> Executable helpers (`scripts/` run without loading code into context) -> Scaffolding assets (`assets/`). Minimal token footprint for unchosen branches. |

---

## Pillar 3: Steering & Behavioral Invariants

Evaluates how clearly the skill instructs the agent: whether it guides outcomes with checkable criteria or causes brittleness through micro-management or vagueness.

| Score | Rating | Characteristic Behaviors |
|:---:|:---|:---|
| **1** | **Unsteered / Open-Ended** | Conversational musings; no checkable steps; no definition of done; no constraints on scope; agent wanders or hallucinates completion. |
| **2** | **Fragile Micro-Management** | Dictates trivial, fragile keystrokes or exact arbitrary commands that break across environments; fails when minor tool variations occur; lacks high-level intent. |
| **3** | **Basic Procedural** | Numbered sequence of steps; states desired goals; completion criteria are informal or subjective ("ensure the code looks good"). |
| **4** | **Outcome-Led Guidance** | Each phase specifies inputs, actions, constraints, checkable outputs, and completion criteria; uses precise domain vocabulary to steer behavior without over-prescribing mechanics. |
| **5** | **Contract-Grade Specification** | Every step defines: Input schema, Invariants, Checkable artifact receipt, Failure/Stop threshold, and Concrete termination signal. Balances strict invariants with agentic adaptability. |

---

## Pillar 4: Execution Determinism & Tool Delegation

Evaluates whether deterministic, repetitive, or calculation-heavy tasks are offloaded to executable scripts rather than handled in error-prone prompt text.

| Score | Rating | Characteristic Behaviors |
|:---:|:---|:---|
| **1** | **LLM Arithmetic / Parsing** | Forces the LLM to do manual regex parsing, complex AST transformations, math calculations, or large file formatting inside chat tokens. |
| **2** | **Ad-hoc Inline Snippets** | Instructs the LLM to write throwaway python/bash one-liners on the fly without validation, error checking, or test fixtures. |
| **3** | **Scripted Helpers Present** | Key repetitive tasks are encapsulated in `scripts/`; scripts run without syntax errors; basic error logging present; lacks comprehensive unit tests or CLI args. |
| **4** | **Robust CLI Tools** | Scripts are well-parameterized (`argparse`), return structured JSON receipts, handle timeouts and non-zero exits gracefully, and include clear invocation syntax in `SKILL.md`. |
| **5** | **Verified Helper Scripts** | Automated helpers handle data parsing, validation, and schema checking; standard library dependencies where possible; verified by automated unit tests with rollback-protected mutation. |

---

## Pillar 5: Safety, Authority & Failure Modes

Evaluates how the skill protects project assets, prevents unintended side effects, handles errors, and enforces human-in-the-loop oversight.

| Score | Rating | Characteristic Behaviors |
|:---:|:---|:---|
| **1** | **Silent Destroyer** | Unbounded destructive file operations (`rm -rf`, overwriting git history, dropping tables); no dry-run options; assumes infinite authority; crashes on network or tool failure. |
| **2** | **Naive Optimism** | Only handles the happy path; ignores rate limits, timeouts, tool errors, or missing dependencies; leaves system in corrupt/intermediate state on failure. |
| **3** | **Guarded Baseline** | Includes general warning notes for destructive actions; distinguishes read-only inspection from file modification; basic retry mention. |
| **4** | **Explicit Authority Gates** | Hard boundaries between exploration and mutation; explicit confirmation checkpoints before irreversible or consequential actions; capped retries with exponential backoff. |
| **5** | **Resilient Assurance System** | Enforces rollback-protected operations; rollback or clean degradation on partial failure; controller-owned state receipts; no credential exposure in tracked files; explicit human authorization gates for all consequential mutations. |

---

## Pillar 6: Token Economics & Context Efficiency

Evaluates the information density of the skill, ensuring high signal-to-noise ratio and concise, high-density instructions.

| Score | Rating | Characteristic Behaviors |
|:---:|:---|:---|
| **1** | **Bloated Common Sense** | Wastes thousands of context tokens re-explaining fundamental programming concepts (e.g. how git commits work, basic Python syntax, elementary HTML); verbose conversational filler. |
| **2** | **Verbose / Redundant** | Repeats the same instruction multiple times across sections; includes lengthy sample outputs or huge boilerplate blocks directly in `SKILL.md`. |
| **3** | **Moderate Density** | Relatively focused; minimal conversational padding; could still benefit from pruning 20-30% of repetitive guidance or obvious boilerplate. |
| **4** | **Lean & High-Signal** | Every sentence conveys specific domain constraints or required procedures; boilerplate moved to `assets/`; zero basic programming lectures. |
| **5** | **High-Density Precision** | Maximum semantic density; compact domain shorthand; pruned boilerplate and redundant prose; verified minimal token footprint; optimized for fast LLM ingestion and exact instruction-following. |
