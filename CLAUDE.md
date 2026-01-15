# hawk-hooks

A modular Claude Code hooks manager.

## Architecture

```
src/hawk_hooks/
├── config.py      # Configuration loading/saving (JSON)
├── scanner.py     # Auto-discovery of hook scripts
├── generator.py   # Generates bash runners for command/stdout hooks
├── installer.py   # Registers hooks in Claude settings + syncs prompt hooks
├── cli.py         # Interactive CLI with Rich
└── rich_menu.py   # Custom Rich-based interactive menu system
```

## Hook Types

| Pattern | Type | How it works |
|---------|------|--------------|
| `*.py`, `*.sh`, `*.js`, `*.ts` | Command | Executed, receives JSON stdin |
| `*.stdout.md`, `*.stdout.txt` | Stdout | Content cat'd to stdout (context injection) |
| `*.prompt.json` | Native Prompt | Registered as `type: "prompt"` in Claude settings |

## Key Concepts

- **Command hooks**: Scripts that process JSON input and can block/modify
- **Stdout hooks**: Files that inject text into Claude's context
- **Native prompt hooks**: LLM-evaluated hooks (Haiku decides approve/block)
- **Runners**: Generated bash scripts that chain enabled command/stdout hooks
- **Events**: pre_tool_use, post_tool_use, stop, subagent_stop, notification, user_prompt_submit, session_start, session_end, pre_compact

## File Locations

- Global config: `~/.config/hawk-hooks/config.json`
- Hooks: `~/.config/hawk-hooks/hooks/{event}/`
- Runners: `~/.config/hawk-hooks/runners/{event}.sh`
- Venv: `~/.config/hawk-hooks/.venv/`

## How It Works

1. `hawk-hooks install` → registers bash runners in `~/.claude/settings.json`
2. `hawk-hooks toggle` → enables/disables hooks, regenerates runners, syncs prompt hooks
3. Claude triggers event → bash runner executes → chains enabled hooks
4. Native prompt hooks are registered directly as `type: "prompt"` in Claude settings

## Development

```bash
pip install -e .
hawk-hooks  # Run the CLI (or just `hawk`)
```

After modifying hook-related code:
1. Run `hawk-hooks toggle` to regenerate runners
2. Test with a Claude Code session

## Adding New Hook Types

1. Update `scanner.py` to detect the pattern
2. Update `generator.py` if it needs runner handling
3. Update `installer.py` if it needs direct Claude registration
