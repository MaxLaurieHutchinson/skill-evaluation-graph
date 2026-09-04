# Agent Skill Deep Audit & Optimization Scorecard

| Metadata | Details |
|:---|:---|
| **Skill Name** | `[skill-name]` |
| **Directory Path** | `[path-to-skill]` |
| **Audit Date** | YYYY-MM-DD |
| **Harness Compatibility** | Antigravity / Codex / Claude Code |
| **Overall Recommendation** | **[ACCEPT / REVISE / ESCALATE]** |

---

## 1. Executive Summary

Provide a 2–3 paragraph evaluation summarizing the core purpose of the skill, its principal strengths, critical bottlenecks, and the highest-leverage improvements.

---

## 2. The 6-Pillar Scorecard

Ratings are scored from 1 (Failing) to 5 (Exemplary) based on the [Audit Rubric](../references/audit-rubric.md).

| Pillar | Current Score (1-5) | Target Score (1-5) | Gap & Key Observations |
|:---|:---:|:---:|:---|
| **1. Trigger & Routing Precision** | / 5 | 5 / 5 | |
| **2. Progressive Disclosure** | / 5 | 5 / 5 | |
| **3. Steering & Invariants** | / 5 | 5 / 5 | |
| **4. Execution Determinism** | / 5 | 5 / 5 | |
| **5. Safety & Authority Gates** | / 5 | 5 / 5 | |
| **6. Token Economics & Density** | / 5 | 5 / 5 | |
| **STATIC QUALITY SCORE** | **`[X]` / 100** | **Target: 95 / 100** | **Static Quality Readiness: `[Y]`%** |

---

## 3. Automated Static Diagnostic Findings

*Captured via `scripts/audit_skill.py`:*

- **Frontmatter Syntax & Schema:** [Valid / Errors]
- **Name Conformance:** [Matches directory / Mismatch]
- **SKILL.md Footprint:** `[X]` lines | `[Y]` words | ~`[Z]` tokens
- **Description Footprint:** `[A]` characters | `[B]` words
- **Broken Relative Links:** `[None / List detected broken links]`
- **Orphaned Assets/References:** `[None / List unlinked files]`

---

## 4. Anti-Patterns Detected

Refer to the [Anti-Patterns Catalog](../references/anti-patterns.md) for remediation recipes.

- [ ] **1. The Monolith:**
- [ ] **2. The Semantic Black Hole:**
- [ ] **3. The Ghost Trigger:**
- [ ] **4. The LLM Calculator:**
- [ ] **5. The Micro-Manager:**
- [ ] **6. The Silent Destroyer:**
- [ ] **7. The Nested Reference Maze:**
- [ ] **8. The Stale Fossil:**
- [ ] **9. The Common Sense Echo Chamber:**
- [ ] **10. The Missing Completion Signal:**
- [ ] **11. The Fragile Pipeline:**
- [ ] **12. The Leaky Boundary:**

---

## 5. Synthetic Routing & Trigger Test Matrix

Test the description's ability to trigger on target tasks while rejecting adjacent or confusing requests:

| Test Prompt | Category | Expected Behavior | Observed Result | Pass / Fail |
|:---|:---|:---|:---|:---:|
| *"Target request 1"* | Direct Trigger | Skill activates | | |
| *"Target request 2 (paraphrased)"* | Indirect Trigger | Skill activates | | |
| *"Adjacent task A (near miss)"* | Negative Boundary | Rejects (uses general tools) | | |
| *"Keyword collision prompt"* | Negative Boundary | Rejects (uses other skill) | | |
| *"Unrelated request"* | Noise Filter | Rejects | | |

---

## 6. Prioritized Remediation Plan

### Phase 1: Critical Correctness & Safety (P0)
- [ ] Fix broken markdown links.
- [ ] Insert confirmation gates before irreversible actions.
- [ ] Resolve frontmatter schema or naming defects.

### Phase 2: Progressive Disclosure & Partitioning (P1)
- [ ] Carve out monolithic sections from `SKILL.md` into `references/`.
- [ ] Move templates and schemas into `assets/`.
- [ ] Delegate calculations and brittle parsing to `scripts/`.

### Phase 3: Token Pruning & Steering Refinement (P2)
- [ ] Prune conversational padding and LLM common sense.
- [ ] Front-load description with precise trigger terms and negative boundaries.
- [ ] Add checkable termination criteria to each phase.

---

## 7. Before vs. After Benchmark

| Metric | Before Audit & Refactor | After Optimization | Delta |
|:---|:---:|:---:|:---:|
| `SKILL.md` Line Count | | | |
| Estimated Working Memory Tokens | | | |
| Description Length (chars) | | | |
| Broken Relative Links | | | |
| 6-Pillar Total Score | / 30 | / 30 | |
