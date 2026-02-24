# hawk-hooks

![hawk banner](docs/hawk_banner.png)

**One registry for all your AI coding tools.** Skills, hooks, agents, prompts, and MCP servers — configured once, synced everywhere.

<p align="center">
  <img src="docs/demo.gif" alt="hawk TUI demo" width="720">
</p>

You have Claude Code, Gemini CLI, and Codex CLI all running on the same codebase — each with its own config format, its own directory, its own way of wiring hooks. You copy files between `~/.claude`, `~/.gemini`, and `~/.codex`. You forget which project has which hooks enabled. You update a skill in one place and forget the other two.

hawk-hooks manages a single registry of components and syncs them into every tool's native format. Write once, enable anywhere.

## Features

- **One registry, every tool** — Write a hook or skill once, hawk symlinks it into Claude Code, Gemini CLI, Codex CLI, OpenCode, and Cursor
- **Hierarchical config** — Global defaults, monorepo overrides, per-project tweaks — resolved automatically through a config chain
- **Git-based packages** — `hawk download <url>` to install community skills and hooks, `hawk update` to stay current
- **Interactive TUI** — Dashboard for toggling components, managing packages, and browsing your registry without memorizing CLI commands
- **Canonical hook events** — One hook script auto-translates to each tool's native event format and wiring
- **Batteries included** — Ships with safety hooks (`file-guard`, `dangerous-cmd`), code review agents, and cross-tool delegation prompts

## Quick Start

```bash
# Install
uv tool install git+https://github.com/pkronstrom/hawk-hooks.git

# Launch the TUI — auto-detects installed AI tools on first run
hawk
```

The first-run wizard scans for installed tools, sets up your registry, and optionally installs the built-in starter kit. From there, the dashboard is your home base.

### Install a package

```bash
# Import skills from any git repo
hawk download https://github.com/anthropics/skills

# Enable what you want
hawk enable anthropics/skills

# Push to all tools
hawk sync
```

### Per-project overrides

```bash
# In a project directory — creates .hawk/config.yaml
hawk init

# Now this project can enable/disable components independently
# while still inheriting your global config
```

## What hawk manages

| Type | What it is | Example |
|------|-----------|---------|
| **Skills** | Instruction files that shape how your AI tool behaves | `frontend-design.md` |
| **Hooks** | Event-triggered scripts (pre-tool, post-tool, stop, etc.) | `file-guard.py` |
| **Prompts** | Slash commands and reusable prompt templates | `commit.md` |
| **Agents** | Autonomous agent definitions for task delegation | `code-reviewer.md` |
| **MCP** | Model Context Protocol server configs | `github.yaml` |

All components live in `~/.config/hawk-hooks/registry/` and get synced into each tool's native config format via symlinks.

## Supported Tools

| Tool | Skills | Hooks | Prompts | Agents | MCP |
|------|--------|-------|---------|--------|-----|
| Claude Code | yes | yes | yes | yes | yes |
| Gemini CLI | yes | yes | yes | yes | yes |
| Codex CLI | yes | partial | yes | yes | yes |
| OpenCode | yes | partial | yes | yes | yes |
| Cursor | yes | — | yes | — | yes |

Hook support varies by tool — Claude and Gemini have native hook APIs, while Codex and OpenCode use generated bridge wrappers for supported events.

## CLI Reference

The TUI (`hawk`) is the primary interface, but all operations are available as commands:

```
hawk                          # Interactive TUI dashboard
hawk init [dir]               # Register a project directory
hawk status                   # Show registry and sync state
hawk sync                     # Sync components to all tools
hawk add <type> <path>        # Add a component to the registry
hawk remove <type> <name>     # Remove a component
hawk enable <target>          # Enable a component, package, or type
hawk disable <target>         # Disable a component, package, or type
hawk download <url>           # Import components from a git repo
hawk scan <path>              # Import from a local directory
hawk packages                 # List installed packages
hawk update [package]         # Update packages from git
hawk new <type> <name>        # Scaffold a new component
hawk clean                    # Remove all hawk-managed symlinks
```

## How it works

```
~/.config/hawk-hooks/
├── config.yaml          # Global config (which components are enabled)
├── registry/            # All components live here
│   ├── skills/
│   ├── hooks/
│   ├── prompts/
│   ├── agents/
│   └── mcp/
├── packages.yaml        # Installed package index
└── profiles/            # Named config profiles

project/.hawk/
└── config.yaml          # Per-project overrides
```

On `hawk sync`, the resolver walks the config chain (global → registered parent dirs → project) to compute which components are active, then each tool's adapter symlinks them into the right place in the right format.

## Development

```bash
git clone https://github.com/pkronstrom/hawk-hooks.git
cd hawk-hooks
uv tool install --editable .
python3 -m pytest tests/ -q    # 630 tests
```

## License

MIT
