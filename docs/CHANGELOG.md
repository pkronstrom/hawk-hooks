# Changelog

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
