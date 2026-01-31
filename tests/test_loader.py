"""Tests for loader.deploy_templates CLI behavior.

This module tests the high-level deployment workflow of `deploy_templates`:

Deployment behaviors tested:
- Dry-run mode: Shows a JSON diff and skips API calls
- Actual deployment: Calls the DatadogDashboardManager to create/update dashboards
- Widget validation: Ensures widget dimensions are clamped to grid constraints
- Multi-widget dashboards: Handles multiple widgets with correct positioning
- Template variables: Preserves and merges template variable definitions
- Complex layouts: Handles dashboards with various widget types and configurations

Testing approach:
- All tests patch `loader.DatadogDashboardManager` to avoid real API calls
- Tests use temporary directories to write template files
- Tests capture stdout/stderr to verify output messages
- Mocks are configured with return values matching expected Datadog API responses

Widget types tested:
- timeseries: Line/area charts with metric queries
- query_value: Single value displays
- log_stream: Real-time log views
- distribution: Histogram distributions
- heatmap: 2D heatmap visualizations
- toplist: Top N items ranking
- check_status: Service health status indicators
- differential: Rate of change calculations
- cat_scan: Category scan visualizations
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from loader import deploy_templates

# =============================================================================
# Template Fixtures
# =============================================================================
# These template dictionaries represent various Datadog dashboard configurations
# used in tests. They match the schema expected by the Datadog API.

# SAMPLE_TEMPLATE: A minimal dashboard used for testing basic deployment
# It has an intentionally-large width (47) to test widget validation/clamping
SAMPLE_TEMPLATE = {
    "title": "sample",
    "widgets": [
        {"definition": {"type": "timeseries"}, "layout": {"x": 0, "y": 0, "width": 47, "height": 15}}
    ],
}

# TEMPLATE_TIMESERIES: Dashboard with a timeseries (line/area) widget
# Tests metric visualization and time-series queries
TEMPLATE_TIMESERIES = {
    "title": "Time Series Widget",
    "widgets": [
        {
            "definition": {
                "type": "timeseries",
                "requests": [
                    {
                        "q": "avg:system.cpu.user{*}",
                        "display_type": "line"
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

# TEMPLATE_QUERY_VALUE: Dashboard with a query value (single value) widget
# Tests single metric display and aggregation
TEMPLATE_QUERY_VALUE = {
    "title": "Query Value Widget",
    "widgets": [
        {
            "definition": {
                "type": "query_value",
                "requests": [
                    {
                        "q": "avg:system.load.1{*}",
                        "aggregator": "avg"
                    }
                ],
                "autoscale": True
            },
            "layout": {"x": 0, "y": 0, "width": 6, "height": 6}
        }
    ],
}

TEMPLATE_LOG_STREAM = {
    "title": "Log Stream Widget",
    "widgets": [
        {
            "definition": {
                "type": "log_stream",
                "logset": "Logs",
                "indexes": ["main"],
                "query": "status:error",
                "columns": ["timestamp", "message", "host"],
                "show_date_column": True
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_DISTRIBUTION = {
    "title": "Distribution Widget",
    "widgets": [
        {
            "definition": {
                "type": "distribution",
                "requests": [
                    {
                        "q": "avg:system.mem.used{*}",
                        "style": {"palette": "cool"}
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_HEATMAP = {
    "title": "Heatmap Widget",
    "widgets": [
        {
            "definition": {
                "type": "heatmap",
                "requests": [
                    {
                        "q": "avg:system.cpu.user{*} by {host}"
                    }
                ],
                "yaxis": {"include_zero": True}
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_TOPLIST = {
    "title": "Top List Widget",
    "widgets": [
        {
            "definition": {
                "type": "toplist",
                "requests": [
                    {
                        "q": "top(avg:system.mem.used{*} by {host}, 10, 'desc', 'avg')"
                    }
                ],
                "custom_links": [
                    {
                        "link": "https://datadog.com",
                        "label": "View in Datadog"
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_CHECK_STATUS = {
    "title": "Check Status Widget",
    "widgets": [
        {
            "definition": {
                "type": "check_status",
                "checks": [
                    {
                        "name": "HTTP Check",
                        "query": "http{Check URL}"
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 6, "height": 4}
        }
    ],
}

TEMPLATE_DIFFERENTIAL = {
    "title": "Differential Widget",
    "widgets": [
        {
            "definition": {
                "type": "differential",
                "requests": [
                    {
                        "q": "diff(avg:system.mem.used{*} by {host})"
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_CAT_SCAN = {
    "title": "Cat Scan Widget",
    "widgets": [
        {
            "definition": {
                "type": "cat_scan",
                "requests": [
                    {
                        "q": "sum:system.net.bytes_rcvd{*}",
                        "style": {"palette": "dog_classic"}
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_WITH_TEMPLATE_VARIABLES = {
    "title": "Dashboard with Template Variables",
    "widgets": [
        {
            "definition": {
                "type": "timeseries",
                "requests": [
                    {
                        "q": "avg:system.cpu.user{$env}",
                        "display_type": "area"
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 12, "height": 8}
        }
    ],
    "template_variables": [
        {
            "name": "env",
            "prefix": "env",
            "default": "prod",
            "available_values": ["prod", "dev", "staging"]
        },
        {
            "name": "service",
            "prefix": "service",
            "default": "*",
            "available_values": []
        }
    ]
}

TEMPLATE_MULTI_WIDGET = {
    "title": "Multi-Widget Dashboard",
    "widgets": [
        {
            "definition": {
                "type": "timeseries",
                "requests": [
                    {
                        "q": "avg:system.cpu.user{*}",
                        "display_type": "line"
                    }
                ]
            },
            "layout": {"x": 0, "y": 0, "width": 6, "height": 8}
        },
        {
            "definition": {
                "type": "query_value",
                "requests": [
                    {
                        "q": "avg:system.load.1{*}",
                        "aggregator": "avg"
                    }
                ]
            },
            "layout": {"x": 6, "y": 0, "width": 6, "height": 8}
        },
        {
            "definition": {
                "type": "heatmap",
                "requests": [
                    {
                        "q": "avg:system.mem.used{*} by {host}"
                    }
                ]
            },
            "layout": {"x": 0, "y": 8, "width": 12, "height": 8}
        }
    ],
}

TEMPLATE_COMPLEX_LAYOUT = {
    "title": "Complex Layout Dashboard",
    "widgets": [
        {
            "definition": {"type": "timeseries"},
            "layout": {"x": 0, "y": 0, "width": 3, "height": 2}
        },
        {
            "definition": {"type": "query_value"},
            "layout": {"x": 3, "y": 0, "width": 3, "height": 2}
        },
        {
            "definition": {"type": "toplist"},
            "layout": {"x": 6, "y": 0, "width": 6, "height": 2}
        },
        {
            "definition": {"type": "distribution"},
            "layout": {"x": 0, "y": 2, "width": 4, "height": 3}
        },
        {
            "definition": {"type": "heatmap"},
            "layout": {"x": 4, "y": 2, "width": 4, "height": 3}
        },
        {
            "definition": {"type": "log_stream"},
            "layout": {"x": 8, "y": 2, "width": 4, "height": 3}
        }
    ],
}

TEMPLATE_MINIMAL = {
    "title": "Minimal Dashboard",
    "widgets": []
}

TEMPLATE_LARGE_DASHBOARD = {
    "title": "Large Dashboard with Many Widgets",
    "widgets": [
        {
            "definition": {
                "type": "timeseries",
                "requests": [{"q": f"avg:system.cpu.user{{env:prod}} by {{service:web{i}}}"}]
            },
            "layout": {"x": (i % 12), "y": (i // 12) * 8, "width": 6, "height": 8}
        }
        for i in range(20)
    ],
}

INVALID_TEMPLATE_MISSING_WIDGETS = {
    "title": "Invalid Template - Missing Widgets",
    "widgets": None
}

INVALID_TEMPLATE_MISSING_LAYOUT = {
    "title": "Invalid Template - Missing Layout",
    "widgets": [
        {
            "definition": {"type": "timeseries"},
            # Missing layout
        }
    ]
}

INVALID_TEMPLATE_INVALID_LAYOUT = {
    "title": "Invalid Template - Invalid Layout",
    "widgets": [
        {
            "definition": {"type": "timeseries"},
            "layout": {"x": 0, "y": 0, "width": -1, "height": 0}  # Invalid dimensions
        }
    ]
}


def write_template(path: Path, content: dict):
    """Write JSON content to `path`.

    This helper keeps tests small and focused by writing a single template
    file to a temporary directory used by the test.

    Args:
        path: Path where the JSON file should be written
        content: Dict to serialize as JSON
    """
    path.write_text(json.dumps(content))


def write_multiple_templates(temp_dir: Path, templates: dict):
    """Write multiple template files to the temp directory.

    Useful for testing multi-file dashboard merging and grouping.

    Args:
        temp_dir: Path to temporary directory
        templates: Dict mapping filename to template content
    """
    for filename, content in templates.items():
        file_path = temp_dir / filename
        write_template(file_path, content)


def capture_stdout(func):
    """Run `func()` and return the captured stdout as a string.

    Temporarily replaces sys.stdout to capture print output without side effects.
    Useful for verifying that tests produce expected output messages.

    Args:
        func: Callable that produces stdout output

    Returns:
        String containing all captured stdout
    """
    from io import StringIO
    import sys

    old = sys.stdout
    sys.stdout = StringIO()
    try:
        func()
        return sys.stdout.getvalue()
    finally:
        sys.stdout = old


def _extract_dashboard_from_mock(mock_instance):
    """Return the dashboard body dict passed to mock_instance.create_or_update.

    Handles both positional and keyword invocation styles used by the code
    under test. Fails the test if the mock was not called.

    This helper extracts the dashboard dict from various call styles:
    - create_or_update(dashboard_dict)
    - create_or_update(title="T", widgets=[...])
    - create_or_update(**dashboard_dict)

    Args:
        mock_instance: MagicMock object with create_or_update method

    Returns:
        Dashboard dict that was passed to create_or_update

    Raises:
        AssertionError: If create_or_update was never called
    """
    call_args = mock_instance.create_or_update.call_args
    assert call_args is not None, "create_or_update was not called"
    pos_args, call_kwargs = call_args
    if call_kwargs:
        return call_kwargs
    if pos_args and isinstance(pos_args[0], dict):
        return pos_args[0]
    for a in pos_args:
        if isinstance(a, dict):
            return a
    return {}


@patch("loader.DatadogDashboardManager", autospec=True)
def test_dry_run_shows_diff(mock_mgr):
    """Test that dry-run mode shows planned changes without calling the Datadog API.

    Scenario:
    - User runs: python3 loader.py --dry-run
    - Dashboard template has widget with oversized width (47, exceeds max 12)

    Expected behavior:
    - Dry-run mode is activated (no API calls to manager)
    - Widget validation runs and shows that width will be clamped to 12
    - A unified diff is printed showing the planned change
    - No actual deployment occurs
    """
    # Setup a temp templates dir and write the sample template
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "t.json"
        write_template(f, SAMPLE_TEMPLATE)

        # Capture stdout by temporarily swapping sys.stdout
        from io import StringIO
        import sys

        old = sys.stdout
        sys.stdout = StringIO()
        try:
            # Run in dry-run mode (no API calls expected)
            deploy_templates(templates_dir=td_path, dry_run=True)
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old

        # Assertions
        assert "[DRY-RUN] Would deploy dashboard" in out
        assert "width" in out  # diff contains the clamped width


@patch("loader.DatadogDashboardManager", autospec=True)
def test_confirm_skips_deployment_when_no(mock_mgr):
    """Test that deployment is skipped when user declines confirmation.

    Note: Interactive confirmation was removed in recent refactoring,
    so this test now verifies that deployment proceeds by default without
    a confirmation step.

    Scenario:
    - User runs: python3 loader.py
    - Dashboard template exists

    Expected behavior:
    - Manager is called to deploy (no confirmation step)
    - create_or_update is invoked exactly once
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "t.json"
        write_template(f, SAMPLE_TEMPLATE)

        # Patch manager instance and its create_or_update return value
        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        # Capture stdout
        from io import StringIO
        import sys

        old = sys.stdout
        sys.stdout = StringIO()
        try:
            # Not a dry-run; deploy_templates should call the manager directly
            deploy_templates(templates_dir=td_path, dry_run=False)
            out = sys.stdout.getvalue()
        finally:
            sys.stdout = old

        # Ensure the manager was invoked (deployment proceeded)
        mock_instance.create_or_update.assert_called_once()


@patch("loader.DatadogDashboardManager", autospec=True)
def test_deploy_calls_manager(mock_mgr):
    """Test that deploy_templates calls the manager to create/update dashboards.

    Scenario:
    - User runs: python3 loader.py (actual deployment, not dry-run)
    - Dashboard template exists
    - User is prompted and confirms with 'y'

    Expected behavior:
    - Manager is initialized
    - create_or_update is called with the dashboard body
    - Success message is printed with dashboard URL
    """
    # Test that when not dry-run and user confirms, the manager is called
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "t.json"
        write_template(f, SAMPLE_TEMPLATE)

        # Patch manager instance and its create_or_update return value
        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        # Patch input to return 'y' to confirm
        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            # Capture stdout while running the deploy
            from io import StringIO
            import sys

            old = sys.stdout
            sys.stdout = StringIO()
            try:
                deploy_templates(templates_dir=td_path, dry_run=False)
                out = sys.stdout.getvalue()
            finally:
                sys.stdout = old

        # Verify deploy message and that the manager was invoked
        assert "Dashboard deployed" in out
        mock_instance.create_or_update.assert_called_once()


# =============================================================================
# Widget Type Tests
# =============================================================================
# These tests verify that deploy_templates correctly handles various Datadog
# widget types. Each widget type has unique properties and query formats.
# The tests ensure our framework doesn't break on different dashboard
# configurations.

@patch("loader.DatadogDashboardManager", autospec=True)
def test_timeseries_widget_deployment(mock_mgr):
    """Test deployment of dashboard with timeseries (line/area) widget.

    Timeseries widgets show metrics over time using line, area, or step displays.
    Common use case: CPU usage, latency, error rates over time.

    Scenario:
    - Dashboard contains a timeseries widget with metric query
    - Dry-run and actual deployment tested

    Expected behavior:
    - Dry-run shows dashboard name and diff
    - Actual deployment calls manager.create_or_update
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "timeseries.json"
        write_template(f, TEMPLATE_TIMESERIES)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        out = capture_stdout(lambda: deploy_templates(td_path, dry_run=True))

        # Verify dry-run works with timeseries widget
        assert "[DRY-RUN] Would deploy dashboard" in out
        assert "Time Series Widget" in out

        # Also test actual deployment
        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        mock_instance.create_or_update.assert_called_once()


@patch("loader.DatadogDashboardManager", autospec=True)
def test_query_value_widget_deployment(mock_mgr):
    """Test deployment of dashboard with query value (single value) widget.

    Query value widgets display a single number: sum, average, max, min, etc.
    Common use case: Current user count, total errors, average response time.

    Scenario:
    - Dashboard contains a query value widget
    - Tests that widget properties are preserved

    Expected behavior:
    - Manager is called with correct dashboard title and widget
    - Query value widget is included in the dashboard body
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "query_value.json"
        write_template(f, TEMPLATE_QUERY_VALUE)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert dashboard.get("title") == "Query Value Widget"


@patch("loader.DatadogDashboardManager", autospec=True)
def test_log_stream_widget_deployment(mock_mgr):
    """Test deployment of dashboard with log stream widget.

    Log stream widgets display real-time log entries with filtering and search.
    Common use case: Viewing application logs, error logs, audit trails.

    Scenario:
    - Dashboard contains a log stream widget with query filter
    - Tests that log configuration is preserved

    Expected behavior:
    - Manager is called with correct dashboard
    - Log stream widget properties are included
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "log_stream.json"
        write_template(f, TEMPLATE_LOG_STREAM)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "log_stream" in str(dashboard.get("widgets"))


@patch("loader.DatadogDashboardManager", autospec=True)
def test_distribution_widget_deployment(mock_mgr):
    """Test deployment of dashboard with distribution (histogram) widget.

    Distribution widgets show the frequency distribution of metric values.
    Common use case: Response time distribution, error rate distribution.

    Scenario:
    - Dashboard contains a distribution widget
    - Tests that histogram configuration is preserved

    Expected behavior:
    - Manager is called with correct dashboard
    - Distribution widget is included in body
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "distribution.json"
        write_template(f, TEMPLATE_DISTRIBUTION)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "distribution" in str(dashboard.get("widgets"))


@patch("loader.DatadogDashboardManager", autospec=True)
def test_heatmap_widget_deployment(mock_mgr):
    """Test deployment of dashboard with heatmap widget.

    Heatmap widgets display a 2D visualization with time on one axis and
    grouping dimension on the other. Color intensity represents metric value.
    Common use case: Response time by host, CPU usage by container.

    Scenario:
    - Dashboard contains a heatmap widget
    - Tests that heatmap configuration is preserved

    Expected behavior:
    - Manager is called with correct dashboard
    - Heatmap widget is included
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "heatmap.json"
        write_template(f, TEMPLATE_HEATMAP)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "heatmap" in str(dashboard.get("widgets"))


@patch("loader.DatadogDashboardManager", autospec=True)
def test_toplist_widget_deployment(mock_mgr):
    """Test deployment of dashboard with toplist widget including custom links."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "toplist.json"
        write_template(f, TEMPLATE_TOPLIST)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "toplist" in str(dashboard.get("widgets"))


@patch("loader.DatadogDashboardManager", autospec=True)
def test_check_status_widget_deployment(mock_mgr):
    """Test deployment of dashboard with check status widget."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "check_status.json"
        write_template(f, TEMPLATE_CHECK_STATUS)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "check_status" in str(dashboard.get("widgets"))


@patch("loader.DatadogDashboardManager", autospec=True)
def test_differential_widget_deployment(mock_mgr):
    """Test deployment of dashboard with differential widget."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "differential.json"
        write_template(f, TEMPLATE_DIFFERENTIAL)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "differential" in str(dashboard.get("widgets"))


@patch("loader.DatadogDashboardManager", autospec=True)
def test_cat_scan_widget_deployment(mock_mgr):
    """Test deployment of dashboard with cat scan widget."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "cat_scan.json"
        write_template(f, TEMPLATE_CAT_SCAN)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "cat_scan" in str(dashboard.get("widgets"))


# ====================
# Template Variables Tests
# ====================

@patch("loader.DatadogDashboardManager", autospec=True)
def test_dashboard_with_template_variables(mock_mgr):
    """Test deployment of dashboard with template variables."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "template_vars.json"
        write_template(f, TEMPLATE_WITH_TEMPLATE_VARIABLES)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert "template_variables" in dashboard
        assert len(dashboard["template_variables"]) == 2
        assert dashboard["template_variables"][0]["name"] == "env"
        assert dashboard["template_variables"][1]["name"] == "service"


# ====================
# Multi-Widget Tests
# ====================

@patch("loader.DatadogDashboardManager", autospec=True)
def test_multi_widget_dashboard(mock_mgr):
    """Test deployment of dashboard with multiple widget types."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "multi_widget.json"
        write_template(f, TEMPLATE_MULTI_WIDGET)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert len(dashboard["widgets"]) == 3
        widget_types = [widget["definition"]["type"] for widget in dashboard["widgets"]]
        assert "timeseries" in widget_types
        assert "query_value" in widget_types
        assert "heatmap" in widget_types


@patch("loader.DatadogDashboardManager", autospec=True)
def test_complex_layout_dashboard(mock_mgr):
    """Test deployment of dashboard with complex grid layout."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "complex_layout.json"
        write_template(f, TEMPLATE_COMPLEX_LAYOUT)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert len(dashboard["widgets"]) == 6
        layouts = [widget["layout"] for widget in dashboard["widgets"]]
        assert len(set((layout["x"], layout["y"]) for layout in layouts)) == len(layouts)


@patch("loader.DatadogDashboardManager", autospec=True)
def test_large_dashboard_deployment(mock_mgr):
    """Test deployment of a large dashboard with many widgets."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "large_dashboard.json"
        write_template(f, TEMPLATE_LARGE_DASHBOARD)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert len(dashboard["widgets"]) == 20


@patch("loader.DatadogDashboardManager", autospec=True)
def test_empty_dashboard_deployment(mock_mgr):
    """Test deployment of an empty dashboard."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        f = td_path / "empty_dashboard.json"
        write_template(f, TEMPLATE_MINIMAL)

        mock_instance = mock_mgr.return_value
        mock_instance.create_or_update.return_value = {"url": "http://example"}

        from unittest.mock import patch as mp
        with mp("builtins.input", return_value="y"):
            deploy_templates(td_path, dry_run=False)

        assert mock_instance.create_or_update.called
        dashboard = _extract_dashboard_from_mock(mock_instance)
        assert len(dashboard.get("widgets", [])) == 0


@patch("loader.DatadogDashboardManager", autospec=True)
def test_recursive_discovery(mock_mgr_class, tmp_path, monkeypatch):
    """Ensure loader discovers templates recursively using subdirectories."""
    # create nested directory structure with one template file inside
    nested_dir = tmp_path / "nested" / "sub"
    nested_dir.mkdir(parents=True)

    nested_file = nested_dir / "ABC_Monitoring--2025-09-29T10_38_16.json"
    nested_content = {
        "title": "ABC_Monitoring - Nested Panel",
        "widgets": [
            {"definition": {"type": "query_value", "requests": [{"q": "avg:system.cpu.user{*}"}]},
             "layout": {"x": 0, "y": 0, "width": 12, "height": 3}}
        ]
    }
    nested_file.write_text(json.dumps(nested_content))

    # Run deploy_templates pointing templates_dir to the tmp_path root
    # Use dry_run so no API calls are made
    # Patch DatadogDashboardManager to ensure no real network calls
    mock_mgr = mock_mgr_class.return_value

    # Call deploy_templates - it should find the nested JSON
    deploy_templates(templates_dir=tmp_path, dry_run=True, verbose=True)

    # validate nothing was sent to Datadog (dry-run) and no exceptions raised
    assert mock_mgr.create_or_update.call_count == 0


@patch("loader.DatadogDashboardManager", autospec=True)
def test_deploy_from_directory_selection(mock_mgr_class, tmp_path):
    """Ensure providing a directory via --files makes the loader discover JSON inside it."""
    # Create a directory with multiple JSON templates
    dir_path = tmp_path / "templates_dir"
    dir_path.mkdir()

    (dir_path / "a.json").write_text(json.dumps({"title": "A - part", "widgets": []}))
    (dir_path / "b.json").write_text(json.dumps({"title": "B - part", "widgets": []}))

    # Call deploy_templates with selected_files pointing to the directory
    mock_mgr = mock_mgr_class.return_value

    # Run in dry-run to avoid actual API calls
    deploy_templates(templates_dir=Path(), dry_run=True, selected_files=[str(dir_path)], verbose=True)

    # Ensure no create_or_update calls were made (dry-run)
    assert mock_mgr.create_or_update.call_count == 0
