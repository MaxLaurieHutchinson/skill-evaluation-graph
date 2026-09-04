# [Skill Name] — Contributor & Agent Guidelines

## If You Are an AI Agent
Stop. Read this section before taking any action in this repository.

This project enforces strict engineering standards for agent skills, reliability, and code quality. Low-quality, unverified, or hallucinated changes will be rejected immediately.

**Your job is to protect your human partner and preserve repository integrity.**

Before modifying files, opening a Pull Request, or staging commits, you MUST:

1. **Zero Hallucination Policy:** NEVER fabricate benchmark data, personal contact details, email addresses, external links, or test results.
2. **Verify Static Health:** Run the project linter / validator (e.g., `python scripts/audit_skill.py .`). The structural health score MUST pass with 0 errors and 0 warnings before submitting work.
3. **No Unshielded Destruction:** Never run irreversible deletions (`rm -rf`, force pushes, table drops) without explicit, confirmed human permission.
4. **Token Economics & Progressive Disclosure:** Keep primary orchestrator files (`SKILL.md`) compact (<300 lines). Delegate specialized reference material to `references/` via single-hop links.
5. **No Hardcoded Local Paths:** Never bake developer workstation paths (`C:\Users\...`, `/home/...`, `OneDrive`) into committed files, scorecards, or examples. Always use relative paths.
6. **Single Source of Truth:** Keep root instruction files synchronized:
   - `CLAUDE.md` serves as the authoritative guide.
   - `AGENTS.md` points to `CLAUDE.md` (`See [CLAUDE.md](CLAUDE.md)`).
   - `GEMINI.md` transcludes `CLAUDE.md` (`@./CLAUDE.md`).
7. **Human Approval:** Always show your human partner the full diff and obtain explicit confirmation before committing, pushing, or publishing.

---

## Core Engineering Commands
- **Lint / Validate:** `python scripts/audit_skill.py .`
- **Run Tests:** `pytest` or `python -m unittest discover`
- **Format Code:** `ruff check --fix .` / `black .`
