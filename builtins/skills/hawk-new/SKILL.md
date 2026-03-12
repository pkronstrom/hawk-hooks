---
name: hawk-new
description: Create or add hawk components (commands, hooks, agents, MCP servers, skills)
---

# hawk-new

Help the user add a new component to their hawk setup.

## Step 1: Determine Intent

Ask the user what they want to do:

1. **Create new** — scaffold a new component from scratch
2. **Add existing** — register a file/directory already on disk
3. **Add from URL** — download components from a git repo or configure an MCP server from docs

## Step 2: Route

### If adding from URL

Run `hawk download <url>` and let the user pick which components to install. After download, ask if they want to enable the added components (`hawk enable <name>`) and run `hawk sync` to activate.

### If adding an existing file

Run `hawk add <type> <path>` to register it. Ask the user for the component type if not obvious from the path. Then offer to enable it (`hawk enable <type>/<name>`) and run `hawk sync`.

### If creating new

Continue to Step 3.

## Step 3: Create New Component

Ask the user:

1. **What type?** — command, hook, agent, mcp, or skill
2. **Where?** — project-local (`.hawk/`) or global registry (`~/.config/hawk-hooks/registry/`)

## Step 4: Read the Guide

Read the matching guide file from this skill's directory:

| Type | Guide file |
|------|-----------|
| command | `command-guide.md` |
| hook | `hook-guide.md` |
| agent | `agent-guide.md` |
| mcp | `mcp-guide.md` |
| skill | `skill-guide.md` |

Follow the guide to scaffold the component with the user's input.

## Step 5: Register and Sync

After creating the file(s):

1. If placed outside the registry, run `hawk add <type> <path>`
2. Ask: "Want me to enable this and run `hawk sync`?"

## Available hawk Commands

| Command | Purpose |
|---------|---------|
| `hawk new <type> <name>` | CLI scaffolding (alternative to this skill) |
| `hawk add <type> <path>` | Register a component |
| `hawk download <url>` | Download from git repo |
| `hawk sync` | Push config to tool directories |
| `hawk status` | Show what's enabled |
