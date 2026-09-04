# Applied AI Wiki Standards Alignment & Architectural Provenance

This document records the formal mapping between `skill-auditor` and the canonical 14-step framework defined in `good-agent-skill-authoring-procedure.md` and its parent research entry `building-great-agent-skills-reviewed-framework.md`.

---

## The System Architecture

```text
Applied AI Research Wiki (The Knowledge Plane)
└── building-great-agent-skills-reviewed-framework.md (Theory: Trigger, Structure, Steering, Pruning)
    └── good-agent-skill-authoring-procedure.md (Specification: 14-step manual standard)
        │
        ▼ (Mechanization & Automation)
skill-auditor (The Execution & Assurance Plane)
├── audit_skill.py       ──► Automates §11 (Structural Validation), §4 (Links), & Syntax
├── audit-rubric.md      ──► Formalizes §12 (Task Performance) & §13 (Acceptance Rubric)
├── anti-patterns.md     ──► Codifies §14 (Failure Classes & Remediation Recipes)
└── scorecard generator ──► Automates §13 (Provenance, Metrics, & Release Decision)
```

---

## Detailed Section-by-Section Mapping

| Section in Wiki Procedure | Canonical Requirement | How `skill-auditor` Implements & Enforces It |
|---|---|---|
| **§1. Real Repeated Job** | Define one-sentence job, bounded scope, explicit exclusions | Verified in Pillar 1 of `audit-rubric.md`; checked for negative boundary clauses in `audit_skill.py`. |
| **§2. Harness & Portable Core** | Adhere to portable Agent Skills spec; isolate host configs | Validates directory/name match, YAML schema, and verifies `agents/openai.yaml` if present. |
| **§3. Trigger & Routing** | Front-load actions, discriminate adjacent skills, <150 words | Evaluated in Pillar 1; `audit_skill.py` flags descriptions >200 words or missing "Use when...". |
| **§4. Progressive Disclosure** | 1-hop links, condition-bearing pointers, separate tiers | Evaluated in Pillar 2 and `progressive-disclosure-patterns.md`; `audit_skill.py --profile` monitors token budgets per tier. |
| **§5. Outcome-Led Instructions** | Specify Input, Action, Constraints, Output, and Done signal | Enforced via Pillar 3; all `SKILL.md` runbooks must define checkable `*Completion criterion:*` gates. |
| **§6. Safety & Authority** | Non-destructive defaults, explicit gates before mutation | Pillar 5; `audit_skill.py` scans for unshielded destructive shell commands (`rm -rf`, `git push --force`). |
| **§11. Structural Validation** | Directory matching, link resolution, no placeholders | **Directly automated** by `audit_skill.py` (checks frontmatter, broken links, `TODO`/`FIXME` markers, unclosed code fences). |
| **§12. Performance Evaluation** | Separate discovery from execution; score 6 dimensions | Quantified in `audit-rubric.md` (Levels 1 to 5) and automated via `audit_skill.py --scorecard`. |
| **§13. Release & Provenance** | Document metrics, dependencies, acceptance decision | Captured in `assets/skill-audit-scorecard-template.md` and pre-populated by `--scorecard`. |
| **§14. Improve From Evidence** | Classify observed failures into structured failure classes | Codified into the 12 anti-patterns in `references/anti-patterns.md` with concrete refactoring recipes. |
