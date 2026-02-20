"""Tests for v2 CLI."""

import pytest

from hawk_hooks.v2_cli import _name_from_content, build_parser


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

    def test_sync_dry_run(self):
        args = self.parser.parse_args(["sync", "--dry-run"])
        assert args.dry_run is True

    def test_sync_with_tool(self):
        args = self.parser.parse_args(["sync", "--tool", "claude"])
        assert args.tool == "claude"

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

    def test_add_no_enable(self):
        args = self.parser.parse_args(["add", "skill", "/path", "--no-enable"])
        assert args.enable is False

    def test_add_enable_default(self):
        args = self.parser.parse_args(["add", "skill", "/path"])
        assert args.enable is True

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
        assert args.no_enable is False

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

    def test_scan_no_enable(self):
        args = self.parser.parse_args(["scan", "--no-enable"])
        assert args.no_enable is True

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
        from hawk_hooks.v2_cli import cmd_new

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
        from hawk_hooks.v2_cli import cmd_new

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
        from hawk_hooks.v2_cli import cmd_new

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace(
            type="command", name="deploy", event="pre_tool_use",
            lang=".py", force=False,
        )
        cmd_new(args)

        cmd_file = registry_dir / "commands" / "deploy.md"
        assert cmd_file.exists()
        content = cmd_file.read_text()
        assert "deploy" in content

    def test_new_agent_creates_file(self, tmp_path, monkeypatch):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.v2_cli import cmd_new

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
        from hawk_hooks.v2_cli import cmd_new

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
        from hawk_hooks.v2_cli import cmd_new

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


class TestCmdDeps:
    """Test hawk deps command."""

    def test_deps_no_hooks(self, tmp_path, monkeypatch, capsys):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.v2_cli import cmd_deps

        registry_dir = tmp_path / "registry"
        monkeypatch.setattr(v2_config, "get_registry_path", lambda cfg=None: registry_dir)

        args = argparse.Namespace()
        cmd_deps(args)

        captured = capsys.readouterr()
        assert "No hooks directory" in captured.out

    def test_deps_no_deps_found(self, tmp_path, monkeypatch, capsys):
        import argparse
        from hawk_hooks import v2_config
        from hawk_hooks.v2_cli import cmd_deps

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
        from hawk_hooks.v2_cli import cmd_scan

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
        assert pkg["items"][0]["type"] == "command"
        assert pkg["items"][0]["name"] == "hello.md"

    def test_scan_all_without_manifest_no_package(self, tmp_path, monkeypatch):
        """hawk scan --all without a manifest does not record a package."""
        import argparse

        from hawk_hooks import v2_config
        from hawk_hooks.v2_cli import cmd_scan

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
