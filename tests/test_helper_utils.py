"""
Tests for template merging utilities.

This module tests the core merge_templates() function which is responsible for:
- Combining multiple template files into a single dashboard
- Stacking widgets vertically to avoid overlaps (optional)
- Merging collections like template_variables and notify_list
- Handling malformed/missing descendant templates gracefully

All tests use temporary directories and mocked file loaders to simulate
real-world merging scenarios without actual file I/O.
"""

from pathlib import Path

import pytest

import helper


def test_merge_templates_basic(monkeypatch, tmp_path):
    """Test basic merge of top-level template with descendant templates.

    Scenario:
    - Top template has 1 widget at (0,0) with height=2
    - Descendant d1 has 1 widget (not positioned) with height=3
    - Descendant d2 has 1 widget (not positioned) with height=4
    - stack=True (default: position widgets to avoid overlaps)

    Expected behavior:
    - Merged dashboard has 3 widgets total
    - d1's widget is positioned at y=3 (after top widget: 0+2+1)
    - d2's widget is positioned at y=7 (after d1: 3+3+1)
    - template_variables from all three are merged
    - notify_list from all three are merged and de-duplicated
    """
    # Prepare top-level template
    top_tpl = {
        "title": "Base",
        "widgets": [
            {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 12, "height": 2}}
        ],
        "template_variables": [{"name": "a"}],
        "notify_list": ["n1"],
    }

    # Create temporary file paths for descendants
    d1 = tmp_path / "d1.json"
    d2 = tmp_path / "d2.json"

    # Mock file loader to return different templates based on filename
    def fake_load(path: Path):
        """Load different template content based on the filename."""
        if path.name == "d1.json":
            return {
                "title": "Base - part1",
                "widgets": [
                    {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 12, "height": 3}}
                ],
                "template_variables": [{"name": "b"}],
                "notify_list": ["n2"],
            }
        elif path.name == "d2.json":
            return {
                "title": "Base - part2",
                "widgets": [
                    {"definition": {"type": "heatmap"}, "layout": {"x": 0, "y": 0, "width": 12, "height": 4}}
                ],
                "template_variables": [{"name": "c"}],
                "notify_list": ["n3"],
            }
        raise FileNotFoundError(path)

    # Patch the load_template_file function
    monkeypatch.setattr(helper, "load_template_file", fake_load)

    # Call merge_templates with stacking enabled
    merged = helper.merge_templates(top_tpl, [d1, d2], stack=True, verbose=False)

    # Assertions
    assert "widgets" in merged
    assert len(merged["widgets"]) == 3  # top + d1 + d2

    # Verify template variables were merged
    tv_names = [tv.get("name") for tv in merged.get("template_variables", [])]
    assert set(tv_names) >= {"a", "b", "c"}

    # Verify notify_list was merged
    assert set(merged.get("notify_list", [])) >= {"n1", "n2", "n3"}

    # Verify widget stacking
    # First incoming widget (d1) should be at y=3 (top height 2 + 1 gap)
    incoming_widget_1 = merged["widgets"][1]
    assert incoming_widget_1["layout"]["y"] == 3

    # Second incoming widget (d2) should be at y=7 (d1 at 3 + d1 height 3 + 1 gap)
    incoming_widget_2 = merged["widgets"][2]
    assert incoming_widget_2["layout"]["y"] == 7


def test_merge_templates_stack_false(monkeypatch, tmp_path):
    """Test merge with stacking disabled (preserve original y positions).

    Scenario:
    - Top template has 1 widget at (0,0) with height=2
    - Descendant has 1 widget positioned at y=5 with height=3
    - stack=False (don't reposition widgets)

    Expected behavior:
    - Merged dashboard has 2 widgets
    - Descendant's widget keeps original y position (5)
    - No automatic vertical stacking occurs
    """
    # Prepare top-level template
    top_tpl = {
        "title": "Base",
        "widgets": [
            {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 12, "height": 2}}
        ],
    }

    d1 = tmp_path / "d1.json"

    # Mock file loader
    def fake_load(path: Path):
        if path.name == "d1.json":
            return {
                "title": "Base - part1",
                "widgets": [
                    {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 5, "width": 12, "height": 3}}
                ],
            }
        raise FileNotFoundError(path)

    monkeypatch.setattr(helper, "load_template_file", fake_load)

    # Call merge with stack=False
    merged = helper.merge_templates(top_tpl, [d1], stack=False, verbose=False)

    # Assertions
    # When stack=False, original y position should be preserved
    assert merged["widgets"][1]["layout"]["y"] == 5


def test_merge_templates_malformed_descendant(monkeypatch, tmp_path, capsys):
    """Test that malformed/missing descendant templates are skipped gracefully.

    Scenario:
    - Top template has 1 widget
    - d1 is valid with 1 widget
    - d2 is malformed (raises RuntimeError)

    Expected behavior:
    - Merge continues despite d2 being malformed
    - Only d1's widget is merged (not d2)
    - Result has 2 widgets (top + d1, but not d2)
    - No exception is raised
    """
    # Prepare top-level template
    top_tpl = {
        "title": "Base",
        "widgets": [
            {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 12, "height": 2}}
        ],
    }

    d1 = tmp_path / "d1.json"
    d2 = tmp_path / "d2.json"

    # Mock file loader that simulates malformed JSON
    def fake_load(path: Path):
        if path.name == "d1.json":
            return {
                "title": "Base - part1",
                "widgets": [
                    {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 12, "height": 3}}
                ],
            }
        if path.name == "d2.json":
            # Simulate malformed JSON by raising an error
            raise RuntimeError("Malformed JSON")
        raise FileNotFoundError(path)

    monkeypatch.setattr(helper, "load_template_file", fake_load)

    # Should not raise; malformed descendant is skipped
    merged = helper.merge_templates(top_tpl, [d1, d2], stack=True, verbose=True)

    # Assertions
    assert len(merged["widgets"]) == 2  # top + d1 only (d2 skipped)
    # Verify only d1's widget type is present
    assert merged["widgets"][1]["definition"]["type"] == "timeseries"
