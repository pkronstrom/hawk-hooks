# Package Grouping & Operations

## Problem

Components downloaded via `hawk download` are scattered into flat registry dirs (`skills/`, `commands/`, `agents/`). There's no record of which package they came from, making it hard to:
- See what you installed as a unit
- Update a package when upstream changes
- Remove all items from a package at once
- Understand the toggle list when you have 20+ items

## Data Model

### `~/.config/hawk-hooks/packages.yaml`

Central package index, written at download time:

```yaml
packages:
  superpowers-marketplace:
    url: https://github.com/user/superpowers-marketplace
    installed: "2026-02-18"
    commit: a1b2c3d4
    items:
      - type: command
        name: commit
        hash: f8e9d2a1
      - type: agent
        name: code-reviewer
        hash: b3c4e5f6
```

**Fields:**
- `url`: Git clone URL
- `installed`: ISO date of last install/update
- `commit`: Git HEAD commit hash at download time
- `items[].hash`: SHA-256 of file contents (or sorted dir contents hash)

**Rules:**
- Written by `hawk download` after adding items to registry
- Package name defaults to repo name (last URL segment minus `.git`), overridable with `--name`
- Re-downloading same URL updates the existing package entry
- Items added via `hawk add` are not in any package (shown as "ungrouped")

### New functions in `v2_config.py`

```python
def get_packages_path() -> Path:
    return get_config_dir() / "packages.yaml"

def load_packages() -> dict[str, Any]:
def save_packages(data: dict[str, Any]) -> None:

def get_package_for_item(component_type: str, name: str) -> str | None:
    """Reverse lookup: which package owns this item?"""

def list_package_items(package_name: str) -> list[tuple[ComponentType, str]]:
    """All items belonging to a package."""

def remove_package(package_name: str) -> None:
    """Remove package entry from index."""
```

### Content hashing

```python
def _hash_file(path: Path) -> str:
    """SHA-256 of file contents, truncated to 8 chars."""

def _hash_dir(path: Path) -> str:
    """SHA-256 of sorted (relative_path, file_hash) pairs."""
```

Computed at download time, stored per-item for update diffing.

## Toggle List: Grouped Display

### Visual

```
Skills — 📍 This project: frontend    [Tab: 🌐 All projects]
──────────────────────────────────────────────────────
  📦 superpowers-marketplace  (3/5 enabled)  ▼
    ✔ tdd
    ✔ dry-coder
    ☐ react-patterns              (enabled in 🌐 All projects)
    ☐ typescript-strict
    ✔ frontend-a11y
  📦 my-custom-skills  (1/1 enabled)  ▼
    ✔ company-standards
  ── ungrouped ──
    ✔ local-experiment
  ─────────
  Select All
  Select None
  Done

Space/Enter: toggle  ↑↓/jk: navigate  Tab: scope  q: done
```

### Collapsed state

```
  📦 superpowers-marketplace  (3/5 enabled)  ▶
  📦 my-custom-skills  (1/1 enabled)  ▼
    ✔ company-standards
```

### Behavior

- **Arrow keys**: navigate everything including package headers
- **Space/Enter on header**: collapse/expand that package group
- **Space/Enter on item**: toggle that item in current scope
- Package headers show `(N/M enabled)` count for current scope
- Collapsed packages hide their items, show `▶`
- Expanded packages show items, show `▼`
- Items not in any package appear under "ungrouped" section at bottom
- All existing scope behavior (Tab cycling, parent hints) works within groups

### Implementation

New `groups` parameter for `run_toggle_list`:

```python
@dataclass
class ToggleGroup:
    key: str          # package name or "__ungrouped__"
    label: str        # "📦 superpowers-marketplace" or "ungrouped"
    items: list[str]  # item names in this group
    collapsed: bool = False

def run_toggle_list(
    ...,
    groups: list[ToggleGroup] | None = None,  # NEW
) -> tuple[list[list[str]], bool]:
```

When `groups` is provided:
- Items are rendered under their group headers
- `_total_rows()` accounts for headers and collapsed groups
- Navigation logic skips collapsed items
- Backward compat: when `groups` is None, flat list as before

### Building groups from packages

In `dashboard.py`, `_handle_component_toggle`:

```python
packages = v2_config.load_packages()
groups = []
ungrouped = set(registry_names)

for pkg_name, pkg_data in packages.items():
    pkg_items = [
        item["name"] for item in pkg_data.get("items", [])
        if item["type"] == field.rstrip("s")  # "skills" -> "skill"
        and item["name"] in registry_names_or_enabled
    ]
    if pkg_items:
        groups.append(ToggleGroup(key=pkg_name, label=f"📦 {pkg_name}", items=sorted(pkg_items)))
        ungrouped -= set(pkg_items)

if ungrouped:
    groups.append(ToggleGroup(key="__ungrouped__", label="ungrouped", items=sorted(ungrouped)))
```

## Package Operations

### `hawk update [package]`

```
hawk update                    # Update all packages
hawk update superpowers        # Update specific package
hawk update --check            # Check without applying
```

**Flow:**
1. Load `packages.yaml`
2. For each package (or specified one):
   a. Shallow clone URL to temp dir
   b. Get HEAD commit hash
   c. If same as stored `commit` and not `--force`: skip ("up to date")
   d. Re-classify contents
   e. Compute per-item hashes
   f. Compare to stored hashes:
      - **Changed**: replace in registry
      - **New**: add to registry
      - **Removed upstream**: warn but keep local (unless `--prune`)
   g. Update `packages.yaml` entry
3. Show summary per package
4. Run `sync_all()`

**Output:**
```
superpowers-marketplace:
  + new-skill (added)
  ~ commit (updated)
  = code-reviewer (unchanged)
  2 updated, 1 new

All packages up to date: my-custom-skills
```

### `hawk remove-package <name>`

**Flow:**
1. Look up package in `packages.yaml`
2. For each item: `registry.remove(type, name)`
3. For each item: remove from `global.{field}` enabled lists in config
4. For each registered directory: remove from `dir_config.{field}.enabled` lists
5. Remove package entry from `packages.yaml`
6. Run `sync_all()`

### `hawk packages`

List installed packages:
```
Packages:
  superpowers-marketplace  20 items  installed 2026-02-18
    https://github.com/user/superpowers-marketplace @ a1b2c3d
  my-custom-skills         3 items   installed 2026-02-15
    https://github.com/me/skills @ e5f6g7h
```

### `hawk download` changes

After adding items to registry, append to `packages.yaml`:
1. Compute package name from URL (or `--name`)
2. Get HEAD commit hash from the clone
3. Compute content hash per item
4. Write/update entry in `packages.yaml`

## Dashboard Integration

### Menu changes

Replace or augment "Download" menu item:
```
Download       Fetch from git URL
Packages       3 installed, manage & update    # NEW
```

### Packages submenu

Selecting "Packages" shows:
```
hawk packages
────────────────────────────
❯ 📦 superpowers-marketplace    20 items
  📦 my-custom-skills           3 items
  ─────────
  Update all
  Download new...

[Enter: details]  [u: update]  [x: remove]  [q: back]
```

Selecting a package shows its items with type tags.

## Implementation Order

1. **Data model**: `packages.yaml` load/save/lookup functions in `v2_config.py`
2. **Content hashing**: `_hash_file`, `_hash_dir` utilities
3. **Download integration**: Update `downloader.py` and `cmd_download` to write package entries
4. **Toggle grouping**: `ToggleGroup` dataclass, grouped rendering in `toggle.py`
5. **Dashboard grouping**: Build groups from packages in `_handle_component_toggle`
6. **`hawk packages`**: CLI command + dashboard menu item
7. **`hawk update`**: Clone, diff, replace flow
8. **`hawk remove-package`**: Registry + config cleanup
9. **Tests**: Package index CRUD, update diffing, grouped toggle rendering
10. **Migration**: Scan existing registry items and try to match to download history (best-effort)

## Migration for Existing Items

Existing items that predate `packages.yaml` will appear as "ungrouped". No automatic migration — users can:
- Re-download with `hawk download <url>` which will recognize existing items and create the package entry
- Or leave them ungrouped (still fully functional)
