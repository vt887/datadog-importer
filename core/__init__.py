"""Validation and sanitization utilities for dashboards."""

import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Tuple

from config import DASHBOARD_GRID_WIDTH, DEPRECATED_KEYS


def validate_widgets(widgets: Iterable[Dict[str, Any]], max_width: int = DASHBOARD_GRID_WIDTH) -> Tuple[List[Dict[str, Any]], bool]:
    """Validate widget layouts and clamp values that exceed Datadog limits.

    This function ensures widgets fit within the Datadog dashboard grid constraints.
    It clamps the `layout.width` to `max_width` when present and adjusts `layout.x`
    to ensure the widget remains inside the grid boundaries.

    Args:
        widgets: List of widget dictionaries with layout information
        max_width: Maximum allowed width for widgets (default: 12, Datadog's grid width)

    Returns:
        A tuple (new_widgets, changed) where:
        - new_widgets: List of validated widget dictionaries (possibly modified)
        - changed: Boolean indicating if any modifications were made
    """
    changed: bool = False
    new_widgets: List[Dict[str, Any]] = deepcopy(list(widgets))

    for w in new_widgets:
        layout = w.get("layout")
        if not isinstance(layout, dict):
            continue

        width = layout.get("width")
        if isinstance(width, int) and width > max_width:
            layout["width"] = max_width
            changed = True

        x = layout.get("x")
        if isinstance(x, int):
            width_now = layout.get("width", 1)
            max_x = max(0, max_width - (width_now or 1))

            if x > max_x:
                layout["x"] = max_x
                changed = True

    return new_widgets, changed


def sanitize_dashboard_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """Return a sanitized copy of the dashboard body suitable for the Datadog API.

    Removes deprecated keys and ensures compatibility with the current Datadog
    Dashboards API. The sanitizer walks the body recursively and strips any
    deprecated keys found in nested dictionaries or lists.

    Args:
        body: Dictionary containing dashboard configuration data

    Returns:
        A new dictionary with deprecated keys removed, safe for API submission
    """
    def _recursive_cleanse(obj):
        """Recursively remove deprecated keys from nested structures."""
        if isinstance(obj, dict):
            to_remove = [k for k in obj.keys() if k in DEPRECATED_KEYS]
            for k in to_remove:
                obj.pop(k, None)

            for k, v in list(obj.items()):
                obj[k] = _recursive_cleanse(v)
            return obj

        elif isinstance(obj, list):
            return [_recursive_cleanse(item) for item in obj]
        else:
            return obj

    sanitized = deepcopy(body)
    sanitized = _recursive_cleanse(sanitized)
    return sanitized


def validate_dashboard_id_format(dashboard_id: str) -> bool:
    """Return True when a dashboard id looks like a valid Datadog dashboard id.

    This is a light-weight heuristic to catch obvious typos such as passing an
    option ("-y") or a filename instead of an id. It verifies that the id is
    a non-empty string composed of alphanumeric segments separated by
    hyphens, e.g. "59i-vd3-sqh" or "id-123".

    It's intentionally permissive; the function returns False only for strings
    that clearly don't match the expected id form.
    """
    if not isinstance(dashboard_id, str) or not dashboard_id:
        return False

    # Reject option-like strings e.g. "-y"
    if dashboard_id.startswith("-"):
        return False

    # Expect at least one hyphen-separated segment pair: abc-123 (one hyphen)
    # Each segment must be alphanumeric.
    pattern = re.compile(r'^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$')
    return bool(pattern.match(dashboard_id))
