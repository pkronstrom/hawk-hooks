# Formulae Magicae Repository Migration Plan

**Status:** Approved for future execution; this document does not perform the migration.

**Goal:** Rename and expand the existing Spellbook repository into a public, standards-first collection of portable agent skills, with a structurally similar private companion repository.

**Architecture:** `formulae-magicae` becomes the canonical public source for portable skills, while vendor and Hawk manifests remain thin distribution wrappers around the open Agent Skills layout. `formulae-magicae-privatae` follows the same convention for selectively migrated private skills. Hawk retains only its product-specific authoring skill in the wheel and consumes Formulae Magicae as an optional external package.

---

## Summary

Rename `pkronstrom/spellbook` to `pkronstrom/formulae-magicae` and relaunch it as **Formulae Magicae**, subtitled *Ars Automata*: a standards-first collection of portable skills for Claude Code, Codex, Hawk, and other Agent Skills-compatible hosts.

Create the private companion repository `formulae-magicae-privatae`. Use clean migration commits rather than importing Hawk's historical commit graph.

## Public Repository

- Preserve Spellbook's existing history, `summon`, and `portal` by renaming the repository in place.
- Use a flat canonical layout under `skills/<name>/`; every skill contains its own scripts, references, templates, assets, internal prompts, and related resources.
- Initially publish:
  - `summon`
  - `portal`
  - `bento-slides`
  - `singlefile`
  - `visualize`
  - `transcribe-media`
  - `tts`
  - `pr-voice-review`
  - `pr-voice-review-single-file`
  - `spec-flow`
- Defer `agent-team` and `agent-team-openspec` until their Claude-, Superpowers-, and private `/rev3` dependencies are redesigned.
- Make all migrated instructions host-neutral: remove `builtins/...` references and hard-coded `~/.claude/skills/...` paths, resolving companion files relative to the active skill directory.
- Keep the intentional relationship between the two PR review skills explicit; ensure installing `pr-voice-review-single-file` also installs its sibling or move their shared narration guidance into a neutral bundled reference.
- Retain MIT licensing and add third-party notices for fonts, wordlists, runtimes, and other redistributed assets.

## Distribution and Interfaces

- Add `hawk-package.yaml` so Hawk can install the complete repository or selected skills:
  - Remote users use `hawk download` and `hawk update`.
  - Local development uses `hawk scan <checkout> --all --replace`; subsequent `hawk update` re-scans the recorded path.
  - Do not add a new live-link command.
- Replace Spellbook's Claude metadata with:
  - A root `formulae-magicae` plugin providing the complete collection.
  - Marketplace entries for each individual skill, using each skill directory as a single-skill plugin source.
  - Version `1.0.0`, with README migration instructions for the old `spellbook@spellbook` identity.
- Add a root `.codex-plugin/plugin.json` for the complete collection. Document individual Codex installation through `$skill-installer`, repository subpaths, and supported symlink locations.
- Document generic/manual installation and OpenSkills as optional paths; neither becomes part of the canonical format.
- Base portability on the [Agent Skills specification](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx), with vendor manifests as additive wrappers.

## Hawk Changes

- Retain only the Hawk-specific authoring skill as a bundled wheel resource.
- Remove the extracted public skills and their assets from Hawk's wheel.
- Change first-run setup to offer Formulae Magicae as an optional network-installed collection. Declining it or encountering a network failure must not block Hawk setup.
- Update package metadata, tests, README, and release notes to distinguish:
  - Bundled Hawk authoring support.
  - Optional remote Formulae Magicae skills.
- Document migration for existing `hawk-builtins` installations rather than silently replacing users' package ownership.

## Private Companion

- Create private `pkronstrom/formulae-magicae-privatae` with the same `skills/<name>/SKILL.md` convention and its own `hawk-package.yaml`.
- Initially migrate the three private skills:
  - `backlog-shaping`
  - `bezala`
  - `review-work`
- Include `review-work`'s genuinely required scripts, schemas, prompts, and `/rev*` command shortcuts.
- Leave unrelated agents, hooks, commands, MCP definitions, and generated `.claude`/`.codex`/`.gemini` output behind until individually reviewed.
- Exclude credentials, machine configuration, synced output, caches, and local runtime state. Run a full secret audit before creating the private remote.

## Cover and Presentation

- Generate a landscape README hero named `assets/formulae-magicae-grimoire.png`.
- Art direction: Renaissance technomancy—an aged leather grimoire with gold tooling, alchemical geometry, clockwork diagrams, and restrained computational motifs.
- Render the exact cover text:
  - `FORMULAE MAGICAE`
  - `ARS AUTOMATA`
- Avoid vendor logos, modern UI elements, watermarks, illegible pseudo-text, and horror imagery.
- Inspect the generated image at full resolution, verify both Latin lines exactly, and make one focused correction pass if necessary.
- Present the repository as a real technical collection with a grimoire skin: concise compatibility and installation information first, lore and spell terminology as supporting personality.

## Verification

- Validate every public and private skill with `skills-ref`.
- Run `claude plugin validate` against the collection and verify individual marketplace entries resolve only their intended skill.
- Validate OpenAI and Hawk manifests as JSON/YAML and confirm names, descriptions, versions, and paths agree.
- Test full-collection and individual-skill discovery through Hawk using both Git and local-path sources.
- Build the Hawk wheel and verify it contains the Hawk authoring skill but none of the extracted Formulae Magicae skills.
- Exercise the first-run wizard with successful download, declined installation, and simulated network failure.
- Move each skill's existing focused tests into Formulae Magicae and update them to use repository-relative paths.
- Scan migrated content for hard-coded Claude paths, `builtins` references, missing sibling dependencies, secrets, internal URLs, and absent third-party licensing.
- Smoke-test representative scripts from TTS, transcription, visualization, Bento, PR review, Summon, and Portal without requiring external credentials.

## Assumptions and Decisions

- Formulae Magicae is the canonical source for the ten public skills; Hawk no longer maintains mirrored copies.
- Individual skills and the whole collection are both supported installation units.
- Internal skill resources always travel with their owning skill.
- The public migration uses a clean import commit; original Hawk history remains available in `hawk-hooks`.
- `Formulae Magicae Privatae` is a structurally similar private companion, not a dependency of the public collection.
- The Hawk authoring skill remains bundled with Hawk.
- Generic Hawk agents, commands, hooks, and notifications do not move unless a later review establishes that they belong to a specific public or private skill.
