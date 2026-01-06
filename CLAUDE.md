# captain-hook

A modular Claude Code hooks manager.

## Architecture

```
src/captain_hook/
├── config.py      # Configuration loading/saving (JSON)
├── scanner.py     # Auto-discovery of hook scripts
├── generator.py   # Generates bash runners for performance
├── installer.py   # Registers hooks in Claude settings
└── cli.py         # Interactive CLI with questionary + rich
```

## Key Concepts

- **Hooks**: Scripts in `~/.config/captain-hook/hooks/{event}/` that run on Claude events
- **Runners**: Generated bash scripts that chain enabled hooks (for fast execution)
- **Events**: pre_tool_use, post_tool_use, stop, notification, user_prompt_submit

## How It Works

1. User runs `captain-hook install` → registers bash runners in `~/.claude/settings.json`
2. User runs `captain-hook toggle` → enables/disables hooks, regenerates runners
3. Claude triggers event → bash runner executes → chains enabled hooks

## File Locations

- Global config: `~/.config/captain-hook/config.json`
- Hooks: `~/.config/captain-hook/hooks/{event}/*.{py,js,sh,ts,md}`
- Runners: `~/.config/captain-hook/runners/{event}.sh`
- Venv: `~/.config/captain-hook/.venv/`

## Development

```bash
pip install -e .
captain-hook  # Run the CLI
```

## Testing Changes

After modifying hook-related code:
1. Run `captain-hook toggle` to regenerate runners
2. Test with a Claude Code session

## Adding New Events

1. Add to `EVENTS` list in `config.py`
2. Add to `CLAUDE_EVENTS` mapping in `installer.py`
3. Create directory in `hooks/`
