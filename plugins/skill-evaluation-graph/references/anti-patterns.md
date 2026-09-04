# Catalog of 14 Agent Skill Anti-Patterns & Remediation Recipes

This catalog documents the 14 most frequent architectural defects found in agent skills, how to diagnose them, and concrete recipes to refactor them into production-grade patterns.

---

### 1. The Monolith ("God SKILL.md")
- **Symptom:** A single `SKILL.md` file exceeding 500 lines (>2500 words), containing full API specs, multiple scripting languages, deep architectural theory, and lengthy configuration templates.
- **Why It Fails:** Floods the model's active working memory with hundreds of irrelevant tokens on every task, increasing inference costs, latency, and instruction-skipping (needle-in-a-haystack effect).
- **Remediation:**
  1. Extract branch-specific documentation into standalone markdown files in `references/`.
  2. Move copy-paste boilerplate, schemas, and templates into `assets/`.
  3. Replace the extracted sections in `SKILL.md` with single-level, condition-bearing links:
     `"For database migration procedures, consult `references/database-migrations.md`."`

---

### 2. The Semantic Black Hole
- **Symptom:** Description is overly broad: *"Assists with software development, debugging, testing, refactoring, and code analysis."*
- **Why It Fails:** Triggers inappropriately on virtually every prompt, preempting more specialized skills or general assistant capabilities when unneeded.
- **Remediation:**
  1. Front-load the exact specific job: *"Run comprehensive mutation testing and AST-level safety analysis..."*
  2. Add an explicit negative boundary: *"Do not use for routine bug fixes or single-file formatting; use standard edit tools instead."*

---

### 3. The Ghost Trigger
- **Symptom:** Description uses obscure academic jargon, acronyms, or non-standard terms that user prompts never contain (e.g., *"Orchestrates ephemeral hermetic virtualization containers"*).
- **Why It Fails:** The host agent never selects the skill because user prompts never match the semantic embedding of the description.
- **Remediation:**
  1. Include real-world user intent phrases: *"Use when the user asks to spin up a sandboxed test environment, isolate a test run, or test in Docker."*
  2. Test trigger phrasing against a realistic user prompt test suite.

---

### 4. The LLM Calculator
- **Symptom:** Asking the LLM in markdown text to parse complex ASTs, compute checksums, format large CSV tables, calculate date math, or run regex search-and-replace.
- **Why It Fails:** Non-deterministic token generation frequently hallucinates calculations, drops lines from large tabular datasets, and makes off-by-one errors.
- **Remediation:**
  1. Encapsulate the calculation/parsing in a Python or shell script under `scripts/`.
  2. Have `SKILL.md` instruct the agent to execute the script:
     `` `python scripts/process_metrics.py --input data.csv --output result.json` ``.
  3. Let the LLM interpret the structured summary output rather than doing raw crunching.

---

### 5. The Micro-Manager
- **Symptom:** Over-prescribing exact terminal keystrokes, editor cursor movements, or rigid single-line commands that assume a specific OS or shell configuration.
- **Why It Fails:** Extremely fragile across different environments (PowerShell vs Bash, Windows vs Linux/macOS) and strips the agent of its natural problem-solving adaptability.
- **Remediation:**
  1. Transition from prescriptive keystrokes to outcome-led contracts.
  2. Specify: Input -> Action -> Constraints -> Expected Checkable Output.
  3. State the required invariant (e.g. *"Ensure port 8080 is available before starting"*) instead of dictating the exact command to free it.

---

### 6. The Silent Destroyer
- **Symptom:** Instructing the agent to run destructive commands (`rm -rf`, `git reset --hard`, database drops) without dry-run options or user confirmation gates.
- **Why It Fails:** Irreversible data loss when an agent encounters unexpected file layouts or misinterpreted requirements.
- **Remediation:**
  1. Default all mutation scripts to a `--dry-run` mode.
  2. Add an explicit invariant in `SKILL.md`:
     `"STOP and request explicit user confirmation before executing any irreversible deletion, table drop, or force-push."`

---

### 7. The Nested Reference Maze
- **Symptom:** `SKILL.md` links to `ref1.md`, which instructs the agent to read `ref2.md`, which links to `ref3.md`.
- **Why It Fails:** Triggers deep recursive tool calls, exhausts agent call limits, and scatters context across disjoint documents.
- **Remediation:**
  1. Flatten references to a single level of hierarchy.
  2. Every reference file in `references/` should be self-contained and directly linkable from `SKILL.md`.

---

### 8. The Stale Fossil
- **Symptom:** Contains hardcoded deprecated API versions, broken URLs, references to deleted repository files, or assumptions about external tools that no longer exist.
- **Why It Fails:** Causes repeated tool errors, confused agent retries, and hallucinations as the agent attempts to satisfy impossible constraints.
- **Remediation:**
  1. Run automated link checks using `audit_skill.py`.
  2. Declare version constraints and environment prerequisites clearly.
  3. Include fallback routines when optional dependencies are absent.

---

### 9. The Common Sense Echo Chamber
- **Symptom:** Long paragraphs instructing the agent on basic programming common sense (e.g., *"Always write clean code with meaningful variable names and handle exceptions properly"*).
- **Why It Fails:** Consumes valuable token window space without providing any project-specific leverage or non-obvious constraints.
- **Remediation:**
  1. Aggressively prune generic programming advice that modern foundational LLMs already know.
  2. Retain only proprietary conventions, bespoke business rules, architectural invariants, and non-obvious failure modes.

---

### 10. The Missing Completion Signal
- **Symptom:** Open-ended steps such as *"Investigate the performance of the system and refine it."*
- **Why It Fails:** The agent has no measurable way to determine when it has finished, leading to infinite loops or premature termination.
- **Remediation:**
  1. Define checkable termination criteria:
     `"This phase is complete when: (1) all 5 benchmarks run without errors, (2) p95 latency is recorded in metrics.json, and (3) a comparison table is written to the report."`

---

### 11. The Fragile Pipeline
- **Symptom:** Multi-step pipelines where a single transient error (e.g. rate limit, network blip) immediately crashes the entire workflow and discards all prior work.
- **Why It Fails:** Wastes time and tokens; leaves work in undefined halfway states.
- **Remediation:**
  1. Implement atomic staging (write to temporary files, validate, then rename).
  2. Define explicit retry policies with exponential backoff for external network calls.
  3. Add degraded fallback modes (e.g., if live API is unavailable, proceed with cached fixtures and record a caveat).

---

### 12. The Leaky Boundary
- **Symptom:** The skill modifies configuration files, global environment variables, or unrelated source files outside the user's requested scope.
- **Why It Fails:** Violates user trust and breaks downstream builds or unrelated services.
- **Remediation:**
  1. Define a strict operational scope boundary:
     `"Do not modify files outside <target-dir>. Do not alter global git configuration or system PATH without explicit user permission."`

---

### 13. The Fragmented Docs Maze
- **Symptom:** Creating arbitrary subdirectories like `docs/`, `notes/`, or `wiki/` inside a skill package alongside `references/`, splitting documentation across conflicting human and agent formats.
- **Why It Fails:** Violates SEG's recommended folder convention (`SEG_RECOMMENDATION`). When documentation is fragmented across arbitrary directories, agents struggle to locate relevant reference files, leading to missed lookups, unindexed reference files, and confusion between human manuals and agent runbooks.
- **Remediation:**
  1. Follow SEG's recommended 4-folder layout: `scripts/`, `references/`, `assets/`, `hooks/`.
  2. Consolidate all on-demand agent knowledge into `references/`.
  3. Keep human installation, usage, and contributor manuals in `README.md`.

---

### 14. The Leaky Local Path (PII Exposure)
- **Symptom:** Hardcoding local machine paths (`C:\Users\<username>\...`, `/home/<username>/...`, `OneDrive\...`) in scorecards, tests, templates, or markdown examples.
- **Why It Fails:** Exposes personal usernames and workstation file paths to public repositories, breaks cross-platform portability on other machines or CI runners, and causes relative path resolution errors.
- **Remediation:**
  1. Replace absolute workstation paths with standard relative paths (e.g. `skills/<skill-name>`).
  2. Use environment variables or CLI flags (`--path <dir>`) for dynamic location resolution.
  3. Scan for machine path leaks with `audit_skill.py` before publishing.
