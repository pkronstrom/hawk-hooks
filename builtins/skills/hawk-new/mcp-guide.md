# MCP Server Guide

MCP (Model Context Protocol) configs tell hawk how to wire an MCP server into the user's tool setup. Hawk manages the MCP section in each tool's config file.

## Format

- Single `.yaml` file (or `.json`)
- Defines the server name, command, args, and environment variables
- Placed in `mcp/` directory

## Adding from a URL or Docs

If the user provides a URL to an MCP server's documentation, npm page, or GitHub repo:

1. Fetch the URL to find the server's install/config instructions
2. Extract: package name, command to run, required args, env vars
3. Scaffold the YAML config below
4. For git repos with hawk-compatible layout, prefer `hawk download <url>` instead

## YAML Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Server identifier (used in tool configs) |
| `command` | yes | Executable to run (`npx`, `uvx`, `node`, `python`, etc.) |
| `args` | no | List of arguments to pass to the command |
| `env` | no | Map of environment variables the server needs |

## Tips

- Use `npx -y` for npm packages so they auto-install
- Use `uvx` for Python packages published to PyPI
- Environment variables often include API keys — use placeholders and tell the user to fill them in
- Server name should be short and descriptive (e.g., `github`, `slack`, `postgres`)

## Template

```yaml
name: my-server
command: npx
args:
  - -y
  - "@namespace/mcp-server-name"
env:
  API_KEY: "your-api-key-here"
```

## Example: Python-based Server

```yaml
name: my-python-server
command: uvx
args:
  - mcp-server-name
  - --flag
  - value
env:
  DATABASE_URL: "postgresql://localhost:5432/mydb"
```
