# Changelog

## 2026-08-27 (v0.12.0)

### Added

- Skill bundles:
  - `SKILL.md` can declare `requires:` for companion agents, hooks, prompts, and MCP servers.
  - `hawk sync` expands enabled skills to include their required companion components.
  - `hawk scan` and `hawk download` import typed companion directories inside skills (`agents/`, `hooks/`, `prompts/`, `commands/`, `mcp/`).
- Archive imports: `hawk add`, `hawk scan`, and `hawk download` accept `.zip`, `.tar.gz`, `.tgz`, and `.skill` archives, local or remote, with batch classification.
- New builtin skills: `agent-team-openspec`, `bell`, `claudemd-bootstrap`, `grill-singlefile`, `grill-docs-singlefile`, `rev`.
- New builtin commands: `/humanize`, `/stop-babbling`, `/whats-next`, `/eng-converge`, `/antigravity` (and its `/agy` alias), `/agent-team-openspec`.

### Changed

- Gemini CLI was sunset by Google and replaced by Antigravity. The `gemini` adapter is gone; existing configs migrate automatically and `hawk cleanup-gemini` removes what the old integration left behind.
- Builtin model lineups updated for current Claude, Codex, and Antigravity releases.

### Fixed

- `codex`: MCP server names containing dots are sanitized instead of producing invalid config.
- `codex`: orphaned agent entries are purged on sync.
- Hook command path resolution no longer crashes on very long inline commands.

### Security

- Archive extraction rejects tar members that resolve outside the extraction directory, and link or device entries. Python trusts tar archives by default before 3.14, so a crafted `.tar.gz` could write anywhere the user could.
- Archives that expand past 2 GiB are refused before extraction.
- Remote archive URLs must use https, are fetched with a timeout, and are capped at 512 MiB.
- Copying a component directory into the registry preserves symlinks instead of following them, so a skill directory cannot smuggle out files it links to.

### Removed

- Builtin skill `spec-flow`, which moved to [Formulae Magicae](https://github.com/pkronstrom/formulae-magicae) along with the rest of the portable, host-neutral skills.

## 2026-02-22 (v0.8.0)

### Added

- Cross-tool hook registration rollout:
  - Canonical event contract + support levels in `event_mapping.py`
  - Gemini native hook registration
  - Codex notify-style hook bridge
  - Explicit unsupported-hook warnings for OpenCode/Cursor/Antigravity
- Dashboard Registry browser:
  - New `Registry` action in TUI
  - Read-only grouped browse by component type
  - Per-item metadata: type, owning package, and file size
  - Enter opens selected item in `$EDITOR`

### Changed

- `hawk sync` output is compact by default (per-tool counts).
- `hawk sync -v/--verbose` restores per-item detailed output.
- Dashboard sync display now uses compact formatting.
- Continue prompts in dashboard flows now accept Enter, `q`, and Ctrl+C.
- Dashboard scope detection now resolves nearest registered ancestor directory.
- Dashboard component counts now reflect resolved chain output (global + parent layers + local overrides).

### Docs

- `CLAUDE.md` updated to describe v2 as the primary architecture.
- v2 completion plan reconciled with implemented Phase A/B/C/D/E status.

## 2026-02-21

### Breaking

- Canonical slash-item schema changed from `commands` to `prompts`.
- v2 runtime now resolves/syncs prompt entries as the primary slash concept.
- Legacy `commands` layout is no longer the long-term runtime model.

### Added

- `hawk migrate-prompts` one-shot upgrader:
  - `--check` to preview migration impact
  - `--apply` to perform migration
  - `--no-backup` to skip backup generation
- Migration coverage for:
  - global config fields (`global.commands -> global.prompts`)
  - directory config layers (`commands.enabled/disabled -> prompts.enabled/disabled`)
  - tool overrides (`commands.extra/exclude -> prompts.extra/exclude`)
  - registry move (`registry/commands/* -> registry/prompts/*`)
  - package metadata rewrite (`command -> prompt`)

### Changed

- v2 interactive dashboard labeling now uses **Prompts**.
- Downloader classification maps legacy `commands/` directories to prompt items.
- Legacy v1 destination key usage is aligned to `prompts` terminology (with compatibility fallback where needed).

### Docs

- Added deprecation inventory: `docs/DEPRECATE.md`
- Added migration guide: `docs/MIGRATION-v3-prompts.md`
