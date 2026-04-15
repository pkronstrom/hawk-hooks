# Archive Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow `hawk add`, `hawk scan`, and `hawk download` to accept `.zip`, `.tar.gz`/`.tgz`, and `.skill` (zip alias) archives as input, extracting to a temp dir before processing.

**Architecture:** Add shared `extract_archive()` / `is_archive()` helpers in `downloader.py`. Each command detects archives at its entry point and routes extracted temp dirs into existing classify/scan flows. Remote archive URLs in `hawk download` are fetched with `urllib`.

**Tech Stack:** Python stdlib only — `zipfile`, `tarfile`, `urllib.request`, `tempfile`

---

### Task 1: Add archive helpers to downloader.py

**Files:**
- Modify: `src/hawk_hooks/downloader.py` (top of file, after imports)
- Test: `tests/test_downloader.py`

**Step 1: Write failing tests for `is_archive` and `extract_archive`**

In `tests/test_downloader.py`, add a new test class at the bottom:

```python
import zipfile
import tarfile


class TestArchiveHelpers:
    def test_is_archive_zip(self):
        from hawk_hooks.downloader import is_archive
        assert is_archive(Path("foo.zip")) is True

    def test_is_archive_tar_gz(self):
        from hawk_hooks.downloader import is_archive
        assert is_archive(Path("foo.tar.gz")) is True

    def test_is_archive_tgz(self):
        from hawk_hooks.downloader import is_archive
        assert is_archive(Path("foo.tgz")) is True

    def test_is_archive_skill(self):
        from hawk_hooks.downloader import is_archive
        assert is_archive(Path("foo.skill")) is True

    def test_is_archive_md(self):
        from hawk_hooks.downloader import is_archive
        assert is_archive(Path("foo.md")) is False

    def test_is_archive_string(self):
        from hawk_hooks.downloader import is_archive
        assert is_archive("foo.zip") is True
        assert is_archive("foo.md") is False

    def test_extract_zip(self, tmp_path):
        from hawk_hooks.downloader import extract_archive

        # Create a zip with a skill file inside
        archive = tmp_path / "test.zip"
        inner = tmp_path / "content"
        inner.mkdir()
        (inner / "hello.md").write_text("# Hello skill")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.write(inner / "hello.md", "hello.md")

        result = extract_archive(archive)
        assert result.is_dir()
        assert (result / "hello.md").read_text() == "# Hello skill"

    def test_extract_skill(self, tmp_path):
        from hawk_hooks.downloader import extract_archive

        # .skill is zip format
        archive = tmp_path / "test.skill"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("my-skill.md", "# My skill")

        result = extract_archive(archive)
        assert (result / "my-skill.md").read_text() == "# My skill"

    def test_extract_tar_gz(self, tmp_path):
        from hawk_hooks.downloader import extract_archive

        # Create a tar.gz with a skill file inside
        inner = tmp_path / "content"
        inner.mkdir()
        (inner / "hello.md").write_text("# Hello skill")

        archive = tmp_path / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(inner / "hello.md", "hello.md")

        result = extract_archive(archive)
        assert result.is_dir()
        assert (result / "hello.md").read_text() == "# Hello skill"

    def test_extract_tgz(self, tmp_path):
        from hawk_hooks.downloader import extract_archive

        archive = tmp_path / "test.tgz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.addstr = None  # use writestr equivalent
        # simpler: just create valid tgz
        inner = tmp_path / "content2"
        inner.mkdir()
        (inner / "a.md").write_text("A")
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(inner / "a.md", "a.md")

        result = extract_archive(archive)
        assert (result / "a.md").read_text() == "A"

    def test_extract_unsupported_raises(self, tmp_path):
        from hawk_hooks.downloader import extract_archive

        bad = tmp_path / "test.rar"
        bad.write_text("not an archive")
        with pytest.raises(ValueError, match="Unsupported archive"):
            extract_archive(bad)
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_downloader.py::TestArchiveHelpers -v`
Expected: ImportError — `is_archive` and `extract_archive` don't exist yet

**Step 3: Implement the helpers**

In `src/hawk_hooks/downloader.py`, add after the existing imports (after `import tempfile`):

```python
import tarfile
import zipfile

ARCHIVE_EXTENSIONS = (".zip", ".tar.gz", ".tgz", ".skill")


def is_archive(path: str | Path) -> bool:
    """Check if a path has a supported archive extension."""
    name = str(path).lower()
    return any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def extract_archive(path: Path) -> Path:
    """Extract an archive to a temp directory.

    Supports .zip, .skill (zip format), .tar.gz, and .tgz.
    Returns the path to the temp directory containing extracted contents.
    Caller is responsible for cleanup (shutil.rmtree).

    Raises:
        ValueError: If the archive format is not supported.
        zipfile.BadZipFile / tarfile.TarError: If the archive is corrupt.
    """
    path = Path(path)
    dest = Path(tempfile.mkdtemp(prefix="hawk-archive-"))
    name_lower = path.name.lower()

    if name_lower.endswith(".zip") or name_lower.endswith(".skill"):
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(dest)
    elif name_lower.endswith(".tar.gz") or name_lower.endswith(".tgz"):
        with tarfile.open(path, "r:gz") as tf:
            tf.extractall(dest, filter="data")
    else:
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"Unsupported archive format: {path.name}")

    return dest
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_downloader.py::TestArchiveHelpers -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/downloader.py tests/test_downloader.py
git commit -m "feat: add archive extraction helpers (zip, tar.gz, tgz, skill)"
```

---

### Task 2: Add `fetch_remote_archive` helper

**Files:**
- Modify: `src/hawk_hooks/downloader.py`
- Test: `tests/test_downloader.py`

**Step 1: Write failing test**

Add to `TestArchiveHelpers` in `tests/test_downloader.py`:

```python
    def test_fetch_remote_archive(self, tmp_path, monkeypatch):
        from hawk_hooks.downloader import fetch_remote_archive

        # Create a local zip to serve as the "remote" file
        archive = tmp_path / "remote.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("skill.md", "# Remote skill")

        # Monkeypatch urlretrieve to copy from local file
        def fake_urlretrieve(url, filename):
            import shutil
            shutil.copy2(archive, filename)
            return filename, {}

        monkeypatch.setattr("hawk_hooks.downloader.urlretrieve", fake_urlretrieve)

        result = fetch_remote_archive("https://example.com/pkg.zip")
        assert result.exists()
        assert result.name.endswith(".zip")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_downloader.py::TestArchiveHelpers::test_fetch_remote_archive -v`
Expected: ImportError — `fetch_remote_archive` doesn't exist

**Step 3: Implement**

In `src/hawk_hooks/downloader.py`, add import near top:

```python
from urllib.request import urlretrieve
```

Add function after `extract_archive`:

```python
def fetch_remote_archive(url: str) -> Path:
    """Download a remote archive URL to a temp file.

    Returns the path to the downloaded file.
    Caller is responsible for cleanup.
    """
    # Preserve the extension so extract_archive can detect the format
    suffix = ""
    url_lower = url.lower().split("?")[0]  # strip query params
    for ext in ARCHIVE_EXTENSIONS:
        if url_lower.endswith(ext):
            suffix = ext
            break

    tmp = Path(tempfile.mkdtemp(prefix="hawk-fetch-"))
    dest = tmp / f"archive{suffix}"
    urlretrieve(url, str(dest))
    return dest
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_downloader.py::TestArchiveHelpers::test_fetch_remote_archive -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/downloader.py tests/test_downloader.py
git commit -m "feat: add fetch_remote_archive for downloading archive URLs"
```

---

### Task 3: Update `hawk scan` to accept archives

**Files:**
- Modify: `src/hawk_hooks/cli.py` (`cmd_scan`, around line 633)
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

Add to `tests/test_cli.py` — find the scan test section and add:

```python
import zipfile as _zipfile


class TestScanArchive:
    def test_scan_zip_archive(self, tmp_path, monkeypatch):
        """hawk scan should accept a zip file and extract before scanning."""
        from hawk_hooks import config

        # Patch config paths
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(config, "get_profiles_dir", lambda: config_dir / "profiles")
        monkeypatch.setattr(config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(config, "get_registry_path", lambda cfg=None: registry_dir)

        # Create a zip archive with a skills dir
        archive = tmp_path / "components.zip"
        with _zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("skills/hello.md", "# Hello\nA skill.")

        from hawk_hooks.cli import cmd_scan
        import argparse

        args = argparse.Namespace(
            path=str(archive), ui=False, replace=False,
            select=None, depth=5, enable=False,
        )

        # Should not raise "not a directory" error
        cmd_scan(args)

        # Verify the skill was added to registry
        from hawk_hooks.registry import Registry
        reg = Registry(registry_dir)
        assert reg.detect_clash(ComponentType.SKILL, "hello.md")

    def test_scan_skill_archive(self, tmp_path, monkeypatch):
        """hawk scan should accept a .skill file."""
        from hawk_hooks import config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(config, "get_profiles_dir", lambda: config_dir / "profiles")
        monkeypatch.setattr(config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(config, "get_registry_path", lambda cfg=None: registry_dir)

        archive = tmp_path / "pkg.skill"
        with _zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("my-skill.md", "# My Skill")

        from hawk_hooks.cli import cmd_scan
        import argparse

        args = argparse.Namespace(
            path=str(archive), ui=False, replace=False,
            select=None, depth=5, enable=False,
        )
        cmd_scan(args)

        from hawk_hooks.registry import Registry
        reg = Registry(registry_dir)
        assert reg.detect_clash(ComponentType.SKILL, "my-skill.md")
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py::TestScanArchive -v`
Expected: FAIL — `sys.exit(1)` with "not a directory"

**Step 3: Implement**

In `src/hawk_hooks/cli.py`, modify `cmd_scan` (around line 633). Replace:

```python
    scan_path = Path(args.path).resolve()
    if not scan_path.is_dir():
        print(f"Error: {scan_path} is not a directory.")
        sys.exit(1)
```

With:

```python
    scan_path = Path(args.path).resolve()
    archive_tmp = None
    if scan_path.is_file():
        from .downloader import is_archive, extract_archive
        if is_archive(scan_path):
            archive_tmp = extract_archive(scan_path)
            scan_path = archive_tmp
        else:
            print(f"Error: {scan_path} is not a directory or supported archive.")
            sys.exit(1)
    elif not scan_path.is_dir():
        print(f"Error: {scan_path} does not exist.")
        sys.exit(1)
```

And add cleanup at the end of `cmd_scan` (before the final return / after all processing). Add a try/finally wrapping the rest of the function body after the archive detection:

```python
    try:
        # ... existing scan logic stays here unchanged ...
    finally:
        if archive_tmp:
            import shutil
            shutil.rmtree(archive_tmp, ignore_errors=True)
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py::TestScanArchive -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/cli.py tests/test_cli.py
git commit -m "feat: hawk scan accepts archive files (zip, tar.gz, skill)"
```

---

### Task 4: Update `hawk download` to accept archives

**Files:**
- Modify: `src/hawk_hooks/download_service.py` (`download_and_install`)
- Test: `tests/test_download_service.py`

**Step 1: Write failing tests**

Add to `tests/test_download_service.py`:

```python
import zipfile as _zipfile


def test_download_local_archive(monkeypatch, tmp_path):
    """hawk download with a local .zip should extract and classify."""
    from hawk_hooks.download_service import download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    # Create a zip archive with skills
    archive = tmp_path / "package.zip"
    with _zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("skills/hello.md", "# Hello skill")

    result = download_and_install(str(archive), select_all=True)

    assert result.success is True
    assert any("hello.md" in item for item in result.added)


def test_download_skill_archive(monkeypatch, tmp_path):
    """hawk download with a .skill file should work."""
    from hawk_hooks.download_service import download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    archive = tmp_path / "my-package.skill"
    with _zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("hello.md", "# Hello")

    result = download_and_install(str(archive), select_all=True)

    assert result.success is True
    assert len(result.added) > 0


def test_download_remote_archive(monkeypatch, tmp_path):
    """hawk download with a URL ending in .zip should fetch and extract."""
    from hawk_hooks.download_service import download_and_install

    _patch_config_paths(monkeypatch, tmp_path)

    # Create a zip that our fake fetch will return
    archive = tmp_path / "remote.zip"
    with _zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("skills/remote-skill.md", "# Remote skill")

    def fake_fetch(url):
        return archive

    monkeypatch.setattr("hawk_hooks.download_service.fetch_remote_archive", fake_fetch)

    result = download_and_install("https://example.com/pkg.zip", select_all=True)

    assert result.success is True
    assert any("remote-skill.md" in item for item in result.added)
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_download_service.py::test_download_local_archive tests/test_download_service.py::test_download_skill_archive tests/test_download_service.py::test_download_remote_archive -v`
Expected: FAIL — current code tries `shallow_clone` on the archive path

**Step 3: Implement**

In `src/hawk_hooks/download_service.py`, update imports at top:

```python
from .downloader import (
    ClassifiedContent, add_items_to_registry, check_clashes,
    classify, extract_archive, fetch_remote_archive, get_head_commit,
    is_archive, scan_directory, shallow_clone,
)
```

In `download_and_install()`, replace the clone section (lines ~362-368):

```python
    logf(f"Cloning {url}...")
    try:
        clone_dir = shallow_clone(url)
    except Exception as exc:
        err = f"Error cloning: {exc}"
        logf(err)
        return DownloadResult(success=False, error=err)
```

With:

```python
    # Detect archive input: local file or remote archive URL
    from pathlib import Path as _Path
    local_path = _Path(url)
    archive_tmp = None
    is_local_archive = local_path.is_file() and is_archive(local_path)
    is_remote_archive = not is_local_archive and "://" in url and is_archive(url)

    if is_local_archive:
        logf(f"Extracting {local_path.name}...")
        try:
            clone_dir = extract_archive(local_path)
            archive_tmp = clone_dir
        except Exception as exc:
            err = f"Error extracting archive: {exc}"
            logf(err)
            return DownloadResult(success=False, error=err)
    elif is_remote_archive:
        logf(f"Downloading {url}...")
        try:
            fetched = fetch_remote_archive(url)
            logf("Extracting...")
            clone_dir = extract_archive(fetched)
            archive_tmp = clone_dir
        except Exception as exc:
            err = f"Error downloading archive: {exc}"
            logf(err)
            return DownloadResult(success=False, error=err)
    else:
        logf(f"Cloning {url}...")
        try:
            clone_dir = shallow_clone(url)
        except Exception as exc:
            err = f"Error cloning: {exc}"
            logf(err)
            return DownloadResult(success=False, error=err)
```

Also update the existing `try/finally` cleanup block to handle `archive_tmp`.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_download_service.py -v`
Expected: All PASS (new and existing)

**Step 5: Commit**

```bash
git add src/hawk_hooks/download_service.py tests/test_download_service.py
git commit -m "feat: hawk download accepts local/remote archives"
```

---

### Task 5: Update `hawk add` to accept archives

**Files:**
- Modify: `src/hawk_hooks/cli.py` (`cmd_add`, around line 365)
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

Add to `tests/test_cli.py`:

```python
class TestAddArchive:
    def test_add_zip_with_skills(self, tmp_path, monkeypatch):
        """hawk add <archive.zip> should extract and add all components."""
        from hawk_hooks import config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(config, "get_profiles_dir", lambda: config_dir / "profiles")
        monkeypatch.setattr(config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(config, "get_registry_path", lambda cfg=None: registry_dir)

        archive = tmp_path / "bundle.zip"
        with _zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("skills/s1.md", "# Skill 1")
            zf.writestr("skills/s2.md", "# Skill 2")

        from hawk_hooks.cli import cmd_add
        import argparse

        args = argparse.Namespace(
            type=str(archive), path=None, name=None,
            force=False, enable=False, package=None,
            type_flag=None,
        )
        cmd_add(args)

        from hawk_hooks.registry import Registry
        reg = Registry(registry_dir)
        assert reg.detect_clash(ComponentType.SKILL, "s1.md")
        assert reg.detect_clash(ComponentType.SKILL, "s2.md")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py::TestAddArchive -v`
Expected: FAIL — current code tries to add the .zip as a single file

**Step 3: Implement**

In `src/hawk_hooks/cli.py`, in `cmd_add`, after the path/stdin resolution block (after line ~368 where `source` is set), add archive detection:

```python
    if args.path:
        source = Path(args.path).resolve()
        if not source.exists():
            print(f"Error: {source} does not exist.")
            sys.exit(1)

        # Archive? Extract and use classify+batch-add flow instead
        from .downloader import is_archive
        if source.is_file() and is_archive(source):
            _add_from_archive(source, args)
            return
```

Then add a helper function before `cmd_add`:

```python
def _add_from_archive(archive_path: Path, args):
    """Extract an archive and add all classified components to registry."""
    from .downloader import (
        add_items_to_registry, check_clashes, classify,
        extract_archive, is_archive,
    )
    from .registry import Registry
    from . import config
    import shutil

    registry = Registry(config.get_registry_path())
    registry.ensure_dirs()

    try:
        extract_dir = extract_archive(archive_path)
    except Exception as exc:
        print(f"Error extracting archive: {exc}")
        sys.exit(1)

    try:
        content = classify(extract_dir)
        if not content.items:
            print("No components found in archive.")
            return

        _print(f"Found {len(content.items)} component(s) in archive:")
        for item in content.items:
            _print(f"  [{item.component_type.value}] {item.name}")

        replace = getattr(args, "force", False)
        clashes = check_clashes(content.items, registry)
        if clashes and not replace:
            clash_names = {f"{c.component_type.value}/{c.name}" for c in clashes}
            _print(f"\n[yellow]Skipping {len(clashes)} clash(es):[/yellow] {', '.join(sorted(clash_names))}")
            _print("[dim]Use --force to replace.[/dim]")
            items_to_add = [i for i in content.items if i not in clashes]
        else:
            items_to_add = content.items

        if not items_to_add:
            print("No new components to add.")
            return

        added, skipped = add_items_to_registry(items_to_add, registry, replace=replace)
        for ct_name in added:
            _print(f"[green]+[/green] Added {ct_name}")

        if getattr(args, "enable", False) and added:
            newly = config.enable_items_in_config(added)
            if newly:
                _print(f"Enabled {len(newly)} component(s) in global config.")
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py::TestAddArchive -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/hawk_hooks/cli.py tests/test_cli.py
git commit -m "feat: hawk add accepts archive files with batch classify"
```

---

### Task 6: Update CLI help text and argument descriptions

**Files:**
- Modify: `src/hawk_hooks/cli.py` (argparse definitions, around lines 1593-1613)

**Step 1: Update help strings**

Change scan parser help:

```python
scan_p = subparsers.add_parser("scan", help="Scan directory or archive for components to import")
scan_p.add_argument("path", nargs="?", default=".", help="Directory or archive file to scan (default: cwd)")
```

Change download parser help:

```python
dl_p = subparsers.add_parser("download", help="Download components from git URL or archive")
dl_p.add_argument("url", help="Git URL, archive URL, or local archive path")
```

**Step 2: Run existing tests to verify nothing breaks**

Run: `python3 -m pytest tests/test_cli.py::TestArgParsing -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/hawk_hooks/cli.py
git commit -m "docs: update CLI help text to mention archive support"
```

---

### Task 7: Run full test suite

**Step 1: Run all tests**

Run: `python3 -m pytest tests/ -q`
Expected: All pass, no regressions

**Step 2: Manual smoke test**

```bash
# Create a test zip
mkdir -p /tmp/hawk-test/skills
echo "# Test Skill" > /tmp/hawk-test/skills/test-archive.md
cd /tmp && zip -r test-archive.zip hawk-test/

# Test each command
hawk scan /tmp/test-archive.zip
hawk add /tmp/test-archive.zip
hawk download /tmp/test-archive.zip
```

**Step 3: Clean up test components**

```bash
hawk remove skill test-archive.md
```
