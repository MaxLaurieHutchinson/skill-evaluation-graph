# Progressive Disclosure Architecture for High-Performance Agent Skills

Progressive disclosure is the architectural practice of structuring a skill so that the agent loads only the minimum context required at each phase of execution. 

Without progressive disclosure, complex skills become bloated monoliths that overwhelm context windows, degrade model reasoning, increase latency, and cause instruction-skipping.

---

## The SEG Context Tier Model

> [!NOTE]
> **SEG Recommendation**: The SEG Context Tier Model is an opinionated architectural framework and convention maintained by SEG (`FindingKind.SEG_RECOMMENDATION`). It establishes best practices for progressive disclosure and context token budgeting. Deviations reduce the Static Quality Score rather than failing mandatory specification conformance gates.

```text
┌────────────────────────────────────────────────────────┐
│ TIER 1: Metadata / Discovery Tier                      │
│ - System prompt level (Name & Description only)        │
│ - Zero body tokens loaded until activated              │
└────────────────────────┬───────────────────────────────┘
                         │ User prompt matches trigger
                         ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: Task Orchestration Tier (SKILL.md)             │
│ - Concise workflow runbook (<250 lines)                │
│ - Flowchart, phases, inputs, outputs, invariants       │
│ - Condition-bearing pointers to Tiers 3, 4, 5          │
└───────────┬────────────────────┬───────────────────────┘
            │ Branch chosen      │ Deterministic action
            ▼                    ▼
┌──────────────────────┐ ┌───────────────────────────────┐
│ TIER 3: Domain Manual│ │ TIER 4: Deterministic Tools   │
│ (references/*.md)    │ │ (scripts/*)                   │
│ - Deep API specs     │ │ - Python / Shell scripts      │
│ - Complex heuristics │ │ - Run via bash/pwsh CLI       │
│ - Syntax cheatsheets │ │ - Output structured JSON/text │
│ - Loaded on-demand   │ │ - Never loaded into context   │
└──────────────────────┘ └───────────────────────────────┘
            │ Template needed
            ▼
┌────────────────────────────────────────────────────────┐
│ TIER 5: Scaffolding & Asset Tier (assets/*)            │
│ - Reusable document templates, schemas, boilerplate    │
│ - Copied, populated, or deployed to user directory     │
└────────────────────────────────────────────────────────┘
```

---

## The Four Cardinal Rules of Progressive Disclosure

### 1. The Rule of One Hop (Flat References)
- **Constraint:** Links from `SKILL.md` to `references/` must be directly actionable in a single step.
- **Prohibition:** Never chain references (`SKILL.md` -> `refA.md` -> `refB.md` -> `refC.md`).
- **Standard:** Every reference file must be self-contained and focused on a single distinct domain, phase, or branch.

### 2. The Rule of Lazy Loading (Condition-Bearing Pointers)
- **Constraint:** Never tell the agent to read all reference files upfront.
- **Pattern:** Always prefix links with the explicit condition or branch that requires them:
  - *Do:* `"If migrating a PostgreSQL database, read references/postgres-migration.md."`
  - *Don't:* `"Please read all documents in the references/ folder before starting."`

### 3. The Rule of Silent Execution (Script Delegation)
- **Constraint:** Do not make the model read executable helper scripts into chat context if it only needs to run them.
- **Pattern:** Instruct the agent to execute the script from the command line and capture its structured stdout/JSON:
  ```powershell
  python "<skill-dir>/scripts/validate_schema.py" --schema "<schema-file>" --target "<data-file>"
  ```
- **Rationale:** Code execution is orders of magnitude faster, cheaper, and more accurate than token-level simulation.

### 4. The Context Budget Rule
- **Target Metrics for Production Skills:**
  - `description`: < 150 words (< 1024 characters)
  - `SKILL.md`: < 300 lines (< 1800 words / ~2200 tokens)
  - `references/*.md`: 100–400 lines per file (modular domain guides)
  - `scripts/*`: Fully executable, zero context overhead until called

---

## Refactoring Monoliths: A Practical 4-Step Walkthrough

When you encounter an existing skill whose `SKILL.md` is 600+ lines long:

1. **Audit Branch Density:** Identify sections in `SKILL.md` that are only relevant to specific conditions (e.g., specific cloud providers, advanced configurations, legacy fallbacks).
2. **Carve Out Domain Manuals:** Move those conditional sections into dedicated `references/<subtopic>.md` files.
3. **Carve Out Boilerplate:** Move large JSON schemas, XML configs, and Markdown document templates into `assets/<template-name>`.
4. **Wire Condition-Bearing Links:** In `SKILL.md`, replace the cut material with crisp, one-line pointer bullets linking to the new reference or asset.
