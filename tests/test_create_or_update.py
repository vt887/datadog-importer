"""
Tests for DatadogDashboardManager.create_or_update() behavior.

This module tests the logic that determines whether to create a new dashboard
or update an existing one based on the dashboard title.

Tests cover:
- Creating a new dashboard when no existing dashboard with the same title is found
- Updating an existing dashboard when a dashboard with the same title already exists
"""

import pytest
from unittest.mock import MagicMock

import helper


def test_create_or_update_creates_when_missing():
    """Test that create_or_update calls create_dashboard when no existing dashboard is found.

    Scenario:
    - _find_dashboard_by_title() returns None (dashboard doesn't exist)
    - create_dashboard() is mocked to return a new dashboard object

    Expected behavior:
    - create_dashboard should be called exactly once
    - update_dashboard should NOT be called
    - The returned response should be the created dashboard
    """
    # Create manager instance without invoking __init__ (using __new__)
    mgr = helper.DatadogDashboardManager.__new__(helper.DatadogDashboardManager)

    # Mock the methods we'll call
    mgr._find_dashboard_by_title = MagicMock(return_value=None)  # Dashboard not found
    mgr.create_dashboard = MagicMock(return_value={"id": "new-id", "title": "New"})
    mgr.update_dashboard = MagicMock()

    # Prepare the dashboard body to deploy
    body = {"title": "New", "widgets": []}

    # Call create_or_update
    resp = helper.DatadogDashboardManager.create_or_update(mgr, **body)

    # Assertions
    mgr.create_dashboard.assert_called_once()
    assert resp == {"id": "new-id", "title": "New"}


def test_create_or_update_updates_when_exists():
    """Test that create_or_update calls update_dashboard when an existing dashboard is found.

    Scenario:
    - _find_dashboard_by_title() returns an existing dashboard object
    - update_dashboard() is mocked to return the updated dashboard object

    Expected behavior:
    - update_dashboard should be called exactly once
    - create_dashboard should NOT be called
    - The returned response should be the updated dashboard
    """
    # Create manager instance without invoking __init__
    mgr = helper.DatadogDashboardManager.__new__(helper.DatadogDashboardManager)

    # Mock the methods we'll call
    mgr._find_dashboard_by_title = MagicMock(return_value={"id": "existing-id", "title": "Existing"})
    mgr.update_dashboard = MagicMock(return_value={"id": "existing-id", "title": "Existing"})
    mgr.create_dashboard = MagicMock()

    # Prepare the dashboard body to deploy
    body = {"title": "Existing", "widgets": []}

    # Call create_or_update
    resp = helper.DatadogDashboardManager.create_or_update(mgr, **body)

    # Assertions
    mgr.update_dashboard.assert_called_once()
    assert resp == {"id": "existing-id", "title": "Existing"}
