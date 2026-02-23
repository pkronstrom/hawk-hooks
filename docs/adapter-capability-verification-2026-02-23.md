# Adapter Capability Verification (Cursor + Antigravity)

Date: 2026-02-23
Scope: Phase 1 verification gate for adapter parity plan.

## Cursor

### Verified from official docs

1. Rules / project instructions
   - Source: https://docs.cursor.com/context/rules
   - Decision: keep skills mapping to `.cursor/rules/`.

2. Custom commands (slash command style)
   - Source: https://docs.cursor.com/en/agent/chat/commands
   - Decision: map hawk `prompts` to Cursor `commands` directory.

3. Cursor CLI reuses rules + MCP config
   - Source: https://docs.cursor.com/en/cli/using
   - Decision: keep MCP in `.cursor/mcp.json`; keep rules behavior.

### Not verified as stable contract

1. Hook event model compatible with hawk canonical events.
2. Native file-based agent-definition contract equivalent to hawk agents.

Decision:
1. Keep hooks as `unsupported` for now.
2. Keep agent behavior unchanged (non-native placeholder), to be addressed in
   Phase 2 after verification.

## Antigravity

### Verified from official docs

1. MCP configuration file + workflow
   - Source: https://firebase.google.com/docs/studio/agentic-dev#add-mcp-server
   - Notes: docs describe `~/.gemini/antigravity/mcp_config.json`.
   - Decision: keep MCP adapter behavior.

### Not verified with first-party Antigravity docs

1. Prompt/command file conventions.
2. Hook event contract.
3. Agent definition format.

Decision:
1. Keep hooks `unsupported`.
2. Keep current skill mapping (provisional).
3. Defer prompt/agent parity implementation until official docs are confirmed.

## Phase 1 Outcomes Implemented

1. Added verification notes directly in:
   - `src/hawk_hooks/adapters/cursor.py`
   - `src/hawk_hooks/adapters/antigravity.py`
2. Implemented verified Cursor prompt mapping:
   - hawk `prompts` -> `.cursor/commands/`
3. Deferred unverified integrations to Phase 2/3 in plan:
   - `docs/plans/2026-02-23-cursor-antigravity-adapter-parity-plan.md`

