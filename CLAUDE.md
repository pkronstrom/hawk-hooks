# hawk-hooks (v2)

`hawk-hooks` is now a multi-tool component manager with registry-backed sync.
The primary architecture is the v2 stack (`cli.py`, `v2_config.py`, `v2_sync.py`, adapters, resolver, and `v2_interactive/`).

## Primary Architecture (v2)

```
src/hawk_hooks/
├── cli.py                  # Main CLI entry (hawk + hawk-hooks commands)
├── v2_config.py            # YAML config + directory index + package index
├── v2_sync.py              # Sync/clean orchestration + cache + result formatting
├── resolver.py             # Global/profile/dir-chain resolution
├── registry.py             # Registry add/remove/replace/list operations
├── downloader.py           # Git/local package scan + metadata-aware classification
├── event_mapping.py        # Canonical hook event contract + per-tool support
├── adapters/               # Claude, Gemini, Codex, OpenCode, Cursor, Antigravity
└── v2_interactive/         # Dashboard, toggles, wizard, settings editor
```

## Config + Data Locations

- Global config: `~/.config/hawk-hooks/config.yaml`
- Registry: `~/.config/hawk-hooks/registry/`
- Profiles: `~/.config/hawk-hooks/profiles/*.yaml`
- Packages index: `~/.config/hawk-hooks/packages.yaml`
- Per-project config: `<project>/.hawk/config.yaml`
- Sync cache: `~/.config/hawk-hooks/cache/resolved/`

## Core Concepts

- Registry-managed components: `skills`, `hooks`, `prompts`, `agents`, `mcp`.
- Resolution chain: `global` -> registered parent dirs -> current project (with optional profiles).
- Per-tool adapters own concrete sync behavior and capability warnings.
- Hook events use a canonical contract in `event_mapping.py` with explicit unsupported handling.

## Typical Workflow

```bash
hawk init
hawk add <type> <path>
hawk sync
hawk status
```

For package-based workflows:

```bash
hawk download <url>
hawk packages
hawk update
```

## Legacy (v1) Note

Legacy v1 modules (`cli.py`, `config.py`, `sync.py`, `interactive/`, etc.) remain for migration and compatibility, but new development should target v2 modules.
