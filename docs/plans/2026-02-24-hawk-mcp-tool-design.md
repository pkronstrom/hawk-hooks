# Hawk MCP Tool Design

**Date:** 2026-02-24
**Status:** DRAFT

## Purpose

Expose hawk-hooks operations as an MCP tool so AI agents can register, enable, and sync components (skills, hooks, commands, agents, MCP servers, prompts) within their own conversation — enabling a tight write → add → enable → sync feedback loop.

## Installation

MCP is an optional dependency. The core `hawk` CLI does not require it.

```bash
# pip
pip install hawk-hooks[mcp]

# uv (preferred)
uv pip install hawk-hooks[mcp]
# or as a tool
uv tool install hawk-hooks --with fastmcp
```

`hawk mcp` subcommand fails gracefully if `fastmcp` is not installed:

```
hawk mcp requires FastMCP. Install with:
  uv pip install hawk-hooks[mcp]
```

## Architecture

### Single tool, action dispatch

Following the dodo/goose pattern — one MCP tool named `hawk` with `action: str` + `params: dict | None`.

```python
@mcp.tool()
async def hawk(action: str, params: dict | None = None) -> dict:
    data = {"action": action, **(params or {})}
    result = await handle_action(data, deps)
    return result
```

### Module layout

```
src/hawk_hooks/
├── mcp_server.py       # FastMCP server + hawk tool wrapper
├── mcp_handler.py      # handle_action() dispatch — testable without MCP
└── cli.py              # hawk mcp subcommand (launches mcp_server)
```

`mcp_handler.py` is a plain async function that takes a dict and returns a dict. Tests call it directly. `mcp_server.py` is a thin FastMCP wrapper.

### CLI entry point

```bash
hawk mcp          # starts stdio MCP server
```

Tool config (e.g. Claude `settings.json`):

```json
{
  "mcpServers": {
    "hawk": {
      "command": "hawk",
      "args": ["mcp"]
    }
  }
}
```

### Server instructions

```
Hawk component manager. Single tool with action dispatch.
Use action='describe' to see all available actions and their parameters.
Use action='describe', params={action_name: '<name>'} for details on one action.
Actions: describe, list, status, list_packages, add, remove, enable, disable, sync, download, update, remove_package.
```

## Actions

### Read Actions

#### `describe`

Self-describe available actions and their parameters.

**Params:**
- `action_name?: str` — if provided, return details for that action only

**Returns:** Action names, param schemas, descriptions. Without `action_name`, returns a summary of all actions. With `action_name`, returns full param details including types, defaults, and hints.

---

#### `list`

List registry contents.

**Params:**
- `type?: str` — component type filter (`skill`, `hook`, `command`, `agent`, `mcp`, `prompt`)

**Returns:** Components grouped by type, with enabled/disabled state per scope.

```json
{
  "components": {
    "skills": [
      {"name": "my-skill.md", "enabled_global": true, "enabled_local": false, "package": "superpowers"}
    ]
  },
  "context": { ... }
}
```

---

#### `status`

Show current state for a scope.

**Params:**
- `dir?: str` — project directory (default: global)

**Returns:**
- Enabled components for the scope
- Installed tools and their status
- Unsynced component count
- Active profile (if any)

---

#### `list_packages`

List installed packages.

**Params:** none

**Returns:** Package names, URLs, item counts, last update time.

---

### Write Actions

#### `add`

Register a component in the hawk registry. Supports file path OR inline content.

**Params:**
- `type: str` — component type (required)
- `path?: str` — absolute path to source file/directory
- `content?: str` — inline content (written to temp file, then registered)
- `name?: str` — override name (default: filename from path, or required with `content`)
- `force?: bool` — overwrite if exists (default: false)
- `enable?: bool` — enable in global config after adding (default: false)
- `sync?: bool` — run sync after adding (default: false)
- `dir?: str` — if provided with `enable`, enable in this directory's config instead of global

**Validation:**
- Exactly one of `path` or `content` must be provided
- `name` is required when using `content`
- `type` must be a valid ComponentType

**Returns:**
```json
{
  "added": "my-skill.md",
  "type": "skill",
  "registry_path": "~/.config/hawk-hooks/registry/skills/my-skill.md",
  "enabled": true,
  "sync_results": [ ... ],
  "context": { ... }
}
```

---

#### `remove`

Remove a component from the registry.

**Params:**
- `type: str` — component type (required)
- `name: str` — component name (required)
- `sync?: bool` — run sync after removal (default: false)

**Returns:** Confirmation + sync results if requested.

---

#### `enable`

Enable a component or package.

**Params:**
- `target: str` — `"type/name"`, package name, `"package/type"`, or bare name
- `dir?: str` — target directory config (default: global)
- `sync?: bool` — run sync after enabling (default: false)

**Returns:** List of enabled items + sync results.

---

#### `disable`

Disable a component or package.

**Params:**
- `target: str` — same format as `enable`
- `dir?: str` — target directory config (default: global)
- `sync?: bool` — run sync after disabling (default: false)

**Returns:** List of disabled items + sync results.

---

#### `sync`

Sync enabled components to tool configs.

**Params:**
- `dir?: str` — project directory (omit for global-only)
- `tool?: str` — specific tool to sync (default: all enabled tools)
- `force?: bool` — ignore cache, force full sync (default: false)
- `dry_run?: bool` — show what would change without changing (default: false)

**Returns:** Per-tool sync results with linked/unlinked/skipped/errors.

```json
{
  "results": {
    "claude": {"linked": ["skills/my-skill.md"], "unlinked": [], "skipped": [], "errors": []},
    "gemini": {"linked": ["skills/my-skill.md"], "unlinked": [], "skipped": [], "errors": []}
  },
  "context": { ... }
}
```

---

#### `download`

Download and install a package from a git URL.

**Params:**
- `url: str` — git URL (required)
- `select_all?: bool` — install all items (default: false — installs nothing without this or a select callback)
- `replace?: bool` — replace existing items (default: false)
- `name?: str` — override package name
- `enable?: bool` — enable added items (default: false)
- `sync?: bool` — sync after install (default: false)

**Returns:** Added/skipped items, package name, clashes if any.

---

#### `update`

Update installed packages.

**Params:**
- `package?: str` — specific package (default: all)
- `check?: bool` — check only, don't update (default: false)
- `force?: bool` — force update even if no changes (default: false)
- `prune?: bool` — remove items no longer in upstream (default: false)

**Returns:** Per-package update report.

---

#### `remove_package`

Remove an installed package and its components.

**Params:**
- `name: str` — package name (required)

**Returns:** Removed items list.

---

## CWD Context Hints

Every response includes a `context` block to help agents understand scope:

```json
{
  "context": {
    "cwd": "/Users/foo/myproject",
    "cwd_registered": true,
    "local_config": "/Users/foo/myproject/.hawk/config.yaml",
    "hint": "Local hawk config exists — pass dir='/Users/foo/myproject' to target it"
  }
}
```

When `cwd_registered` is false and no `dir` was passed, operations target global config. The hint surfaces when a local scope is available but wasn't targeted.

When there is no local config, the hint is omitted (no noise).

## Response Design

Following the MCP design patterns from goose/dodo:

1. **Structured data** — return dicts, never JSON strings
2. **Enriched validation errors** — include got value, allowed values, hints
3. **Trimmed lists** — summaries in `list`, full details in `describe`
4. **No internal state leakage** — strip `_shared`, paths to temp files, etc.

### Error format

```json
{
  "error": "Parameter 'type' must be one of: skill, hook, command, agent, mcp, prompt (got 'script')",
  "hint": "Use action='list' to see registered components by type"
}
```

## Implementation Notes

### Dependencies

- `fastmcp` — optional, gated behind `hawk-hooks[mcp]` extra
- No other new dependencies

### Testability

`mcp_handler.py` exports `handle_action(data: dict, deps: Deps) -> dict` where `Deps` bundles `Registry`, config loaders, and sync functions. Tests inject mocks via `Deps`.

### CWD detection

The MCP server can read CWD from the FastMCP context or fall back to `os.getcwd()`. This powers the context hints without requiring the caller to pass `dir` explicitly.

### Sync flag design

The `sync` flag on `add`/`remove`/`enable`/`disable` defaults to `false`. This keeps individual operations fast and predictable. Agents that want the full loop pass `sync: true`. This matches the CLI where `hawk add` and `hawk sync` are separate commands, but `--enable` exists for convenience.

### Log capture

Service functions (`download_and_install`, `update_packages`, etc.) accept a `log: Callable[[str], None]` parameter. The MCP handler passes a list collector, then includes accumulated logs in the response under a `log` key for transparency.
