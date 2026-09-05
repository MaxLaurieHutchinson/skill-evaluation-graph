# Harness Integration & Installation

Install the package at `plugins/skill-evaluation-graph/`, which contains `SKILL.md` and its resources. The repository root is a marketplace, not a standalone Skill directory. Install the Python dependencies from the package's `requirements.txt` before running SEG scripts.

## Antigravity

Copy the nested package into `<workspace>/.agents/skills/skill-evaluation-graph/`. Antigravity discovers it as an Agent Skill. `gemini-extension.json` belongs to Gemini CLI; SEG does not claim a native Antigravity manifest or automatic SessionStart hook execution.

Source: [Antigravity Skills](https://antigravity.google/docs/skills).

## Claude Code

Copy the nested package into `~/.claude/skills/skill-evaluation-graph/` for a personal Skill, or `<workspace>/.claude/skills/skill-evaluation-graph/` for a project Skill. A plain Skill installation does not register plugin hooks. The package also includes `.claude-plugin/plugin.json` and hook metadata for environments that load it as a plugin.

Source: [Claude Code Skills](https://code.claude.com/docs/en/skills).

## OpenAI Codex

Use the repository marketplace through the Codex Plugins UI. `.agents/plugins/marketplace.json` routes to the nested package and its `.codex-plugin/plugin.json` manifest. For a plain Agent Skills installation, copy the package to a skills directory supported by the host. `agents/openai.yaml` supplies display metadata.

## Gemini CLI

Install the nested Skill from this repository:

```bash
gemini skills install https://github.com/MaxLaurieHutchinson/skill-evaluation-graph --path plugins/skill-evaluation-graph
```

The package contains `gemini-extension.json` for extension compatibility. The repository root does not contain that manifest, so a root-level extension installation is not the documented route.

Source: [Gemini CLI Agent Skills](https://geminicli.com/docs/cli/skills/).

## Evidence limits

Packaging validation, SEG Harness Adapter availability, and live verification of a Target Skill are separate evidence classes. Installing a package does not prove its behavioural reliability. See [claim-audit.md](claim-audit.md).
