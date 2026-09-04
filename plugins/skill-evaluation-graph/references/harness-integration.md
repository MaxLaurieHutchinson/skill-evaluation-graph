# Harness Integration & Plugin Setup Guide

This guide describes how to install, register, and activate `SEG` (`skill-evaluation-graph`) across all supported AI coding environments.

---

## 1. Antigravity Installation

Install directly as a plugin into Antigravity:

```bash
agy plugin install https://github.com/MaxLaurieHutchinson/skill-evaluation-graph
```

Antigravity will load `gemini-extension.json`, read `GEMINI.md`, and execute the `SessionStart` hook to maintain context awareness even after compaction.

To install locally for Antigravity:
```powershell
# Global skills directory
Copy-Item -Recurse skill-evaluation-graph ~/.gemini/config/skills/skill-evaluation-graph
```

---

## 2. Claude Code Installation

Install via the Claude Code plugin system:

```bash
/plugin install https://github.com/MaxLaurieHutchinson/skill-evaluation-graph
```

Claude Code registers the `.claude-plugin/plugin.json` manifest and fires `hooks/hooks.json` on `SessionStart` (startup, clear, and compaction).

To install manually:
```bash
cp -r skill-evaluation-graph ~/.claude/skills/skill-evaluation-graph
```

---

## 3. OpenAI Codex Installation

Place the skill package in the Codex skills directory:

```bash
cp -r skill-evaluation-graph ~/.agents/skills/skill-evaluation-graph
```

Codex reads `agents/openai.yaml` for UI titles, parameter definitions, and display metadata.

---

## 4. Gemini CLI Installation

Install as an extension:

```bash
gemini extensions install https://github.com/MaxLaurieHutchinson/skill-evaluation-graph
```
