"""Tests for v2 CLI."""

import pytest

from hawk_hooks.v2_cli import build_parser


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
