# Privacy Policy for Skill Evaluation Graph (SEG)

*Last updated: September 4, 2026*

The **Skill Evaluation Graph (SEG)** project (`MaxLaurieHutchinson/skill-evaluation-graph`) is an open-source development tool built to evaluate, audit, and benchmark Agent Skills locally and within user-controlled CI/CD environments.

## 1. Zero Telemetry & Local Execution
- **Local Operation**: All evaluation algorithms, token profilers, static diagnostics, DAG wave schedulers, and repair sandboxes execute strictly on your local machine or self-hosted CI runners. SEG processes local skill files, scripts, manifests, and references directly on the user's workstation or CI runner.
- **No Telemetry**: SEG contains no analytics, phone-home mechanisms, error reporting beacons, or tracking pixels.
- **Local Storage**: Evaluation scorecards, unified diff previews, and tamper-evident audit receipts are written exclusively to your local filesystem.

## 2. Live Harness Execution & External Network Transmission
- **Static Evaluation Mode (Default)**: Static analysis tools (`audit_skill.py`, `run_loop.py`, and default `eval_skill.py`) make **zero outbound network requests**.
- **Live Behavioral Trials (`--live`)**: When executing live trials against external coding agent harnesses (e.g. `eval_skill.py --live --harness codex`), scenario prompts and responses are processed via the host agent CLI. Network transmission and model inference during these trials are governed entirely by that provider's service terms and privacy policies (e.g., OpenAI API / Codex policies).
- **Isolated Authentication Bridging**: To run authenticated trials in an isolated environment without importing ambient user settings or global skills, the Codex harness adapter temporarily copies only the specific authentication file (`auth.json`) into a local scratch directory when executing live trials in isolated workspaces, never copying full user environments or configuration directories. This file is retained only for the duration of the trial and is never transmitted by SEG.

## 3. Data Retention & Workstation PII Prevention
- SEG does not intentionally collect or transmit personal data. It processes user selected files locally as required to perform evaluation.
- Built-in privacy scanners actively inspect skill files to detect and block accidental exposure of local workstation paths (`C:\Users\...`, `/home/...`, `OneDrive\...`) before public distribution (`Anti-Pattern 14: The Leaky Local Path`).
- By default, evaluation receipts sanitize target workstation file paths into relative paths (`./<skill-name>`).

## 4. Contact & Inquiries
For questions regarding SEG security or privacy practices, please open an issue on the official GitHub repository:
[https://github.com/MaxLaurieHutchinson/skill-evaluation-graph/issues](https://github.com/MaxLaurieHutchinson/skill-evaluation-graph/issues)
