"""
Tests for dashboard delete operations.

This module tests the CLI delete workflow including:
- Dry-run delete (shows what would be deleted without actually deleting)
- Force delete (skips confirmation prompts)
- User confirmation workflow (prompts user to confirm)
- Multiple deletes with explicit IDs
- Error handling for invalid delete commands

All tests mock the DatadogDashboardManager to avoid actual API calls.
"""

import pytest
from unittest.mock import MagicMock, patch

from loader import main as loader_main, _build_cli
import loader


@patch("loader.DatadogDashboardManager", autospec=True)
def test_delete_dry_run_by_id(mock_mgr_class, monkeypatch, capsys):
    """Test that --delete with --dry-run shows planned deletion without actually deleting.

    Scenario:
    - User runs: python3 loader.py --delete id-123 --dry-run
    - The dashboard exists and will be found

    Expected behavior:
    - get_dashboard() is called to verify dashboard exists
    - No actual deletion occurs
    - Dry-run message is printed
    """
    # Setup mock manager
    mock_mgr = mock_mgr_class.return_value
    mock_mgr.get_dashboard.return_value = {"title": "My Dashboard", "id": "id-123"}

    # Simulate the CLI command
    parser = _build_cli()
    args = parser.parse_args(["--delete", "id-123", "--dry-run"])

    # Patch sys.argv to simulate user command
    monkeypatch.setattr("sys.argv", ["loader.py", "--delete", "id-123", "--dry-run"])
    with patch("builtins.print") as mock_print:
        loader_main()

    # Assertions
    mock_mgr.get_dashboard.assert_called_with("id-123")  # Should check if dashboard exists
    # Should print DRY-RUN message (not actually delete)
    mock_print.assert_any_call("[DRY-RUN] Would delete dashboard: My Dashboard (id=id-123)")


@patch("loader.DatadogDashboardManager", autospec=True)
def test_delete_force_deletes(mock_mgr_class, monkeypatch):
    """Test that --delete with --force (-y) skips confirmation and deletes immediately.

    Scenario:
    - User runs: python3 loader.py --delete id-123 --force
    - Dashboard exists

    Expected behavior:
    - get_dashboard() is called to verify dashboard exists
    - No confirmation prompt is shown
    - delete_dashboard() is called and actually deletes
    - Success message is printed
    """
    # Setup mock manager
    mock_mgr = mock_mgr_class.return_value
    mock_mgr.get_dashboard.return_value = {"title": "My Dashboard", "id": "id-123"}
    mock_mgr.delete_dashboard.return_value = {"status": "ok"}

    # Simulate the CLI command with --force
    monkeypatch.setattr("sys.argv", ["loader.py", "--delete", "id-123", "--force"])
    with patch("builtins.print") as mock_print:
        loader.main()

    # Assertions
    mock_mgr.delete_dashboard.assert_called_once_with("id-123")
    mock_print.assert_any_call("Deleted dashboard: My Dashboard (id=id-123)")


@patch("loader.DatadogDashboardManager", autospec=True)
def test_delete_aborted_by_user(mock_mgr_class, monkeypatch, capsys):
    """Test that user can abort deletion when prompted for confirmation.

    Scenario:
    - User runs: python3 loader.py --delete id-123 (no --force)
    - Dashboard exists
    - User types 'no' at confirmation prompt

    Expected behavior:
    - get_dashboard() is called to verify dashboard exists
    - User is prompted for confirmation
    - delete_dashboard() is NOT called (user aborted)
    - "Aborted by user" message is printed
    """
    # Setup mock manager
    mock_mgr = mock_mgr_class.return_value
    mock_mgr.get_dashboard.return_value = {"title": "My Dashboard", "id": "id-123"}

    # Simulate user typing 'no' at confirmation prompt
    monkeypatch.setattr("sys.argv", ["loader.py", "--delete", "id-123"])
    monkeypatch.setattr("builtins.input", lambda prompt='': 'no')

    with patch("builtins.print") as mock_print:
        loader.main()

    # Assertions
    # delete_dashboard should NOT be called when user declines
    mock_mgr.delete_dashboard.assert_not_called()
    mock_print.assert_any_call("Aborted by user.")


@patch("loader.DatadogDashboardManager", autospec=True)
def test_delete_confirm_all_confirmed(mock_mgr_class, monkeypatch):
    """Test deleting multiple dashboards with explicit IDs and --force.

    Scenario:
    - User runs: python3 loader.py -D id-1 -D id-2 -y
    - Multiple dashboards exist
    - User wants to delete all with force flag

    Expected behavior:
    - get_dashboard() is called for each ID to verify existence
    - delete_dashboard() is called exactly twice (once per ID)
    - Success messages are printed for each deletion
    """
    # Setup mock manager with side_effect for multiple calls
    mock_mgr = mock_mgr_class.return_value
    # get_dashboard will return different dashboard objects for each call
    mock_mgr.get_dashboard.side_effect = [
        {"id": "id-1", "title": "Dash One"},
        {"id": "id-2", "title": "Dash Two"},
    ]
    mock_mgr.delete_dashboard.return_value = {"status": "ok"}

    # Simulate user command with multiple IDs and force flag
    monkeypatch.setattr("sys.argv", ["loader.py", "-D", "id-1", "-D", "id-2", "-y"])

    with patch("builtins.print") as mock_print:
        loader.main()

    # Assertions
    assert mock_mgr.delete_dashboard.call_count == 2  # Should delete both
    mock_print.assert_any_call("Deleted dashboard: Dash One (id=id-1)")
    mock_print.assert_any_call("Deleted dashboard: Dash Two (id=id-2)")


@patch("loader.DatadogDashboardManager", autospec=True)
def test_delete_confirm_all_declined(mock_mgr_class, monkeypatch):
    """Test that invalid delete command (-D without ID) is caught by argparse.

    Scenario:
    - User runs: python3 loader.py -D -y  (forgot to specify ID)

    Expected behavior:
    - argparse detects the missing required argument
    - System exits with error code 2
    - Error message indicates missing argument for --delete/-D
    - delete_dashboard() is NOT called
    """
    # Setup mock manager
    mock_mgr = mock_mgr_class.return_value

    # Simulate user mistakenly writing -D -y (no ID provided)
    monkeypatch.setattr("sys.argv", ["loader.py", "-D", "-y"])

    # Capture stderr to check error message
    import sys
    from io import StringIO

    stderr = StringIO()
    old_stderr = sys.stderr
    try:
        sys.stderr = stderr
        # argparse will exit with error code 2 for invalid arguments
        with pytest.raises(SystemExit) as exc:
            loader.main()
    finally:
        sys.stderr = old_stderr

    # Assertions
    assert exc.value.code == 2  # argparse error code
    err = stderr.getvalue()
    assert "argument --delete/-D: expected one argument" in err
    mock_mgr.delete_dashboard.assert_not_called()
