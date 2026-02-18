"""Tests for toggle list grouping logic."""

from hawk_hooks.types import ToggleGroup, ToggleScope


class TestToggleGroup:
    def test_dataclass_defaults(self):
        g = ToggleGroup(key="pkg", label="📦 pkg", items=["a", "b"])
        assert g.collapsed is False
        assert g.items == ["a", "b"]

    def test_collapsed_state(self):
        g = ToggleGroup(key="pkg", label="📦 pkg", items=["a", "b"], collapsed=True)
        assert g.collapsed is True


class TestToggleGroupIntegration:
    """Test the row-building and grouping logic without the interactive loop."""

    def _build_rows(self, groups, items):
        """Simulate the row building from run_toggle_list."""
        ROW_GROUP_HEADER = "group_header"
        ROW_ITEM = "item"
        ROW_SEPARATOR = "separator"
        ROW_ACTION = "action"

        rows = []
        if groups:
            for gi, group in enumerate(groups):
                rows.append((ROW_GROUP_HEADER, group.key, gi))
                if not group.collapsed:
                    for name in group.items:
                        rows.append((ROW_ITEM, name, gi))
        else:
            for name in items:
                rows.append((ROW_ITEM, name, -1))

        rows.append((ROW_SEPARATOR, "", -1))
        rows.append((ROW_ACTION, "__select_all__", -1))
        rows.append((ROW_ACTION, "__select_none__", -1))
        rows.append((ROW_ACTION, "__done__", -1))
        return rows

    def test_flat_mode_no_groups(self):
        rows = self._build_rows(None, ["a", "b", "c"])
        item_rows = [r for r in rows if r[0] == "item"]
        assert len(item_rows) == 3
        header_rows = [r for r in rows if r[0] == "group_header"]
        assert len(header_rows) == 0

    def test_grouped_mode_with_headers(self):
        groups = [
            ToggleGroup(key="pkg1", label="📦 pkg1", items=["a", "b"]),
            ToggleGroup(key="pkg2", label="📦 pkg2", items=["c"]),
        ]
        rows = self._build_rows(groups, ["a", "b", "c"])
        headers = [r for r in rows if r[0] == "group_header"]
        items = [r for r in rows if r[0] == "item"]
        assert len(headers) == 2
        assert len(items) == 3

    def test_collapsed_group_hides_items(self):
        groups = [
            ToggleGroup(key="pkg1", label="📦 pkg1", items=["a", "b"], collapsed=True),
            ToggleGroup(key="pkg2", label="📦 pkg2", items=["c"]),
        ]
        rows = self._build_rows(groups, ["a", "b", "c"])
        headers = [r for r in rows if r[0] == "group_header"]
        items = [r for r in rows if r[0] == "item"]
        assert len(headers) == 2
        assert len(items) == 1  # only pkg2's "c" visible
        assert items[0][1] == "c"

    def test_ungrouped_section(self):
        groups = [
            ToggleGroup(key="pkg1", label="📦 pkg1", items=["a"]),
            ToggleGroup(key="__ungrouped__", label="ungrouped", items=["x", "y"]),
        ]
        rows = self._build_rows(groups, ["a", "x", "y"])
        items = [r for r in rows if r[0] == "item"]
        assert len(items) == 3

    def test_all_collapsed(self):
        groups = [
            ToggleGroup(key="pkg1", label="📦 pkg1", items=["a", "b"], collapsed=True),
            ToggleGroup(key="pkg2", label="📦 pkg2", items=["c"], collapsed=True),
        ]
        rows = self._build_rows(groups, ["a", "b", "c"])
        items = [r for r in rows if r[0] == "item"]
        assert len(items) == 0
        headers = [r for r in rows if r[0] == "group_header"]
        assert len(headers) == 2

    def test_actions_always_present(self):
        groups = [
            ToggleGroup(key="pkg1", label="📦 pkg1", items=["a"], collapsed=True),
        ]
        rows = self._build_rows(groups, ["a"])
        actions = [r for r in rows if r[0] == "action"]
        assert len(actions) == 3  # select all, select none, done

    def test_group_enabled_count(self):
        """Test the enabled count computation logic."""
        group = ToggleGroup(key="pkg", label="📦 pkg", items=["a", "b", "c"])
        checked = {"a", "c"}
        enabled = sum(1 for name in group.items if name in checked)
        assert enabled == 2
        assert len(group.items) == 3


class TestToggleGroupWithScopes:
    """Verify grouping works with N-scope model."""

    def test_groups_and_scopes_compose(self):
        """Groups organize the visual layout, scopes control which enabled set is active."""
        groups = [
            ToggleGroup(key="pkg1", label="📦 pkg1", items=["a", "b"]),
        ]
        scopes = [
            ToggleScope(key="global", label="All projects", enabled=["a"]),
            ToggleScope(key="/local", label="This project", enabled=["b"]),
        ]
        # Scope 0 (global): a is enabled
        checked_sets = [set(s.enabled) for s in scopes]
        assert "a" in checked_sets[0]
        assert "b" in checked_sets[1]

        # Group counts depend on which scope is active
        scope_0_enabled = sum(1 for name in groups[0].items if name in checked_sets[0])
        scope_1_enabled = sum(1 for name in groups[0].items if name in checked_sets[1])
        assert scope_0_enabled == 1  # "a"
        assert scope_1_enabled == 1  # "b"
