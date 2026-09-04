# Cross-Harness Tool Mapping Matrix

When skills specify abstract actions, map them to the concrete tools provided by your active agent harness:

| Action In Skill | Google Antigravity (`agy`) | Anthropic Claude Code | OpenAI Codex | Cursor / General |
|:---|:---|:---|:---|:---|
| **Read File** | `view_file` | `View` / `Read` | `read_file` | Read tool / editor |
| **Create File** | `write_to_file` | `Write` | `create_file` | Write tool |
| **Edit Block** | `replace_file_content` | `Edit` | `replace_lines` | Edit tool |
| **List Directory** | `list_dir` | `LS` | `list_dir` | List files |
| **Search Files** | `grep_search` / `find_by_name` | `Grep` / `Glob` | `grep` / `file_search` | Search |
| **Run Shell Command** | `run_command` (powershell/bash) | `Bash` | `execute_bash` | Terminal / Bash |
| **Dispatch Subagent** | `invoke_subagent` (`TypeName: "self"` or `"research"`) | `Task` | `spawn_agent` | Agent sub-task |
| **Task / Checklist Tracking** | **Task Artifact** (`write_to_file` with `ArtifactType: "task"`) | `TodoWrite` / Todo | Checklist file | Checklist / Scratchpad |
| **Human Question** | `ask_question` | Prompt in chat | Prompt in chat | Chat prompt |

---

## Harness-Specific Notes

### 1. Antigravity (`agy`)
- **Do NOT confuse `manage_task` with a todo list.** `manage_task` is for managing background processes (`list`, `kill`, `status`, `send_input`).
- Maintain task tracking via an explicit **task artifact** (`write_to_file` with `ArtifactType: "task"` and `IsArtifact: true`), updating it with `replace_file_content` as each milestone completes (`- [x]`).
- For subagent delegation, use `invoke_subagent` with built-in `TypeName: "self"` (for full read/write capabilities) or `TypeName: "research"` (for read-only codebase exploration).

### 2. Claude Code
- Plugins register hooks via `hooks/hooks.json`.
- Uses native `Task` tool for sub-processes and `TodoWrite` for session todo tracking.

### 3. OpenAI Codex
- Uses `agents/openai.yaml` for UI display title, description, and parameter routing.

---

## The Tri-Harness Unified Pointer Pattern

Maintaining divergent instructions across multiple agent files causes instruction drift. Use the single-source-of-truth pattern:

1. **`CLAUDE.md` (Authoritative Source):** Contains complete contributor guidelines, tools reference, and the "If You Are an AI Agent" protective contract.
2. **`AGENTS.md` (Open Standard Pointer):** Used by Codex, Cursor, and Copilot. Points to `CLAUDE.md`:
   ```markdown
   <!-- Agent Instructions Pointer -->
   See [CLAUDE.md](CLAUDE.md) for full contributor guidelines and agent instructions.
   ```
3. **`GEMINI.md` (Antigravity Transclusion):** Transcludes `CLAUDE.md` directly into the agent's working context at startup:
   ```markdown
   @./CLAUDE.md
   ```

---

## Compaction Amnesia Defense (Polyglot SessionStart Hooks)

When coding agents hit context window limits, the host compacts context, causing the agent to forget installed skills. Deploy a polyglot `SessionStart` hook (`hooks/session-start` + `hooks/hooks.json`) to re-inject capability awareness across Claude Code, Antigravity, and Cursor on every reset or compaction:

- **Hook Event:** `SessionStart`
- **Injected Context:** `<SYSTEM_CAPABILITY> You have access to the [skill-name] skill package... </SYSTEM_CAPABILITY>`
- **Format Support:** Dynamically emits Claude Code `hookSpecificOutput` format or Cursor `additional_context` JSON.
