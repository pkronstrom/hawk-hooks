# Package-Scoped Registry

## Problem

The registry is flat: `registry/{skills,hooks,prompts,agents,mcp}/filename`. Two packages that ship a component with the same name (e.g., `code-reviewer.md`) clash.

Current workaround: on clash, the downloaded item is auto-renamed with a package prefix (`superpowers-code-reviewer.md`). This works but loses the original name and creates inconsistency between what the package declares and what's in the registry.

## Desired State

Package-scoped items coexist in the registry:

```
registry/agents/
  code-reviewer.md                    # builtin / ungrouped
  superpowers/code-reviewer.md        # from obra/superpowers
  my-skills/code-reviewer.md          # from my-skills package
```

Or flat with a package prefix convention that the resolver understands:

```
registry/agents/
  code-reviewer.md                    # builtin
  superpowers--code-reviewer.md       # from obra/superpowers (double-dash = namespace separator)
```

## What Needs to Change

### Registry
- `Registry.add()` / `has()` / `remove()` / `list()` need to support namespaced names
- `detect_clash()` should check within namespace, not globally

### Config Format
- Enabled lists currently use bare names: `agents: [code-reviewer.md]`
- Need to support `package/name` or `package--name` syntax
- Backward compat: bare names resolve to ungrouped items

### Resolver
- Resolution chain (global -> parent dirs -> project) must handle namespaced items
- Package-level enable/disable (`hawk enable obra/superpowers`) already works at config level, but resolver needs to map namespaced config entries to namespaced registry paths

### Adapters
- Symlink targets change: `~/.claude/agents/code-reviewer.md` -> which one?
- May need adapter-side namespacing too (prefixed symlinks)
- Or: adapters always use the resolved flat name (no change needed if resolver handles disambiguation)

### Downloader
- Remove the prefix-rename workaround once proper namespacing is in place
- `add_items_to_registry()` should accept a package namespace parameter

### Packages Index
- `packages.yaml` items already track `type` and `name` per item
- May need to store the namespace-qualified name

## Open Questions

- Subdirectory namespacing (`superpowers/code-reviewer.md`) vs flat convention (`superpowers--code-reviewer.md`)?
- Should adapters see the namespace or a flat view?
- How do users reference namespaced items in CLI commands? `hawk enable agents/superpowers/code-reviewer.md` vs `hawk enable superpowers:code-reviewer.md`?
- What happens to existing registries on upgrade? Migration path?
