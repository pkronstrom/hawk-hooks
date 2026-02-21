# Hawk v2: Multi-Agent CLI Package Manager -- Research & Design

> Research completed 2026-02-17. Covers Claude Code, Gemini CLI, Codex CLI, OpenCode as primary targets, plus secondary tools (Aider, Continue, Amp, Goose, Kiro, Crush, Cline, Roo Code).

---

## A. Per-Tool Research Summary

### A1. Claude Code (Anthropic)

**Docs**: [code.claude.com/docs](https://code.claude.com/docs)

| Concept | Implementation |
|---------|---------------|
| **Skills** | `SKILL.md` files (Agent Skills open standard). Project: `.claude/skills/<name>/SKILL.md`. Global: `~/.claude/skills/<name>/SKILL.md`. Legacy: `.claude/commands/<name>.md` still works. |
| **Hooks** | 12 events: `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `Notification`, `SubagentStart`, `SubagentStop`, `Stop`, `PreCompact`. Types: `command` (shell), `prompt` (Haiku-evaluated), `agent` (multi-turn). Configured in `settings.json` under `hooks` key. Matchers are regex on tool names. |
| **MCP Servers** | Configured in `.mcp.json` (project) or `~/.claude.json` (user/local). Key: `mcpServers`. Transports: stdio, http, sse. CLI: `claude mcp add/remove/list`. Env var expansion: `${VAR}`, `${VAR:-default}`. |
| **Config hierarchy** | (highest first) Managed policy > CLI flags > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`. |
| **Context injection** | `CLAUDE.md` files (walks up to repo root + child dirs on demand). `CLAUDE.local.md` (gitignored). `.claude/rules/*.md` (conditional via `paths:` frontmatter). Auto-memory at `~/.claude/projects/<proj>/memory/MEMORY.md`. Stdout hooks inject context. `!`\`command\`` in SKILL.md for dynamic preprocessing. |
| **Directory layout** | Global: `~/.claude/{settings.json, CLAUDE.md, skills/, commands/, agents/, rules/, projects/}`. Project: `.claude/{settings.json, settings.local.json, skills/, commands/, agents/, rules/, hooks/}`. Also `.mcp.json` at project root. |

**Notable**: Claude Code does NOT natively read `AGENTS.md`. Skills have rich frontmatter extensions: `context: fork`, `agent`, `model`, `hooks`, `disable-model-invocation`, `user-invocable`.

---

### A2. Gemini CLI (Google)

**Docs**: [geminicli.com/docs](https://geminicli.com/docs), [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli)

| Concept | Implementation |
|---------|---------------|
| **Extensions** | Full extension system with `gemini-extension.json` manifest. Install from GitHub or local path. CLI: `gemini extensions install/uninstall/update/link/enable/disable/list/config/new`. Dir: `~/.gemini/extensions/<name>/`. Contains: manifest, GEMINI.md, commands/, hooks/, skills/, agents/. |
| **Skills** | `SKILL.md` files in `.gemini/skills/` (project) or `~/.gemini/skills/` (global) or extension `skills/`. Progressive disclosure: metadata at startup, full content on `activate_skill` tool call. CLI: `gemini skills list/link/install/enable/disable`. |
| **Commands** | TOML files in `commands/` directories. `{{args}}` for arguments, `!{cmd}` for shell injection, `@{path}` for file injection. Subdirectories create namespaced commands (e.g., `git/commit.toml` -> `/git:commit`). |
| **Hooks** | 11 events: `SessionStart`, `SessionEnd`, `BeforeAgent`, `AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `BeforeTool`, `AfterTool`, `PreCompress`, `Notification`. JSON stdin/stdout + exit codes (same protocol as Claude Code). Configured in `settings.json` `hooks` key or extension `hooks/hooks.json`. |
| **MCP Servers** | In `settings.json` `mcpServers` key or extension manifest. Transports: stdio, sse, http. Fields: `trust`, `includeTools`, `excludeTools`, `timeout`. OAuth auto-detection. |
| **Config hierarchy** | (highest first) CLI flags > env vars > Enterprise settings > `.gemini/settings.json` > `~/.gemini/settings.json` > System defaults > Hardcoded. |
| **Context injection** | `GEMINI.md` files (walks up to git root + subdirectories). `@file.md` import syntax. `context.fileName` configurable (can be array). Extension context via `contextFileName`. |
| **Directory layout** | Global: `~/.gemini/{settings.json, GEMINI.md, commands/, skills/, extensions/}`. Project: `.gemini/{settings.json, commands/, skills/, hooks/}`. Also `.geminiignore`. |

**Notable**: Gemini has the richest extension packaging (manifest with settings, MCP servers, hooks, commands, skills all in one). Variable substitution: `${extensionPath}`, `${workspacePath}`. Extension settings stored in OS keychain for sensitive values.

---

### A3. Codex CLI (OpenAI)

**Docs**: [developers.openai.com/codex](https://developers.openai.com/codex)

| Concept | Implementation |
|---------|---------------|
| **Skills** | `SKILL.md` in `.agents/skills/<name>/` (project) or `~/.agents/skills/` (global) or `/etc/codex/skills/` (system). Optional `agents/openai.yaml` for UI metadata, dependencies, policy. Invocation: `$skill-name` or `/skills` TUI. Built-in `$skill-creator` scaffolder. |
| **Hooks** | Minimal: `notify` config key runs external scripts on `agent-turn-complete`. Broader PreToolUse/PostToolUse system in active development (not shipped as stable API yet). |
| **MCP Servers** | In `config.toml` under `[mcp_servers.<name>]`. Transports: stdio (`command`+`args`) and streamable HTTP (`url`). Fields: `enabled`, `required`, `enabled_tools`, `disabled_tools`, `bearer_token_env_var`, `startup_timeout_sec`. CLI: `codex mcp add/list/get/remove/login/logout`. |
| **Config hierarchy** | (highest first) CLI flags/`--config` > profiles > `.codex/config.toml` (closest to cwd) > `~/.codex/config.toml` > `/etc/codex/config.toml` > defaults. |
| **Context injection** | `AGENTS.md` files (hierarchical walk from repo root to cwd). `AGENTS.override.md` takes precedence without deleting base. Fallback filenames configurable: `project_doc_fallback_filenames`. Also `model_instructions_file` and inline `developer_instructions` in config. |
| **Directory layout** | Global: `~/.codex/{config.toml, auth.json, AGENTS.md}`. Project: `.codex/config.toml`. Skills: `.agents/skills/`. Also `AGENTS.md` at any directory level. |

**Notable**: TOML config (unique among the four). Named profiles (`[profiles.fast]`). Project trust model (`trust_level = "trusted"`). Admin enforcement via `requirements.toml`. Apps/Connectors feature (ChatGPT connectors).

---

### A4. OpenCode (Anomaly/SST)

**Docs**: [opencode.ai/docs](https://opencode.ai/docs), [github.com/anomalyco/opencode](https://github.com/anomalyco/opencode)

| Concept | Implementation |
|---------|---------------|
| **Plugins** | Full SDK: `@opencode-ai/plugin` (npm). JS/TS files in `.opencode/plugins/` (project) or `~/.config/opencode/plugins/` (global). Also npm packages in config. Auto-loaded at startup. Bun runtime. |
| **Skills** | `SKILL.md` in `.opencode/skills/`, `.claude/skills/`, `.agents/skills/` (cross-compatible). Global: `~/.config/opencode/skills/`, `~/.claude/skills/`, `~/.agents/skills/`. |
| **Custom Tools** | TS/JS in `.opencode/tools/` or `~/.config/opencode/tools/`. Uses `tool()` helper with Zod schemas. Filename = tool name. |
| **Hooks** | Plugin-based event system (not shell scripts). Events: `tool.execute.before`, `tool.execute.after`, session events, message events, file events, permission events, `stop`, TUI events, `shell.env`, `experimental.session.compacting`, `experimental.chat.system.transform`. |
| **Commands** | Markdown files in `.opencode/commands/` or `~/.config/opencode/commands/`. Also JSON config. Frontmatter: description, agent, model. Placeholders: `$ARGUMENTS`, `$1`-`$3`, `!`\`command\``, `@filename`. |
| **MCP Servers** | In `opencode.json` under `mcp` key. Types: `local` (stdio) and `remote` (HTTP). OAuth auto-detection. CLI: `opencode mcp add/list/auth/logout/debug`. |
| **Agents** | Custom agents in `.opencode/agents/` or `~/.config/opencode/agents/`. Modes: primary, subagent. Granular permissions. |
| **Config hierarchy** | (highest first) `OPENCODE_CONFIG_CONTENT` env > `.opencode/` dirs > `opencode.json` (project) > `OPENCODE_CONFIG` env > `~/.config/opencode/opencode.json` > remote `.well-known/opencode`. |
| **Context injection** | `AGENTS.md` primary. Also reads `CLAUDE.md` (compatibility, disable with `OPENCODE_DISABLE_CLAUDE_CODE=1`). Config `instructions` array supports globs and URLs. |
| **Directory layout** | Global: `~/.config/opencode/{opencode.json, AGENTS.md, agents/, commands/, modes/, plugins/, skills/, tools/, themes/}`. Project: `.opencode/{agents/, commands/, modes/, plugins/, skills/, tools/}` + `opencode.json`. |

**Notable**: Cross-reads from `.claude/skills/` and `.agents/skills/`. JSON/JSONC config. Variable substitution: `{env:VAR}`, `{file:path}`. Array fields concatenate across config layers.

---

### A5. Secondary Tools (brief)

| Tool | MCP | Hooks | Skills | Custom Cmds | Context File | Config Location | Hawk-Worthy? |
|------|-----|-------|--------|-------------|--------------|-----------------|-------------|
| **Aider** | No | No | No | No | `CONVENTIONS.md` via `--read` | `.aider.conf.yml` | No -- too limited |
| **Continue** | Yes | No | No | Prompt files | `@`-context providers, rules | `~/.continue/config.yaml` | No -- IDE-first |
| **Amp** | Yes | No (delegate) | Yes (SKILL.md + bundled MCP) | Via Skills | `AGENTS.md` | `~/.config/amp/settings.json` | Maybe -- reads AGENTS.md + skills |
| **Goose** | Yes (native) | No | Platform ext | Recipes | `.goosehints` | `~/.config/goose/config.yaml` | Maybe -- MCP-only model |
| **Kiro** | Yes | Yes (5 types) | Yes (skill://) | No | Agent resources | `.kiro/settings/mcp.json` | Maybe -- has hooks |
| **Crush** | Yes | No | Yes | No | `AGENTS.md` | `.crush.json` | No -- too new |
| **Cline CLI** | Yes | Via ACP | Yes | No | N/A | `CLINE_DIR` | No -- IDE bridge |
| **Roo Code** | Yes | No | No | No | `.roo/` | `.roo/mcp.json` | No -- IDE-first |

**Recommendation**: Primary targets are Claude Code, Gemini CLI, Codex CLI, OpenCode. Secondary "easy-add" targets are Amp and Kiro (both consume SKILL.md and have similar config patterns). Others should not be default targets.

---

## B. Open Skills Conventions

### B1. SKILL.md / Agent Skills Standard

**Spec**: [agentskills.io/specification](https://agentskills.io/specification)
**Repo**: [github.com/agentskills/agentskills](https://github.com/agentskills/agentskills) (10.1k stars)

The Agent Skills format is the de facto cross-tool standard. 35+ agents support it.

**Required SKILL.md frontmatter:**

```yaml
---
name: skill-name          # 1-64 chars, lowercase + hyphens
description: What + when   # 1-1024 chars
---
```

**Optional standard fields:**

```yaml
license: Apache-2.0
compatibility: Requires git
metadata:
  author: org
  version: "1.0"
allowed-tools: Bash(git:*) Read  # Experimental
```

**Directory structure:**

```
skill-name/
  SKILL.md           # Required
  scripts/           # Optional executables
  references/        # Optional docs (loaded on demand)
  assets/            # Optional templates/resources
```

**Tool-specific extensions** (not in open standard):
- Claude Code: `context`, `agent`, `model`, `hooks`, `disable-model-invocation`, `user-invocable`, `argument-hint`
- Codex: `agents/openai.yaml` sidecar file
- Gemini: Part of extension manifest (`gemini-extension.json`)

### B2. Skill Discovery Paths

| Tool | Project Path | Global Path |
|------|-------------|-------------|
| Claude Code | `.claude/skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md` |
| Gemini CLI | `.gemini/skills/<name>/SKILL.md` | `~/.gemini/skills/<name>/SKILL.md` |
| Codex CLI | `.agents/skills/<name>/SKILL.md` | `~/.agents/skills/<name>/SKILL.md` |
| OpenCode | `.opencode/skills/<name>/SKILL.md` | `~/.config/opencode/skills/<name>/SKILL.md` |
| OpenCode (compat) | `.claude/skills/`, `.agents/skills/` | `~/.claude/skills/`, `~/.agents/skills/` |
| Amp | `.agents/skills/<name>/SKILL.md` | `~/.config/amp/skills/<name>/SKILL.md` |
| Kiro | `.kiro/skills/<name>/SKILL.md` | `~/.kiro/skills/<name>/SKILL.md` |
| GitHub Copilot | `.github/skills/<name>/SKILL.md` | N/A |
| Cursor | `.cursor/skills/<name>/SKILL.md` | `~/.cursor/skills/<name>/SKILL.md` |

### B3. Instruction File Conventions

| File | Primary Tool | Cross-Tool Adoption |
|------|-------------|-------------------|
| `CLAUDE.md` | Claude Code | OpenCode (compat fallback) |
| `AGENTS.md` | Codex CLI | Amp, OpenCode, Crush, Kiro, 40k+ repos |
| `GEMINI.md` | Gemini CLI | (configurable name) |
| `.cursorrules` | Cursor (deprecated) | Windsurf (some) |
| `.goosehints` | Goose | -- |

**The AGENTS.md vs CLAUDE.md split**: AGENTS.md has broader adoption (40k+ repos, multiple tools). Claude Code does not natively read AGENTS.md. Practical workaround: symlinks.

### B4. MCP Config Convergence

All four primary tools use near-identical JSON structures for MCP:

```json
{
  "mcpServers": {
    "name": {
      "command": "...",
      "args": [...],
      "env": {...}
    }
  }
}
```

Differences: Claude uses `.mcp.json` as standalone file; Gemini/OpenCode embed in `settings.json`/`opencode.json`; Codex uses TOML `[mcp_servers]` tables.

### B5. Package Manager: Vercel Skills CLI

**npm**: `skills` ([npmjs.com/package/skills](https://www.npmjs.com/package/skills))
**Site**: [skills.sh](https://skills.sh)

```bash
npx skills add vercel-labs/agent-skills           # Install from GitHub
npx skills add repo --skill name -a claude-code   # Specific skill + agent
npx skills find "react testing"                    # Search
npx skills list                                    # Show installed
npx skills remove skill-name                       # Uninstall
npx skills init my-skill                           # Scaffold
```

Installation modes: symlink (recommended) or copy. Scopes: project or global (`-g`).

**Security concerns**: Skills "look like docs" and bypass code review. Malicious skills discovered in registries. Hallucinated `npx` commands spreading. Shell access via SKILL.md scripts.

---

## C. Hawk Design Recommendations

### C1. Directory-Based Config as Canonical Registration

**Proposed**: `<repo>/.hawk/config.yaml`

```yaml
# .hawk/config.yaml -- what's active in this directory
profile: web-fullstack          # Optional base profile

skills:
  enabled:
    - tdd
    - react-patterns
    - api-design
  disabled:
    - legacy-jquery

hooks:
  enabled:
    - lint-on-save
    - block-secrets
  disabled: []

commands:
  enabled:
    - deploy
    - db-migrate

mcp:
  enabled:
    - github
    - postgres
  disabled:
    - notion

# Per-tool overrides (optional)
tools:
  claude:
    skills:
      extra: [claude-specific-skill]
  gemini:
    extensions:
      enabled: [my-gcp-extension]
```

**Profiles** at `~/.config/hawk-hooks/profiles/*.yaml`:

```yaml
# ~/.config/hawk-hooks/profiles/web-fullstack.yaml
name: web-fullstack
description: Full-stack web development defaults

skills: [tdd, react-patterns, api-design, typescript-strict]
hooks: [lint-on-save, block-secrets, format-on-edit]
commands: [deploy, db-migrate, test-watch]
mcp: [github, postgres, redis]
```

### C2. Resolved Set Computation

```
resolved = global_defaults + active_profiles + directory_overrides - disabled
```

**Algorithm:**

1. Load `~/.config/hawk-hooks/config.yaml` (global defaults)
2. If `.hawk/config.yaml` specifies a `profile`, load and merge profile
3. Merge `.hawk/config.yaml` `enabled` lists (additive)
4. Remove `.hawk/config.yaml` `disabled` lists (subtractive)
5. Apply per-tool overrides from `tools:` section
6. Output: one resolved set per tool

**Data structure:**

```python
@dataclass
class ResolvedSet:
    skills: dict[str, SkillRef]      # name -> path/metadata
    hooks: dict[str, HookRef]
    commands: dict[str, CommandRef]
    mcp_servers: dict[str, MCPConfig]
    # Per-tool views
    def for_tool(self, tool: str) -> ToolResolvedSet: ...
```

### C3. Application Modes

**Explicit mode** (default, recommended):

```bash
hawk sync                    # Apply resolved set to all tool configs
hawk sync --tool claude      # Apply to specific tool only
hawk sync --dry-run          # Show what would change
```

**Auto-apply mode** (optional):

Option A -- direnv integration:
```bash
# .envrc
eval "$(hawk shell direnv)"
```

Option B -- shell hook:
```bash
# In ~/.zshrc or ~/.bashrc
eval "$(hawk shell init)"
```

**Performance strategy:**
- Compute SHA-256 hash of `.hawk/config.yaml` + profile content + global config
- Cache resolved set at `~/.config/hawk-hooks/cache/<hash>.json`
- On directory change: compare hash -> skip if unchanged
- Target: <10ms for cache-hit path (just hash comparison)
- Full resolve + sync: <200ms

### C4. Hot-Swap Philosophy

**Skills/hooks/commands**: Symlink-based enable/disable.

```
~/.config/hawk-hooks/
  registry/
    skills/
      tdd/SKILL.md
      react-patterns/SKILL.md
    hooks/
      lint-on-save/hook.sh
      block-secrets/hook.py
    commands/
      deploy/deploy.md
      db-migrate/db-migrate.toml
  linked/                       # Tool-specific symlink targets
    claude/
      skills/tdd -> ../../registry/skills/tdd
    gemini/
      skills/tdd -> ../../registry/skills/tdd
```

`hawk sync` creates/removes symlinks in tool-native locations:
- `.claude/skills/tdd/` -> `~/.config/hawk-hooks/registry/skills/tdd/`
- `~/.gemini/skills/tdd/` -> same source

**MCP servers**: Generate minimal tool-specific config containing only active servers.

```python
# Hawk maintains canonical MCP registry
# ~/.config/hawk-hooks/registry/mcp/
#   github.yaml
#   postgres.yaml
#
# On sync, generates:
#   .mcp.json (for Claude Code)
#   .gemini/settings.json mcpServers section (for Gemini)
#   .codex/config.toml [mcp_servers] section (for Codex)
#   opencode.json mcp section (for OpenCode)
```

### C5. UX

**TUI selector**: `hawk ui`

```
hawk ui                    # Interactive enable/disable for current directory
hawk suggest               # AI-advisory: reads repo signals, proposes defaults
hawk status                # Show what's active in current directory per tool
```

`hawk ui` behavior:
1. Detect current directory
2. Load resolved set
3. Show Rich-based TUI with sections: Skills | Hooks | Commands | MCP
4. Checkboxes for enable/disable
5. On save: write `.hawk/config.yaml` + run `hawk sync`

`hawk suggest` behavior:
1. Read repo signals: `package.json`, `Cargo.toml`, `go.mod`, `.github/`, Dockerfile, etc.
2. Propose a default profile + specific items
3. Show proposal in TUI for user review
4. Never silently enable anything
5. Write `.hawk/config.yaml` only after explicit confirmation

---

## D. Hawk-Native Manifest & Adapter Mapping

### D1. `hawk-package.yaml` Schema

```yaml
# hawk-package.yaml -- defines a Hawk-installable package
name: my-awesome-hooks           # Required. Package name.
version: "1.0.0"                 # Required. Semver.
description: Security-focused hooks and skills for web development
author: pkronstrom
license: MIT
repository: https://github.com/user/my-awesome-hooks

# What this package provides
contents:
  skills:
    - path: skills/tdd/
      name: tdd
      description: Test-driven development workflow
    - path: skills/security-review/
      name: security-review
      description: Security-focused code review

  hooks:
    - path: hooks/block-secrets.py
      name: block-secrets
      events: [PreToolUse]
      matcher: "Bash|Write"
      type: command
    - path: hooks/format-on-save.sh
      name: format-on-save
      events: [PostToolUse]
      matcher: "Edit|Write"
      type: command

  commands:
    - path: commands/deploy.md
      name: deploy
      description: Deploy to production
    - path: commands/db-migrate.toml
      name: db-migrate
      description: Run database migrations
      format: toml  # Claude/OpenCode use .md, Gemini uses .toml

  prompts:
    - path: prompts/SECURITY.md
      name: security-guidelines
      description: Security coding guidelines context
      inject: context  # Always injected as context

  mcp_servers:
    - name: postgres
      transport: stdio
      command: npx
      args: ["-y", "@databases/mcp-postgres"]
      env:
        DATABASE_URL: "${DATABASE_URL}"

  # Tool-specific assets that don't map to a universal concept
  tool_assets:
    gemini:
      extension_manifest: gemini/gemini-extension.json
    codex:
      openai_yaml: skills/tdd/agents/openai.yaml

# Package-level metadata
tags: [security, web, testing]
compatibility:
  tools: [claude, gemini, codex, opencode]
  min_hawk_version: "2.0.0"
```

### D2. Package Inspector / Detector

```bash
hawk inspect <github-url|local-path>
```

Behavior:
1. If URL: shallow clone (`--depth 1`) to temp directory
2. Scan for known patterns (NO code execution):
   - `hawk-package.yaml` -> native hawk package
   - `SKILL.md` files -> skill(s)
   - `gemini-extension.json` -> Gemini extension
   - `.py`/`.sh`/`.js` with hook-like names -> hook candidates
   - `*.toml` command files -> Gemini commands
   - `*.md` with frontmatter -> command/prompt candidates
   - MCP server configs -> MCP definitions
3. Classify and report:

```
$ hawk inspect https://github.com/user/repo
Detected: hawk package (hawk-package.yaml found)
  2 skills: tdd, security-review
  1 hook: block-secrets (PreToolUse)
  1 command: deploy
  1 MCP server: postgres
  Compatible: claude, gemini, codex, opencode
```

For non-hawk repos:
```
$ hawk inspect https://github.com/user/cool-skill
Detected: standalone skill (SKILL.md found)
  1 skill: cool-skill
  Auto-wrap as hawk package? [Y/n]
```

### D3. Adapter Mapping Table

| Hawk Component | Claude Code | Gemini CLI | Codex CLI | OpenCode |
|---------------|-------------|------------|-----------|----------|
| **Skill** | Symlink to `.claude/skills/<name>/` or `~/.claude/skills/<name>/` | Symlink to `.gemini/skills/<name>/` or `~/.gemini/skills/<name>/` | Symlink to `.agents/skills/<name>/` or `~/.agents/skills/<name>/` | Symlink to `.opencode/skills/<name>/` or `~/.config/opencode/skills/<name>/` |
| **Hook (command)** | Entry in `settings.json` `hooks` with `type: "command"` pointing to script | Entry in `settings.json` `hooks` with `type: "command"` pointing to script | `notify` array (limited; full hooks not yet stable) | Plugin file in `.opencode/plugins/` wrapping the hook script |
| **Hook (prompt)** | Entry in `settings.json` `hooks` with `type: "prompt"` | Not supported (command hooks only) | Not supported | Plugin with `experimental.chat.system.transform` |
| **Command (.md)** | Symlink to `.claude/commands/<name>.md` (legacy) or skill | N/A (Gemini uses TOML) -> generate `.toml` adapter | N/A (Codex has no custom commands) -> register as skill | Symlink to `.opencode/commands/<name>.md` |
| **Command (.toml)** | N/A (Claude uses .md) -> generate `.md` adapter | Symlink to `.gemini/commands/<name>.toml` | N/A -> register as skill | Generate `.md` adapter |
| **Prompt/Context** | Add to `.claude/rules/<name>.md` or reference in CLAUDE.md | Reference in GEMINI.md or set as extension `contextFileName` | Add to `AGENTS.md` or `model_instructions_file` | Add to `instructions` array in `opencode.json` |
| **MCP Server** | Generate entry in `.mcp.json` | Generate entry in `.gemini/settings.json` `mcpServers` | Generate `[mcp_servers.<name>]` in `.codex/config.toml` | Generate entry in `opencode.json` `mcp` |
| **Extension** | N/A (Claude has no extension concept) | Link/install as Gemini extension | N/A | NPM plugin in `opencode.json` `plugin` array |

### D4. Event Name Mapping

| Hawk Event | Claude Code | Gemini CLI | Codex CLI | OpenCode |
|-----------|-------------|------------|-----------|----------|
| `pre_tool_use` | `PreToolUse` | `BeforeTool` | (not stable) | `tool.execute.before` |
| `post_tool_use` | `PostToolUse` | `AfterTool` | (not stable) | `tool.execute.after` |
| `session_start` | `SessionStart` | `SessionStart` | (not available) | `session.created` |
| `session_end` | `SessionEnd` | `SessionEnd` | (not available) | (via plugin) |
| `user_prompt_submit` | `UserPromptSubmit` | `BeforeAgent` | (not available) | (via plugin) |
| `stop` | `Stop` | `AfterAgent` | `agent-turn-complete` | `session.idle` / `stop` |
| `pre_compact` | `PreCompact` | `PreCompress` | (not available) | `experimental.session.compacting` |
| `notification` | `Notification` | `Notification` | (not available) | (via plugin) |
| `before_model` | N/A | `BeforeModel` | N/A | N/A |
| `after_model` | N/A | `AfterModel` | N/A | N/A |

---

## E. Implementation Plan

### Phase 0: Foundation Refactor (MVP prep)

**Goal**: Restructure existing hawk-hooks codebase for multi-tool support.

1. Rename internal concepts from "hooks-only" to generic "components"
2. Add `Tool` enum: `claude | gemini | codex | opencode`
3. Add `ComponentType` enum: `skill | hook | command | prompt | mcp_server`
4. Introduce `Registry` class: stores all installed components in `~/.config/hawk-hooks/registry/`
5. Introduce `ResolvedSet` class: computed view of what's active
6. Add `.hawk/config.yaml` parser (project-level)
7. Add `~/.config/hawk-hooks/profiles/*.yaml` support
8. Preserve backward compatibility: existing `~/.config/hawk-hooks/hooks/` layout still works

### Phase 1: Claude Code Adapter + Registry + Directory Profiles

**Goal**: Migrate current Claude Code support to new architecture; add skills + MCP management.

1. **Claude adapter** (`src/hawk_hooks/adapters/claude.py`):
   - Skills: symlink management to `.claude/skills/` and `~/.claude/skills/`
   - Hooks: generate `settings.json` hook entries (existing runner approach stays)
   - Commands: symlink to `.claude/commands/`
   - MCP: generate `.mcp.json` entries
   - Context: manage `.claude/rules/` files
2. **MCP registry** (`src/hawk_hooks/mcp_registry.py`):
   - Canonical MCP server definitions in `~/.config/hawk-hooks/registry/mcp/*.yaml`
   - Generate tool-specific configs on sync
3. **`hawk sync`** command: apply resolved set to Claude Code
4. **`hawk status`** command: show what's active
5. **`.hawk/config.yaml`** file support with profile resolution
6. Tests for Claude adapter

### Phase 2: Gemini CLI Adapter

**Goal**: Add Gemini CLI as second target.

1. **Gemini adapter** (`src/hawk_hooks/adapters/gemini.py`):
   - Skills: symlink to `.gemini/skills/` and `~/.gemini/skills/`
   - Hooks: generate `settings.json` hook entries (same JSON protocol as Claude)
   - Commands: generate TOML files in `.gemini/commands/` (convert from .md if needed)
   - MCP: generate `mcpServers` entries in `.gemini/settings.json`
   - Extensions: optional support for linking full Gemini extensions
2. **Command format converter**: .md <-> .toml bidirectional
3. Tests for Gemini adapter

### Phase 3: Codex CLI + OpenCode Adapters

**Goal**: Add remaining primary tools.

1. **Codex adapter** (`src/hawk_hooks/adapters/codex.py`):
   - Skills: symlink to `.agents/skills/`
   - MCP: generate `[mcp_servers]` TOML entries in `.codex/config.toml`
   - Hooks: `notify` array (limited support; document gaps)
   - Context: manage `AGENTS.md` references
2. **OpenCode adapter** (`src/hawk_hooks/adapters/opencode.py`):
   - Skills: symlink to `.opencode/skills/`
   - Hooks: generate plugin wrapper files
   - Commands: symlink to `.opencode/commands/`
   - MCP: generate `mcp` entries in `opencode.json`
   - Custom tools: optional support
3. Tests for both adapters

### Phase 4: Package Manager

**Goal**: Install/inspect packages from GitHub or local paths.

1. **`hawk install <source>`**: Install from GitHub URL, local path, or `hawk-package.yaml`
2. **`hawk inspect <source>`**: Classify contents without execution
3. **`hawk uninstall <name>`**: Remove package + clean up symlinks
4. **`hawk update <name>`**: Pull latest + re-sync
5. **Git fetching**: shallow clone (`--depth 1`), cache in `~/.config/hawk-hooks/cache/repos/`
6. **Auto-detection**: classify non-hawk repos (standalone skills, Gemini extensions, etc.)

### Phase 5: TUI & Auto-Apply

**Goal**: Interactive UI and directory-change automation.

1. **`hawk ui`**: Rich TUI with per-section toggles (Skills | Hooks | Commands | MCP)
2. **`hawk suggest`**: Read repo signals, propose defaults, user reviews in TUI
3. **`hawk shell init`**: Shell hook for auto-sync on directory change
4. **direnv integration**: `eval "$(hawk shell direnv)"`
5. **Hash-based caching**: <10ms cache-hit path

### Safety Notes

- **Never execute untrusted hook scripts during `hawk inspect`**. Inspection is read-only: parse YAML/JSON/TOML frontmatter, check file existence, read metadata. No `eval`, no `subprocess`, no `import`.
- **Sandboxing**: When `hawk install` fetches from GitHub, the package goes to `~/.config/hawk-hooks/registry/` but is NOT linked into any tool config until the user explicitly runs `hawk sync` or confirms in `hawk ui`.
- **Git fetching**: Always shallow clone. Cache repos with timestamp. `hawk update` does `git pull --depth 1`. Never auto-update without user action.
- **Symlink safety**: Before creating symlinks, verify target directories exist and are owned by current user. Never overwrite existing non-symlink files.
- **MCP server trust**: MCP server definitions from packages should be flagged as "package-provided" and require explicit user approval before first activation.

---

## Sources

### Claude Code
- [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)
- [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)
- [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp)
- [code.claude.com/docs/en/settings](https://code.claude.com/docs/en/settings)
- [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)

### Gemini CLI
- [geminicli.com/docs/extensions/reference](https://geminicli.com/docs/extensions/reference/)
- [geminicli.com/docs/hooks](https://geminicli.com/docs/hooks/)
- [geminicli.com/docs/tools/mcp-server](https://geminicli.com/docs/tools/mcp-server/)
- [geminicli.com/docs/cli/custom-commands](https://geminicli.com/docs/cli/custom-commands/)
- [geminicli.com/docs/cli/skills](https://geminicli.com/docs/cli/skills/)

### Codex CLI
- [developers.openai.com/codex/skills](https://developers.openai.com/codex/skills/)
- [developers.openai.com/codex/mcp](https://developers.openai.com/codex/mcp)
- [developers.openai.com/codex/config-reference](https://developers.openai.com/codex/config-reference/)
- [developers.openai.com/codex/guides/agents-md](https://developers.openai.com/codex/guides/agents-md/)

### OpenCode
- [opencode.ai/docs/plugins](https://opencode.ai/docs/plugins/)
- [opencode.ai/docs/config](https://opencode.ai/docs/config/)
- [opencode.ai/docs/mcp-servers](https://opencode.ai/docs/mcp-servers/)
- [opencode.ai/docs/skills](https://opencode.ai/docs/skills/)
- [opencode.ai/docs/custom-tools](https://opencode.ai/docs/custom-tools/)

### Cross-Tool Standards
- [agentskills.io/specification](https://agentskills.io/specification)
- [github.com/agentskills/agentskills](https://github.com/agentskills/agentskills)
- [skills.sh](https://skills.sh) (Vercel Skills CLI)
- [github.com/anthropics/skills](https://github.com/anthropics/skills)

### Other Tools
- [ampcode.com/manual](https://ampcode.com/manual)
- [block.github.io/goose](https://block.github.io/goose/)
- [kiro.dev/docs/cli/hooks](https://kiro.dev/docs/cli/hooks/)
- [aider.chat/docs](https://aider.chat/docs/)
- [docs.continue.dev](https://docs.continue.dev/)
