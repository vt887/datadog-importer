"""
Tests for widget validation and dashboard sanitization utilities.

This module tests the core validation and sanitization functions:
- validate_widgets(): ensures widget dimensions fit within grid constraints
- sanitize_dashboard_body(): removes deprecated/incompatible API fields
- generate_dashboard_diff(): produces a human-readable diff of changes

These functions ensure dashboards are valid before deployment to Datadog.
"""

import pytest

from helper import validate_widgets, sanitize_dashboard_body, generate_dashboard_diff


def test_validate_widgets_clamps_width():
    """Test that validate_widgets clamps widget width to maximum grid width.

    Scenario:
    - Widget width is 15 (exceeds max_width of 12)

    Expected behavior:
    - Widget width is clamped to 12
    - changed flag is True (modification was made)
    """
    widgets = [
        {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 15, "height": 8}}
    ]

    new_widgets, changed = validate_widgets(widgets, max_width=12)
    assert isinstance(new_widgets, list)
    assert isinstance(changed, bool)
    assert changed is True
    assert new_widgets[0]["layout"]["width"] == 12


def test_validate_widgets_clamps_x():
    """Test that validate_widgets clamps widget x position when width causes overflow.

    Scenario:
    - Widget x=10, width=6, max_width=12
    - Widget would extend to x=16 (beyond grid boundary at 12)
    - Max allowed x = max_width - width = 12 - 6 = 6

    Expected behavior:
    - Widget x is clamped to 6
    - changed flag is True
    """
    widgets = [
        {"definition": {"type": "timeseries"}, "layout": {"x": 10, "y": 0, "width": 6, "height": 8}}
    ]

    new_widgets, changed = validate_widgets(widgets, max_width=12)
    assert changed is True
    # max_x = 12 - width = 6 -> x should be clamped to 6
    assert new_widgets[0]["layout"]["x"] == 6


def test_validate_widgets_no_change():
    """Test that validate_widgets returns changed=False when no adjustment needed.

    Scenario:
    - Widget dimensions are valid: x=2, width=6, within max_width=12

    Expected behavior:
    - Widget remains unchanged
    - changed flag is False
    """
    widgets = [
        {"definition": {"type": "timeseries"}, "layout": {"x": 2, "y": 0, "width": 6, "height": 8}}
    ]

    new_widgets, changed = validate_widgets(widgets, max_width=12)
    assert changed is False
    assert new_widgets[0]["layout"]["width"] == 6
    assert new_widgets[0]["layout"]["x"] == 2


def test_validate_widgets_missing_layout_is_skipped():
    """Test that validate_widgets skips widgets without layout field.

    Scenario:
    - Widget has no layout key (malformed)

    Expected behavior:
    - Widget is skipped without error
    - changed flag is False
    - Widget remains in output unchanged
    """
    widgets = [
        {"definition": {"type": "timeseries"}}  # no layout key
    ]

    new_widgets, changed = validate_widgets(widgets, max_width=12)
    assert changed is False
    assert isinstance(new_widgets, list)
    assert new_widgets[0].get("layout") is None


def test_sanitize_dashboard_body_removes_deprecated():
    """Test that sanitize_dashboard_body removes deprecated API fields.

    Scenario:
    - Dashboard has deprecated fields: is_read_only (top level and nested)
    - These fields are not supported by current Datadog API

    Expected behavior:
    - Deprecated fields are removed
    - Other fields (title, widgets) are preserved
    """
    body = {
        "title": "T",
        "widgets": [],
        "metadata": {"is_read_only": True},
        "is_read_only": True,
    }
    cleaned = sanitize_dashboard_body(body)
    assert "is_read_only" not in cleaned
    assert "is_read_only" not in cleaned.get("metadata", {})
    assert cleaned["title"] == "T"


def test_generate_dashboard_diff_contains_changes():
    """Test that generate_dashboard_diff produces a readable diff of changes.

    Scenario:
    - Original dashboard has widget width=15
    - Modified dashboard has widget width=12 (clamped)

    Expected behavior:
    - Diff is a string
    - Diff contains the changed values (15 and 12)
    - Diff contains the field name (width)
    """
    orig = {"title": "T", "widgets": [{"layout": {"width": 15}}]}
    mod = {"title": "T", "widgets": [{"layout": {"width": 12}}]}
    diff = generate_dashboard_diff(orig, mod)
    assert isinstance(diff, str)
    assert "width" in diff
    assert "15" in diff and "12" in diff
