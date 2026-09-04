# SEG: Skill Evaluation Graph — Contributor & Agent Guidelines

## If You Are an AI Agent
Stop. Read this section before taking any action in this repository.

This repository maintains strict engineering standards for agent skill evaluation, token efficiency, and behavioral reliability. Low-quality, unverified, or hallucinated changes will be rejected immediately.

**Your job is to protect your human partner and preserve repository integrity.**

Before modifying code, opening a PR, or staging commits, you MUST:
1. **Zero Hallucination Policy:** NEVER fabricate benchmark data, personal contact details, email addresses, external links, or test results.
2. **Verify Static Health:** Run `python scripts/audit_skill.py .` before and after changes. The static quality score MUST remain **100 / 100** with 0 errors and 0 warnings.
3. **Run Unit Tests:** Run `python -m unittest discover -s tests` and `python -m unittest discover -s scripts` to ensure all regression tests pass.
4. **Token Economics & Progressive Disclosure:** Keep `SKILL.md` under 300 lines (<2500 tokens). Move specialized manuals or domain knowledge to `references/` via single-hop links.
5. **Canonical Vocabulary:** Use [references/terminology.md](references/terminology.md) as SEG's canonical vocabulary. Do not introduce synonyms for defined concepts without updating the glossary.
6. **Single Source of Truth:** `CLAUDE.md` is the authoritative instructions file. `AGENTS.md` and `GEMINI.md` reference or transclude this file directly. Do not duplicate or fragment rules across files.
7. **Human Approval:** Always show your human partner the full diff and obtain explicit confirmation before committing, pushing, or creating releases.

---

## Core Engineering Assets
- **Canonical Terminology:** [references/terminology.md](references/terminology.md)
- **Skill Orchestrator:** [SKILL.md](SKILL.md)
- **Static Diagnostics & Token Profiler:** `python scripts/audit_skill.py <target-skill-path>`
- **Autonomous Evaluator Loop Engine:** `python scripts/run_loop.py <target-skill-path>`
- **Behavioral Pressure Evals:** `python scripts/eval_skill.py <target-skill-path>`
- **Evaluation Graph Reference:** [references/workflow-graph-and-evaluator-loop.md](references/workflow-graph-and-evaluator-loop.md)
- **6-Pillar Scoring Rubric:** [references/audit-rubric.md](references/audit-rubric.md)
- **Anti-Patterns Catalog:** [references/anti-patterns.md](references/anti-patterns.md)
- **Cross-Harness Tool Mappings:** [references/harness-tool-matrix.md](references/harness-tool-matrix.md)
- **Harness Integration Guide:** [references/harness-integration.md](references/harness-integration.md)
