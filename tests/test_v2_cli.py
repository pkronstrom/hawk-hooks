"""Tests for v2 CLI."""

import pytest

from hawk_hooks.cli import _name_from_content, build_parser


class TestArgParsing:
    def setup_method(self):
        self.parser = build_parser()

    def test_init_default(self):
        args = self.parser.parse_args(["init"])
        assert args.command == "init"
        assert args.profile is None
        assert args.dir is None

    def test_init_with_profile(self):
        args = self.parser.parse_args(["init", "--profile", "web"])
        assert args.profile == "web"

    def test_init_with_dir(self):
        args = self.parser.parse_args(["init", "--dir", "/tmp/project"])
        assert args.dir == "/tmp/project"

    def test_sync_default(self):
        args = self.parser.parse_args(["sync"])
        assert args.command == "sync"
        assert args.dry_run is False
        assert args.verbose is False

    def test_sync_dry_run(self):
        args = self.parser.parse_args(["sync", "--dry-run"])
        assert args.dry_run is True

    def test_sync_with_tool(self):
        args = self.parser.parse_args(["sync", "--tool", "claude"])
        assert args.tool == "claude"

    def test_sync_verbose(self):
        args = self.parser.parse_args(["sync", "-v"])
        assert args.verbose is True

    def test_sync_global(self):
        args = self.parser.parse_args(["sync", "--global"])
        assert args.globals_only is True

    def test_status(self):
        args = self.parser.parse_args(["status"])
        assert args.command == "status"

    def test_add(self):
        args = self.parser.parse_args(["add", "skill", "/path/to/skill"])
        assert args.type == "skill"
        assert args.path == "/path/to/skill"

    def test_add_with_name(self):
        args = self.parser.parse_args(["add", "hook", "/path", "--name", "my-hook"])
        assert args.name == "my-hook"

    def test_add_path_only(self):
        args = self.parser.parse_args(["add", "/path/to/file.md"])
        # When only path is given, type is the path and path is None
        # (argparse can't distinguish — cmd_add handles this)
        assert args.type == "/path/to/file.md"

    def test_add_enable_flag(self):
        args = self.parser.parse_args(["add", "skill", "/path", "--enable"])
        assert args.enable is True

    def test_add_enable_default(self):
        args = self.parser.parse_args(["add", "skill", "/path"])
        assert args.enable is False

    def test_remove(self):
        args = self.parser.parse_args(["remove", "skill", "tdd"])
        assert args.type == "skill"
        assert args.name == "tdd"

    def test_list_all(self):
        args = self.parser.parse_args(["list"])
        assert args.command == "list"
        assert args.type is None

    def test_list_filtered(self):
        args = self.parser.parse_args(["list", "skill"])
        assert args.type == "skill"

    def test_profile_list(self):
        args = self.parser.parse_args(["profile", "list"])
        assert args.command == "profile"
        assert args.profile_cmd == "list"

    def test_profile_show(self):
        args = self.parser.parse_args(["profile", "show", "web"])
        assert args.profile_cmd == "show"

    def test_migrate(self):
        args = self.parser.parse_args(["migrate"])
        assert args.command == "migrate"
        assert args.no_backup is False

    def test_migrate_no_backup(self):
        args = self.parser.parse_args(["migrate", "--no-backup"])
        assert args.no_backup is True

    def test_migrate_prompts_check(self):
        args = self.parser.parse_args(["migrate-prompts", "--check"])
        assert args.command == "migrate-prompts"
        assert args.check is True
        assert args.apply is False
        assert args.no_backup is False

    def test_migrate_prompts_apply_no_backup(self):
        args = self.parser.parse_args(["migrate-prompts", "--apply", "--no-backup"])
        assert args.command == "migrate-prompts"
        assert args.check is False
        assert args.apply is True
        assert args.no_backup is True

    def test_download(self):
        args = self.parser.parse_args(["download", "https://github.com/user/repo"])
        assert args.command == "download"
        assert args.url == "https://github.com/user/repo"
        assert args.replace is False
        assert args.all is False

    def test_download_all(self):
        args = self.parser.parse_args(["download", "https://github.com/user/repo", "--all"])
        assert args.all is True

    def test_download_replace(self):
        args = self.parser.parse_args(["download", "https://github.com/user/repo", "--replace"])
        assert args.replace is True

    def test_download_name(self):
        args = self.parser.parse_args(["download", "https://github.com/user/repo", "--name", "my-pkg"])
        assert args.name == "my-pkg"

    def test_download_name_default(self):
        args = self.parser.parse_args(["download", "https://github.com/user/repo"])
        assert args.name is None

    def test_sync_force(self):
        args = self.parser.parse_args(["sync", "--force"])
        assert args.force is True

    def test_clean_default(self):
        args = self.parser.parse_args(["clean"])
        assert args.command == "clean"
        assert args.dry_run is False
        assert args.dir is None
        assert args.tool is None

    def test_clean_dry_run(self):
        args = self.parser.parse_args(["clean", "--dry-run"])
        assert args.dry_run is True

    def test_clean_with_tool(self):
        args = self.parser.parse_args(["clean", "--tool", "claude"])
        assert args.tool == "claude"

    def test_clean_global(self):
        args = self.parser.parse_args(["clean", "--global"])
        assert args.globals_only is True

    def test_prune_default(self):
        args = self.parser.parse_args(["prune"])
        assert args.command == "prune"
        assert args.dry_run is False
        assert args.dir is None
        assert args.tool is None

    def test_prune_dry_run(self):
        args = self.parser.parse_args(["prune", "--dry-run"])
        assert args.dry_run is True

    def test_prune_with_tool(self):
        args = self.parser.parse_args(["prune", "--tool", "claude"])
        assert args.tool == "claude"

    def test_prune_global(self):
        args = self.parser.parse_args(["prune", "--global"])
        assert args.globals_only is True

    def test_config(self):
        args = self.parser.parse_args(["config"])
        assert args.command == "config"
        assert hasattr(args, "func")

    def test_projects(self):
        args = self.parser.parse_args(["projects"])
        assert args.command == "projects"
        assert hasattr(args, "func")

    def test_packages(self):
        args = self.parser.parse_args(["packages"])
        assert args.command == "packages"
        assert hasattr(args, "func")

    def test_update_all(self):
        args = self.parser.parse_args(["update"])
        assert args.command == "update"
        assert args.package is None
        assert args.check is False
        assert args.force is False
        assert args.prune is False

    def test_update_specific(self):
        args = self.parser.parse_args(["update", "my-pkg"])
        assert args.package == "my-pkg"

    def test_update_check(self):
        args = self.parser.parse_args(["update", "--check"])
        assert args.check is True

    def test_update_force(self):
        args = self.parser.parse_args(["update", "--force"])
        assert args.force is True

    def test_update_prune(self):
        args = self.parser.parse_args(["update", "--prune"])
        assert args.prune is True

    def test_remove_package(self):
        args = self.parser.parse_args(["remove-package", "my-pkg"])
        assert args.command == "remove-package"
        assert args.name == "my-pkg"
        assert args.yes is False

    def test_remove_package_yes(self):
        args = self.parser.parse_args(["remove-package", "my-pkg", "-y"])
        assert args.yes is True

    def test_main_dir_flag(self):
        args = self.parser.parse_args(["--dir", "/tmp/project"])
        assert args.main_dir == "/tmp/project"
        assert args.command is None

    def test_scan_default(self):
        args = self.parser.parse_args(["scan"])
        assert args.command == "scan"
        assert args.path == "."
        assert args.all is False
        assert args.replace is False
        assert args.depth == 5
        assert args.enable is False

    def test_scan_with_path(self):
        args = self.parser.parse_args(["scan", "/tmp/project"])
        assert args.path == "/tmp/project"

    def test_scan_all_replace(self):
        args = self.parser.parse_args(["scan", ".", "--all", "--replace"])
        assert args.all is True
        assert args.replace is True

    def test_scan_depth(self):
        args = self.parser.parse_args(["scan", "--depth", "3"])
        assert args.depth == 3

    def test_scan_enable(self):
        args = self.parser.parse_args(["scan", "--enable"])
        assert args.enable is True

    def test_add_type_flag(self):
        args = self.parser.parse_args(["add", "--type", "skill", "--name", "foo.md"])
        assert args.type_flag == "skill"
        assert args.name == "foo.md"

    def test_main_dir_flag_default(self):
        args = self.parser.parse_args([])
        assert args.main_dir is None

    def test_new_hook(self):
        args = self.parser.parse_args(["new", "hook", "my-guard"])
        assert args.command == "new"
        assert args.type == "hook"
        assert args.name == "my-guard"
        assert args.event == "pre_tool_use"
        assert args.lang == ".py"

    def test_new_hook_with_options(self):
        args = self.parser.parse_args(["new", "hook", "notify", "--event", "stop", "--lang", ".sh"])
        assert args.event == "stop"
        assert args.lang == ".sh"

    def test_new_command(self):
        args = self.parser.parse_args(["new", "command", "deploy"])
        assert args.type == "command"
        assert args.name == "deploy"

    def test_new_agent(self):
        args = self.parser.parse_args(["new", "agent", "reviewer"])
        assert args.type == "agent"

    def test_new_prompt_hook(self):
        args = self.parser.parse_args(["new", "prompt-hook", "safety-check"])
        assert args.type == "prompt-hook"

    def test_new_force(self):
        args = self.parser.parse_args(["new", "hook", "guard", "--force"])
        assert args.force is True

    def test_deps(self):
        args = self.parser.parse_args(["deps"])
        assert args.command == "deps"
        assert hasattr(args, "func")


class TestNameFromContent:
    def test_simple_text(self):
        assert _name_from_content("Hello world today") == "hello-world-today.md"

    def test_markdown_heading(self):
        assert _name_from_content("# My Cool Skill\nDoes stuff.") == "my-cool-skill.md"

    def test_frontmatter(self):
        result = _name_from_content("---\nname: deploy\n---\nDeploy the app now.")
        assert result == "deploy-the-app.md"

    def test_empty_content(self):
        assert _name_from_content("") == "unnamed.md"

    def test_short_content(self):
        assert _name_from_content("Hi") == "hi.md"

    def test_special_chars_stripped(self):
        assert _name_from_content("## Fix: the bug!") == "fix-the-bug.md"

    def test_custom_suffix(self):
        assert _name_from_content("test hook", suffix=".py") == "test-hook.py"


class TestCmdNew:
    """Test hawk new command."""

    def test_new_hook_creates_file(self, tmp_path, monkeypatch):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_new

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="hook", name="my-guard", event="pre_tool_use",
            lang=".py", force=False,
        )
        cmd_new(args)

        hook_file = registry_dir / "hooks" / "my-guard.py"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert "hawk-hook: events=pre_tool_use" in content
        assert content.startswith("#!/usr/bin/env python3")

    def test_new_hook_sh(self, tmp_path, monkeypatch):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_new

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="hook", name="guard", event="stop", lang=".sh", force=False,
        )
        cmd_new(args)

        hook_file = registry_dir / "hooks" / "guard.sh"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert "hawk-hook: events=stop" in content

    def test_new_command_creates_file(self, tmp_path, monkeypatch):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_new

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="command", name="deploy", event="pre_tool_use",
            lang=".py", force=False,
        )
        cmd_new(args)

        cmd_file = registry_dir / "prompts" / "deploy.md"
        assert cmd_file.exists()
        content = cmd_file.read_text()
        assert "deploy" in content

    def test_new_agent_creates_file(self, tmp_path, monkeypatch):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_new

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="agent", name="reviewer", event="pre_tool_use",
            lang=".py", force=False,
        )
        cmd_new(args)

        agent_file = registry_dir / "agents" / "reviewer.md"
        assert agent_file.exists()
        content = agent_file.read_text()
        assert "reviewer" in content

    def test_new_prompt_hook_creates_file(self, tmp_path, monkeypatch):
        import argparse
        import json
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_new

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="prompt-hook", name="safety-check", event="pre_tool_use",
            lang=".py", force=False,
        )
        cmd_new(args)

        hook_file = registry_dir / "hooks" / "safety-check.prompt.json"
        assert hook_file.exists()
        data = json.loads(hook_file.read_text())
        assert "prompt" in data
        assert data["hawk-hook"]["events"] == ["pre_tool_use"]

    def test_new_hook_no_overwrite_without_force(self, tmp_path, monkeypatch):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_new

        registry_dir = tmp_path / "registry"
        (registry_dir / "hooks").mkdir(parents=True)
        (registry_dir / "hooks" / "guard.py").write_text("existing")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="hook", name="guard", event="pre_tool_use",
            lang=".py", force=False,
        )
        with pytest.raises(SystemExit):
            cmd_new(args)

        # File should be unchanged
        assert (registry_dir / "hooks" / "guard.py").read_text() == "existing"


class TestCmdMigratePrompts:
    def test_check_mode_outputs_summary(self, monkeypatch, capsys):
        import argparse
        from hawk_hooks.cli import cmd_migrate_prompts

        monkeypatch.setattr(
            "hawk_hooks.migrate_prompts.run_migrate_prompts",
            lambda **kwargs: (True, "global.commands needs migration"),
        )

        args = argparse.Namespace(check=True, apply=False, no_backup=False)
        cmd_migrate_prompts(args)

        out = capsys.readouterr().out
        assert "Migration check:" in out
        assert "global.commands needs migration" in out

    def test_apply_mode_outputs_done(self, monkeypatch, capsys):
        import argparse
        from hawk_hooks.cli import cmd_migrate_prompts

        monkeypatch.setattr(
            "hawk_hooks.migrate_prompts.run_migrate_prompts",
            lambda **kwargs: (True, "migrated global.commands -> global.prompts"),
        )

        args = argparse.Namespace(check=False, apply=True, no_backup=True)
        cmd_migrate_prompts(args)

        out = capsys.readouterr().out
        assert "Migration complete:" in out
        assert "migrated global.commands -> global.prompts" in out


class TestCmdDeps:
    """Test hawk deps command."""

    def test_deps_no_hooks(self, tmp_path, monkeypatch, capsys):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_deps

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace()
        cmd_deps(args)

        captured = capsys.readouterr()
        assert "No hooks directory" in captured.out

    def test_deps_no_deps_found(self, tmp_path, monkeypatch, capsys):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_deps

        registry_dir = tmp_path / "registry"
        hooks_dir = registry_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "guard.py").write_text("#!/usr/bin/env python3\n# hawk-hook: events=pre_tool_use\nimport sys\n")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace()
        cmd_deps(args)

        captured = capsys.readouterr()
        assert "No dependencies found" in captured.out


class TestCmdScanPackageRecording:
    """Test that cmd_scan records packages when hawk-package.yaml is found."""

    def test_scan_all_with_manifest_records_package(self, tmp_path, monkeypatch):
        """hawk scan --all with a manifest records the package in packages.yaml."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        # Set up a scannable directory with manifest
        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text(
            "name: test-pkg\ndescription: Test\nversion: '1.0'\n"
        )
        (scan_dir / "commands").mkdir()
        (scan_dir / "commands" / "hello.md").write_text("# Hello")

        # Point config to temp dirs
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        # Build args
        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        # Verify package was recorded
        packages = v2_config.load_packages()
        assert "test-pkg" in packages
        pkg = packages["test-pkg"]
        assert pkg["path"] == str(scan_dir)
        assert len(pkg["items"]) == 1
        assert pkg["items"][0]["type"] == "prompt"
        assert pkg["items"][0]["name"] == "hello.md"

    def test_scan_all_without_manifest_no_package(self, tmp_path, monkeypatch):
        """hawk scan --all without a manifest does not record a package."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "loose-files"
        scan_dir.mkdir()
        (scan_dir / "commands").mkdir()
        (scan_dir / "commands" / "hello.md").write_text("# Hello")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        packages = v2_config.load_packages()
        assert len(packages) == 0

    def test_scan_records_existing_clashing_items_in_package(self, tmp_path, monkeypatch):
        """Package record includes selected clashes already present in registry."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text(
            "name: test-pkg\ndescription: Test\nversion: '1.0'\n"
        )
        (scan_dir / "mcp").mkdir()
        (scan_dir / "mcp" / "figma.json").write_text("{}\n")
        (scan_dir / "mcp" / "linear.json").write_text("{}\n")
        (scan_dir / "mcp" / "goose.json").write_text("{}\n")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        (registry_dir / "mcp").mkdir(parents=True)
        # Seed existing entries so scan sees clashes for figma/linear.
        (registry_dir / "mcp" / "figma.json").write_text("{}\n")
        (registry_dir / "mcp" / "linear.json").write_text("{}\n")

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        packages = v2_config.load_packages()
        assert "test-pkg" in packages
        item_names = {
            item["name"] for item in packages["test-pkg"]["items"]
            if item["type"] == "mcp"
        }
        assert item_names == {"figma.json", "linear.json", "goose.json"}

    def test_scan_all_clashes_still_records_package(self, tmp_path, monkeypatch):
        """Scan can re-associate an existing package even with zero additions."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text("name: test-pkg\n")
        (scan_dir / "mcp").mkdir()
        (scan_dir / "mcp" / "figma.json").write_text("{}\n")
        (scan_dir / "mcp" / "linear.json").write_text("{}\n")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        (registry_dir / "mcp").mkdir(parents=True)
        (registry_dir / "mcp" / "figma.json").write_text("{}\n")
        (registry_dir / "mcp" / "linear.json").write_text("{}\n")

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        packages = v2_config.load_packages()
        assert "test-pkg" in packages
        item_names = {
            item["name"] for item in packages["test-pkg"]["items"]
            if item["type"] == "mcp"
        }
        assert item_names == {"figma.json", "linear.json"}

    def test_scan_partial_selection_preserves_existing_package_items(self, tmp_path, monkeypatch):
        """Partial re-scan should merge package ownership instead of replacing existing items."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text("name: test-pkg\n")
        (scan_dir / "commands").mkdir()
        (scan_dir / "commands" / "old.md").write_text("# Old")
        (scan_dir / "commands" / "new.md").write_text("# New")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        (registry_dir / "prompts").mkdir(parents=True)
        (registry_dir / "prompts" / "old.md").write_text("# Old")

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        v2_config.save_packages({
            "test-pkg": {
                "url": "",
                "path": str(scan_dir),
                "installed": "2026-02-23",
                "commit": "",
                "items": [{"type": "prompt", "name": "old.md", "hash": "deadbeef"}],
            }
        })

        # Simulate interactive partial selection: select only "new.md".
        monkeypatch.setattr(
            "hawk_hooks.cli._interactive_select_items",
            lambda items, *_args, **_kwargs: (
                [next(i for i in items if i.name == "new.md")],
                "enter",
            ),
        )

        args = argparse.Namespace(
            path=str(scan_dir),
            all=False,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        packages = v2_config.load_packages()
        assert "test-pkg" in packages
        item_names = {
            item["name"] for item in packages["test-pkg"]["items"]
            if item["type"] == "prompt"
        }
        assert item_names == {"old.md", "new.md"}

    def test_scan_checks_conflicts_for_clashing_selected_package(self, tmp_path, monkeypatch):
        """Source-type conflict check covers selected package clashes too."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "scan-root"
        scan_dir.mkdir()
        pkg_a = scan_dir / "pkg-a"
        pkg_b = scan_dir / "pkg-b"
        pkg_a.mkdir()
        pkg_b.mkdir()

        (pkg_a / "hawk-package.yaml").write_text("name: git-pkg\n")
        (pkg_a / "mcp").mkdir()
        (pkg_a / "mcp" / "figma.json").write_text("{}\n")

        (pkg_b / "hawk-package.yaml").write_text("name: local-pkg\n")
        (pkg_b / "mcp").mkdir()
        (pkg_b / "mcp" / "goose.json").write_text("{}\n")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        (registry_dir / "mcp").mkdir(parents=True)
        # Seed clash for git-pkg item.
        (registry_dir / "mcp" / "figma.json").write_text("{}\n")

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        v2_config.save_packages({
            "git-pkg": {
                "url": "https://github.com/acme/git-pkg.git",
                "installed": "2026-02-21",
                "commit": "abc1234",
                "items": [],
            }
        })

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        with pytest.raises(SystemExit) as e:
            cmd_scan(args)
        assert e.value.code == 1
        assert not (registry_dir / "mcp" / "goose.json").exists()

    def test_scan_does_not_steal_item_owned_by_other_package(self, tmp_path, monkeypatch):
        """Clashing items owned by another package stay with their owner."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text("name: new-pkg\n")
        (scan_dir / "mcp").mkdir()
        (scan_dir / "mcp" / "figma.json").write_text("{}\n")
        (scan_dir / "mcp" / "goose.json").write_text("{}\n")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        (registry_dir / "mcp").mkdir(parents=True)
        (registry_dir / "mcp" / "figma.json").write_text("{}\n")

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        v2_config.save_packages({
            "old-pkg": {
                "url": "https://github.com/acme/old-pkg.git",
                "installed": "2026-02-21",
                "commit": "abc1234",
                "items": [{"type": "mcp", "name": "figma.json", "hash": "deadbeef"}],
            }
        })

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        packages = v2_config.load_packages()
        assert "old-pkg" in packages
        assert "new-pkg" in packages

        old_names = {
            item["name"] for item in packages["old-pkg"]["items"]
            if item["type"] == "mcp"
        }
        new_names = {
            item["name"] for item in packages["new-pkg"]["items"]
            if item["type"] == "mcp"
        }
        assert old_names == {"figma.json"}
        assert new_names == {"goose.json"}

    def test_scan_skips_unowned_clash_when_content_differs(self, tmp_path, monkeypatch):
        """Unowned clashing items are only claimed when contents match."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text("name: new-pkg\n")
        (scan_dir / "mcp").mkdir()
        (scan_dir / "mcp" / "figma.json").write_text('{"scan":"value"}\n')
        (scan_dir / "mcp" / "goose.json").write_text("{}\n")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"
        (registry_dir / "mcp").mkdir(parents=True)
        # Same name, different content than scanned file.
        (registry_dir / "mcp" / "figma.json").write_text('{"registry":"value"}\n')

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        cmd_scan(args)

        packages = v2_config.load_packages()
        assert "new-pkg" in packages
        new_names = {
            item["name"] for item in packages["new-pkg"]["items"]
            if item["type"] == "mcp"
        }
        assert new_names == {"goose.json"}

    def test_scan_rejects_source_type_conflict(self, tmp_path, monkeypatch, capsys):
        """hawk scan refuses package source-type replacement (git -> local)."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_scan

        scan_dir = tmp_path / "my-collection"
        scan_dir.mkdir()
        (scan_dir / "hawk-package.yaml").write_text(
            "name: test-pkg\ndescription: Test\nversion: '1.0'\n"
        )
        (scan_dir / "commands").mkdir()
        (scan_dir / "commands" / "hello.md").write_text("# Hello")

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        v2_config.save_packages({
            "test-pkg": {
                "url": "https://github.com/acme/test-pkg.git",
                "installed": "2026-02-21",
                "commit": "abc1234",
                "items": [],
            }
        })

        args = argparse.Namespace(
            path=str(scan_dir),
            all=True,
            replace=False,
            depth=5,
            no_enable=True,
        )

        with pytest.raises(SystemExit) as exc:
            cmd_scan(args)

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "already exists with source [git]" in out
        assert "refusing to replace source metadata" in out
        assert not (registry_dir / "prompts" / "hello.md").exists()


class TestCmdPackagesSources:
    def test_packages_show_source_markers(self, tmp_path, monkeypatch, capsys):
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_packages

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")

        v2_config.save_packages({
            "git-pkg": {
                "url": "https://example.com/a.git",
                "path": "/tmp/local-a",
                "installed": "2026-02-21",
                "commit": "abcdef0",
                "items": [],
            },
            "local-pkg": {
                "url": "",
                "path": "/tmp/local-b",
                "installed": "2026-02-21",
                "commit": "",
                "items": [],
            },
            "manual-pkg": {
                "url": "",
                "installed": "2026-02-21",
                "commit": "",
                "items": [],
            },
        })

        cmd_packages(argparse.Namespace())

        out = capsys.readouterr().out
        assert "[git] git-pkg" in out
        assert "[local] local-pkg" in out
        assert "[manual] manual-pkg" in out


class TestCmdUpdateLocalPackages:
    def _patch_config_paths(self, monkeypatch, tmp_path):
        from hawk_hooks import v2_config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        registry_dir = tmp_path / "registry"

        monkeypatch.setattr(v2_config, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(v2_config, "get_global_config_path", lambda: config_dir / "config.yaml")
        monkeypatch.setattr(v2_config, "get_packages_path", lambda: config_dir / "packages.yaml")
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)
        return config_dir, registry_dir

    def test_update_local_missing_path_fails_nonzero(self, tmp_path, monkeypatch, capsys):
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_update

        self._patch_config_paths(monkeypatch, tmp_path)

        missing_path = tmp_path / "does-not-exist"
        v2_config.save_packages({
            "local-pkg": {
                "url": "",
                "path": str(missing_path),
                "installed": "2026-02-21",
                "commit": "",
                "items": [],
            }
        })

        args = argparse.Namespace(package=None, check=False, force=False, prune=False)
        with pytest.raises(SystemExit) as exc:
            cmd_update(args)

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "local source path not found" in out
        assert "hawk scan" in out
        assert "hawk remove-package local-pkg" in out

    def test_update_local_path_rescans_and_records_items(self, tmp_path, monkeypatch):
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.cli import cmd_update

        _, registry_dir = self._patch_config_paths(monkeypatch, tmp_path)

        local_dir = tmp_path / "local-pkg"
        local_dir.mkdir()
        (local_dir / "commands").mkdir()
        (local_dir / "commands" / "hello.md").write_text("# Hello")

        v2_config.save_packages({
            "local-pkg": {
                "url": "",
                "path": str(local_dir.resolve()),
                "installed": "2026-02-21",
                "commit": "",
                "items": [],
            }
        })

        monkeypatch.setattr("hawk_hooks.v2_sync.sync_all", lambda force=False: {})

        args = argparse.Namespace(package=None, check=False, force=False, prune=False)
        cmd_update(args)

        assert (registry_dir / "prompts" / "hello.md").exists()
        packages = v2_config.load_packages()
        assert packages["local-pkg"]["path"] == str(local_dir.resolve())
        assert len(packages["local-pkg"]["items"]) == 1
        assert packages["local-pkg"]["items"][0]["type"] == "prompt"
        assert packages["local-pkg"]["items"][0]["name"] == "hello.md"
