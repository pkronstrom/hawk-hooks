# hawk-hooks

![hawk banner](docs/hawk_banner.png)

One registry for all your AI coding tools — skills, hooks, agents, and prompts synced everywhere.

<!-- TODO: asciinema recording of `hawk` TUI dashboard -->

Configure your AI tools once. hawk-hooks manages a single registry of components — hooks, skills, agents, prompts, and MCP servers — and syncs them into Claude Code, Gemini CLI, Codex CLI, and more.

No more copying files between `~/.claude`, `~/.gemini`, and `~/.codex`. No more forgetting which project has which hooks enabled.

## Features

- **One registry, many tools** — Write a hook or skill once, sync it to Claude Code, Gemini CLI, Codex CLI, OpenCode, Cursor, and more
- **Hierarchical config** — Global defaults, monorepo overrides, per-project tweaks — all resolved automatically
- **Git-based packages** — `hawk download <url>` to install community components, `hawk update` to stay current
- **Interactive TUI** — Full dashboard for toggling components, browsing the registry, and managing packages
- **Canonical hook events** — One hook script auto-translates to each tool's native event format and wiring
- **Batteries included** — Starter kit with safety hooks, code review agents, and cross-tool delegation prompts

## Quick Start

```bash
# Install (uv recommended)
uv tool install git+https://github.com/pkronstrom/hawk-hooks.git

# Or with pipx
pipx install git+https://github.com/pkronstrom/hawk-hooks.git
```

```bash
# Launch the TUI — auto-detects your AI tools on first run
hawk
```

The interactive dashboard lets you browse, toggle, and sync components without memorizing CLI commands. Everything below can also be done from the TUI.

### Global vs Project Scope

By default, hawk manages components globally — one set of skills, hooks, and agents across all your projects. This is the recommended starting point.

For per-project overrides, run `hawk init` in a project directory. This creates a `.hawk/config.yaml` where you can enable or disable specific components while still inheriting your global config.

### Packages

Import components from any git repo — Claude Code skills, hook collections, agent definitions, or MCP configs:

```bash
hawk download https://github.com/someone/claude-skills
hawk sync
hawk update    # Pull latest when available
```

hawk auto-classifies files by type and lets you pick what to install.

## What hawk manages

| Type | What it is | Example |
|------|-----------|---------|
| **Skills** | Instruction files that shape how your AI tool behaves | `code-style.md` |
| **Hooks** | Event-triggered scripts (pre-tool, post-tool, stop, etc.) | `file-guard.py` |
| **Prompts** | Slash commands / reusable prompt templates | `commit.md` |
| **Agents** | Autonomous agent definitions for task delegation | `code-reviewer.md` |
| **MCP** | Model Context Protocol server configs | `github.yaml` |

All components live in a single registry (`~/.config/hawk-hooks/registry/`) and get synced into each tool's native config format.

## Supported Tools

| Tool | Skills | Hooks | Prompts | Agents | MCP |
|------|--------|-------|---------|--------|-----|
| Claude Code | yes | yes | yes | yes | yes |
| Gemini CLI | yes | yes | yes | yes | yes |
| Codex CLI | yes | partial | yes | yes | yes |
| OpenCode | yes | partial | yes | yes | yes |
| Cursor | yes | — | yes | — | yes |

Hook support varies by tool — Claude and Gemini have native hook APIs, while Codex and OpenCode use generated bridge wrappers for supported events.

More tools coming.

## CLI Reference

The TUI (`hawk`) is the recommended way to use hawk, but all operations are also available as commands:

```bash
hawk                          # Interactive TUI dashboard
hawk init [dir]               # Register a project directory
hawk status                   # Show registry and sync state
hawk sync                     # Sync components to all tools
hawk add <type> <path>        # Add a component to the registry
hawk remove <type> <name>     # Remove a component
hawk download <url>           # Import components from a git repo
hawk scan <path>              # Import from a local directory
hawk packages                 # List installed packages
hawk update [package]         # Update packages from git
hawk new <type> <name>        # Scaffold a new component
hawk clean                    # Remove all hawk-managed symlinks
```

## Development

```bash
git clone https://github.com/pkronstrom/hawk-hooks.git
cd hawk-hooks
uv tool install --editable .
```

## License

MIT
