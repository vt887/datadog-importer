"""Datadog dashboard manager utilities.

This module provides utilities and helper classes for managing Datadog dashboards,
including validation, sanitization, HTTP response handling, and time utilities.
"""

import os
import importlib
import json
import difflib
import json as _json
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from typing import List, Dict, Optional, Iterable, Any, Tuple, Union


# Public API exported by this module
__all__ = [
    "resolve_selected_files",
    "load_template_file",
    "sanitize_dashboard_body",
    "generate_dashboard_diff",
    "verbose_print",
    "print_http_info_from_response",
    "print_http_info_from_exception",
    "get_utc_date",
    "ensure_layout",
]


class DatadogDashboardManager:
    """Manage Datadog dashboards.

    The manager wraps a Datadog ApiClient and exposes convenience methods
    to find, create, and update dashboards by title.
    """

    def __init__(self, api_key: Optional[str] = None, app_key: Optional[str] = None):
        """Initialize the Datadog client.

        If `api_key` or `app_key` are not provided they will be read from the
        DATADOG_API_KEY and DATADOG_APP_KEY environment variables.

        Raises:
            RuntimeError: if no API key can be found or the datadog client
                package is not installed.
        """
        api_key = api_key or os.getenv("DATADOG_API_KEY")
        app_key = app_key or os.getenv("DATADOG_APP_KEY")

        if not api_key:
            raise RuntimeError("DATADOG_API_KEY is required")

        try:
            datadog_mod = importlib.import_module("datadog_api_client")
            dashboards_mod = importlib.import_module("datadog_api_client.v1.api.dashboards_api")
            ApiClient = getattr(datadog_mod, "ApiClient")
            Configuration = getattr(datadog_mod, "Configuration")
            DashboardsApi = getattr(dashboards_mod, "DashboardsApi")
        except Exception as exc:  # pragma: no cover - runtime environment specific
            raise RuntimeError(
                "The 'datadog_api_client' package is required. "
                "Install it with: pip install datadog-api-client"
            ) from exc

        cfg = Configuration()
        cfg.api_key["apiKeyAuth"] = api_key

        if app_key:
            cfg.api_key["appKeyAuth"] = app_key

        self._client = ApiClient(cfg)
        self._api = DashboardsApi(self._client)

    def _find_dashboard_by_title(self, title: str) -> Optional[Dict]:
        """Return a dashboard summary matching ``title`` or ``None``.

        The method uses the Dashboards API list endpoint which returns a
        summary for each dashboard. We iterate the returned items and match
        by title.
        """
        resp = self._api.list_dashboards()
        for item in (resp.get("dashboards") or []):
            if item.get("title") == title:
                return item
        return None

    def create_dashboard(self, title: Optional[str] = None, widgets: Optional[List[Dict]] = None, description: str = "",
                         layout_type: str = "ordered", **extra) -> Dict:
        """Create a new dashboard.

        The method accepts either explicit parameters (title, widgets, ...)
        or arbitrary extra keyword arguments which will be included in the
        request body. This keeps the API flexible and allows the loader to
        pass through keys such as `template_variables`.
        """
        body = dict(extra) if extra else {}

        if not body:
            body = {
                "title": title,
                "description": description,
                "widgets": widgets,
                "layout_type": layout_type,
            }
        else:
            if title is not None:
                body.setdefault("title", title)
            if widgets is not None:
                body.setdefault("widgets", widgets)
            body.setdefault("description", description)
            body.setdefault("layout_type", layout_type)
        return self._api.create_dashboard(body=body)

    def update_dashboard(self, dashboard_id: str, body: Dict) -> Dict:
        """Update an existing dashboard using a full request body.

        Args:
            dashboard_id: The id of the dashboard to update.
            body: Full dashboard body to send to the API.

        Returns:
            The API response for the updated dashboard.
        """
        return self._api.update_dashboard(dashboard_id=dashboard_id, body=body)

    def create_or_update(self, **body) -> Dict:
        """Create or update a dashboard using the provided body dict.

        The body should include at least a `title` key so we can attempt to
        find an existing dashboard. If an existing dashboard is found we call
        update_dashboard(dashboard_id, body), otherwise we call
        create_dashboard with the body.
        """
        title = body.get("title")
        if not title:
            raise ValueError("Dashboard body must include a 'title' key")

        existing = self._find_dashboard_by_title(title)

        if existing:
            dashboard_id = existing["id"]
            print(f"Updating existing dashboard (id={dashboard_id})")
            return self.update_dashboard(dashboard_id, body)
        else:
            print("Creating new dashboard")
            return self.create_dashboard(**body)

    def list_dashboards(self) -> Dict:
        """Return the list of dashboards via the Dashboards API."""
        return self._api.list_dashboards()

    def delete_dashboard(self, dashboard_id: str) -> Dict:
        """Delete a dashboard by id.

        Args:
            dashboard_id: The id of the dashboard to delete.

        Returns:
            The API response for the delete operation.
        """
        return self._api.delete_dashboard(dashboard_id=dashboard_id)

    def get_dashboard(self, dashboard_id: str) -> Dict:
        """Retrieve a full dashboard by id.

        Args:
            dashboard_id: The id of the dashboard to retrieve.

        Returns:
            The dashboard body as returned by the API.
        """
        return self._api.get_dashboard(dashboard_id=dashboard_id)

    def find_dashboard_by_title(self, title: str) -> Optional[Dict]:
        """Public wrapper around internal title lookup.

        Returns a dashboard summary dict when a matching title is found, or
        None when no match exists.
        """
        return self._find_dashboard_by_title(title)

    def resolve_dashboard(self, target: str) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
        """Resolve a user-supplied target to a dashboard id and title.

        The target may be either a dashboard id or an exact dashboard title.
        The method attempts to GET the dashboard by id first; on failure it
        falls back to search by title using the dashboards list endpoint.

        Returns:
            (dashboard_id, title, dashboard_obj_or_None)
        """
        # Try as an id (GET dashboard)
        try:
            obj = self.get_dashboard(target)
            # obj may be dict-like or an API object
            if isinstance(obj, dict):
                title = obj.get("title")
            else:
                title = getattr(obj, "title", None)
            return target, title, obj
        except Exception:
            pass

        # Fallback: exact title match via list lookup
        try:
            found = self._find_dashboard_by_title(target)
        except Exception:
            found = None

        if not found:
            return None, None, None

        dashboard_id = found.get("id")
        dashboard_title = found.get("title")
        # Try to fetch full dashboard object if possible
        try:
            obj = self.get_dashboard(dashboard_id)
        except Exception:
            obj = None

        return dashboard_id, dashboard_title, obj

    def format_dashboard(self, dashboard_obj: Optional[Dict]) -> str:
        """Return a pretty-printed JSON string for a dashboard object.

        This is a best-effort formatter that accepts dict-like API responses or
        objects implementing `to_dict()` and returns a compact JSON string.
        """
        if dashboard_obj is None:
            return "<no dashboard details available>"

        try:
            if isinstance(dashboard_obj, dict):
                return _json.dumps(dashboard_obj, indent=2, ensure_ascii=False)
            if hasattr(dashboard_obj, "to_dict"):
                try:
                    return _json.dumps(dashboard_obj.to_dict(), indent=2, ensure_ascii=False)
                except Exception:
                    pass
            # Fallback to repr
            return repr(dashboard_obj)
        except Exception:
            return repr(dashboard_obj)


def validate_widgets(widgets: Iterable[Dict[str, Any]], max_width: int = 12) -> Tuple[List[Dict[str, Any]], bool]:
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
    # Treat certain presentation keys as deprecated/unsupported by the API
    # and remove them before sending the payload. 'display' was causing
    # API validation errors (unsupported additional property on group widgets).
    deprecated_keys = {"is_read_only", "display"}

    def _recursive_cleanse(obj):
        """Recursively remove deprecated keys from nested structures."""
        if isinstance(obj, dict):
            to_remove = [k for k in obj.keys() if k in deprecated_keys]
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


def resolve_selected_files(templates_dir: Path, selections: Optional[Iterable[str]]) -> List[Path]:
    """Resolve user-supplied file names into absolute Paths.

    This utility function processes user-provided file selections and converts
    them to absolute Path objects, checking for existence and providing helpful
    warnings for missing files.

    Args:
        templates_dir: Base directory for template files
        selections: Optional iterable of file paths/names provided by user

    Returns:
        List of absolute Path objects that exist on disk
    """
    if not selections:
        return []

    resolved: List[Path] = []
    for selection in selections:
        path = Path(selection)

        if not path.is_absolute():
            path = templates_dir / path

        if not path.exists():
            print(f"Warning: selected file or directory '{selection}' does not exist (skipping)")
            continue

        # If a directory was supplied, expand it recursively to find JSON templates
        if path.is_dir():
            for p in sorted(path.rglob("*.json")):
                if p.exists():
                    resolved.append(p)
            continue

        # Otherwise append the explicit file path
        resolved.append(path)

    return resolved


def load_template_file(template_path: Path) -> Dict[str, Any]:
    """Load and parse a JSON template file.

    Args:
        template_path: Path to the JSON template file

    Returns:
        Parsed JSON dictionary containing dashboard template

    Raises:
        FileNotFoundError: If template file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
        UnicodeDecodeError: If file has encoding issues
    """
    try:
        with template_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        raise RuntimeError(f"Failed to load template '{template_path.name}': {exc}") from exc


def generate_dashboard_diff(original: Dict[str, Any], modified: Dict[str, Any]) -> str:
    """Generate a unified diff showing differences between dashboard templates.

    Args:
        original: Original dashboard template
        modified: Modified dashboard template

    Returns:
        String containing unified diff in standard format
    """
    before = _json.dumps(original, indent=2, sort_keys=True)
    after = _json.dumps(modified, indent=2, sort_keys=True)

    return "\n".join(difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        lineterm=""
    ))


def get_short_utc_time() -> str:
    """Return a short UTC time string with millisecond precision.

    Format: HH:MM:SS.mmm (e.g., "12:07:48.856")
    Useful for timestamping log messages in verbose mode.

    Returns:
        Formatted time string or fallback if formatting fails
    """
    try:
        now = datetime.now(timezone.utc)
        milliseconds = int(now.microsecond / 1000)
        return f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}.{milliseconds:03d}"
    except Exception:
        return "--:--:--.---"


def get_utc_date() -> str:
    """Return the current UTC date as a short string.

    Format: YYYY-MM-DD (e.g., "2025-10-28")
    Useful for logging session dates in verbose output.

    Returns:
        Formatted date string or fallback if formatting fails
    """
    try:
        return datetime.now(timezone.utc).date().isoformat()
    except Exception:
        return "----:--:--"


def verbose_print(message: str, verbose: bool = False):
    """Verbose-aware print utility with timestamp prefixing.

    When verbose mode is enabled, each line is prefixed with a timestamp.
    This provides a consistent logging format for debugging and monitoring.

    Args:
        message: Message to print
        verbose: Whether to include timestamp prefix
    """
    text = str(message)
    if not verbose:
        print(text)
        return

    for line in text.splitlines() or [""]:
        print(f"[{get_short_utc_time()}] {line}")


def extract_http_info_from_exception(exc: Exception) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    """Extract headers and body from an exception if available (best-effort).

    This function attempts to extract HTTP-related information from various
    exception types that might be raised by the Datadog API client.

    Args:
        exc: Exception object possibly containing HTTP response information

    Returns:
        Tuple (headers, body) where each may be None if not found
    """
    headers = None
    body = None

    http_resp = getattr(exc, "http_resp", None)
    if http_resp is not None:
        if hasattr(http_resp, "headers"):
            headers = getattr(http_resp, "headers")
        elif hasattr(http_resp, "getheaders"):
            try:
                headers = dict(http_resp.getheaders())
            except Exception:
                headers = http_resp.getheaders()

        if hasattr(http_resp, "data"):
            body = getattr(http_resp, "data")
        elif hasattr(http_resp, "text"):
            body = getattr(http_resp, "text")
        elif hasattr(http_resp, "read"):
            try:
                body = http_resp.read()
            except Exception:
                body = None

    if body is None:
        body = getattr(exc, "body", None) or getattr(exc, "error", None)
    if headers is None:
        headers = getattr(exc, "headers", None)

    return headers, body


def extract_http_info_from_response(resp: Any) -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    """Extract headers and body from a response object (best-effort).

    Handles various response object types that might be returned by the
    Datadog API client, supporting both dictionary and object-based responses.

    Args:
        resp: Response object (dict, API response object, or None)

    Returns:
        Tuple (headers, body) extracted from the response
    """
    headers = None
    body = None

    if resp is None:
        return None, None

    if isinstance(resp, dict):
        headers = resp.get("headers") or resp.get("http_headers") or resp.get("meta")
        body = resp.get("body") or resp.get("data") or resp.get("content")
        return headers, body

    if hasattr(resp, "headers"):
        headers = getattr(resp, "headers")
    elif hasattr(resp, "getheaders"):
        try:
            headers = dict(resp.getheaders())
        except Exception:
            headers = resp.getheaders()

    if hasattr(resp, "data"):
        body = getattr(resp, "data")
    elif hasattr(resp, "text"):
        body = getattr(resp, "text")
    elif hasattr(resp, "to_dict"):
        try:
            body = resp.to_dict()
        except Exception:
            body = None

    return headers, body


def pretty_print_http_info(headers: Optional[Dict[str, Any]], body: Any, verbose: bool = False) -> None:
    """Pretty-print HTTP headers and body to stdout (best-effort).

    This utility function formats HTTP response information for human-readable
    display, handling various data types and encodings.

    Args:
        headers: HTTP headers (dict-like or None)
        body: HTTP response body (string, bytes, dict, or None)
        verbose: Whether to prefix output with timestamps
    """
    import pprint

    if headers is not None:
        verbose_print("HTTP response headers:", verbose)
        try:
            s = pprint.pformat(headers)
            verbose_print(s, verbose)
        except Exception:
            verbose_print(str(headers), verbose)

    if body is not None:
        verbose_print("HTTP response body:", verbose)

        try:
            if isinstance(body, (bytes, bytearray)):
                try:
                    body_text = body.decode()
                except Exception:
                    body_text = str(body)
            else:
                body_text = body

            if isinstance(body_text, str):
                try:
                    parsed = json.loads(body_text)
                    s = pprint.pformat(parsed)
                    verbose_print(s, verbose)
                except Exception:
                    verbose_print(body_text, verbose)
            else:
                s = pprint.pformat(body_text)
                verbose_print(s, verbose)
        except Exception:
            verbose_print(repr(body), verbose)


def print_http_info_from_exception(exc: Exception, verbose: bool = False) -> None:
    """Convenience function to print HTTP info from an exception.

    Args:
        exc: Exception object containing HTTP information
        verbose: Whether to include timestamps in output
    """
    headers, body = extract_http_info_from_exception(exc)
    pretty_print_http_info(headers, body, verbose=verbose)


def print_http_info_from_response(resp: Any, verbose: bool = False) -> None:
    """Convenience function to print HTTP info from a response.

    Args:
        resp: Response object containing HTTP information
        verbose: Whether to include timestamps in output
    """
    headers, body = extract_http_info_from_response(resp)
    pretty_print_http_info(headers, body, verbose=verbose)


def generate_template_filename(title: str, suffix: str = "") -> str:
    """Generate a safe filename from a dashboard title.

    Creates a filesystem-safe filename by converting the dashboard title to
    lowercase, replacing spaces with underscores, and removing special characters.

    Args:
        title: Dashboard title to convert to filename
        suffix: Optional suffix to append (e.g., '.json')

    Returns:
        Safe filename string suitable for template files
    """
    import re

    safe_title = re.sub(r'[^a-zA-Z0-9]+', '_', title.lower())
    safe_title = safe_title.strip('_')  # Remove leading/trailing underscores

    if not safe_title or safe_title.startswith('.'):
        safe_title = f"dashboard_{safe_title or 'template'}"

    if not suffix:
        suffix = ".json"
    elif not suffix.startswith('.'):
        suffix = f".{suffix}"

    return f"{safe_title}{suffix}"


def ensure_layout(widget: Dict) -> Dict:
    """Ensure a widget has a layout dict with sane defaults.

    This helper will create a "layout" mapping on the widget when missing and
    ensure it contains x,y,width,height keys with default values compatible
    with Datadog's dashboard grid.
    """
    layout = widget.setdefault("layout", {})
    layout.setdefault("x", 0)
    layout.setdefault("y", 0)
    layout.setdefault("width", 12)
    layout.setdefault("height", 8)
    return layout


def validate_dashboard_id_format(dashboard_id: str) -> bool:
    """Return True when a dashboard id looks like a valid Datadog dashboard id.

    This is a light-weight heuristic to catch obvious typos such as passing an
    option ("-y") or a filename instead of an id. It verifies that the id is
    a non-empty string composed of alphanumeric segments separated by
    hyphens, e.g. "59i-vd3-sqh" or "id-123".

    It's intentionally permissive; the function returns False only for strings
    that clearly don't match the expected id form.
    """
    import re

    if not isinstance(dashboard_id, str) or not dashboard_id:
        return False

    # Reject option-like strings e.g. "-y"
    if dashboard_id.startswith("-"):
        return False

    # Expect at least one hyphen-separated segment pair: abc-123 (one hyphen)
    # Each segment must be alphanumeric.
    pattern = re.compile(r'^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$')
    return bool(pattern.match(dashboard_id))


def merge_templates(top_tpl: Dict, descendant_paths: List[Path], stack: bool = True, verbose: bool = False, return_summary: bool = False) -> Union[Dict, Tuple[Dict, Dict]]:
    """Merge widgets and template-level fields from descendant templates.

    - Appends widgets from each descendant into ``top_tpl['widgets']``.
    - If ``stack`` is True, incoming widgets' y positions are shifted so
      they don't overlap with previously merged widgets.
    - Merges template-level fields like ``template_variables``, ``notify_list``
      and ``time`` from descendants when not already present.

    Args:
        top_tpl: Dictionary loaded from the top-level JSON template file.
        descendant_paths: List of Path objects pointing to descendant JSON files.
        stack: Whether to vertically stack incoming widgets beneath existing ones.
        verbose: If True, prints diagnostics using ``verbose_print``.

    Returns:
        New dictionary representing merged dashboard template.
    """
    merged = dict(top_tpl)
    merged_widgets = list(merged.get("widgets", []) or [])

    merged_template_vars = list(merged.get("template_variables") or [])
    merged_notify_list = list(merged.get("notify_list") or [])
    merged_time = merged.get("time")

    # compute initial y offset from top template
    max_bottom = 0
    for w in merged_widgets:
        layout = ensure_layout(w)
        bottom = layout.get("y", 0) + layout.get("height", 0)
        if bottom > max_bottom:
            max_bottom = bottom
    current_y_offset = max_bottom + 1 if stack else 0

    # Build a mapping of group titles (normalized) -> group definition dict and per-group y offsets
    import re

    def _norm(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', (s or "").lower())

    group_map: Dict[str, Dict] = {}
    # Discover group widgets inside the top-level template and prepare offsets
    for w in merged_widgets:
        try:
            defn = w.get("definition", {})
            if isinstance(defn, dict) and defn.get("type") == "group":
                g_title = (defn.get("title") or "").strip()
                key = _norm(g_title)
                # compute current max bottom inside group
                g_widgets = defn.get("widgets") or []
                g_max = 0
                for gw in g_widgets:
                    gl = ensure_layout(gw)
                    g_bottom = gl.get("y", 0) + gl.get("height", 0)
                    if g_bottom > g_max:
                        g_max = g_bottom
                group_map[key] = {
                    "defn": defn,
                    "current_y_offset": (g_max + 1) if stack else 0,
                }
        except Exception:
            # best-effort: ignore malformed group widgets
            pass

    # Track detailed additions for improved logging
    added_summary = {
        "groups": {},  # key -> {group_title, files: {filename: [titles...]}, total}
        "top_level": {"files": {}, "total": 0},
    }

    def _widget_title(w: Dict) -> str:
        try:
            return (w.get("definition", {}) or {}).get("title") or w.get("title") or w.get("name") or "<unnamed>"
        except Exception:
            return "<unnamed>"

    for p in descendant_paths:
        try:
            tpl = load_template_file(p)
        except Exception:
            if verbose:
                verbose_print(f"Failed to load descendant template: {p}", True)
            continue

        # merge collections
        for tv in tpl.get("template_variables") or []:
            if tv not in merged_template_vars:
                merged_template_vars.append(tv)
        for n in tpl.get("notify_list") or []:
            if n not in merged_notify_list:
                merged_notify_list.append(n)
        if merged_time is None and "time" in tpl:
            merged_time = tpl.get("time")

        incoming = list(tpl.get("widgets", []) or [])
        if not incoming:
            if verbose:
                verbose_print(f"Skipping descendant {p}: no widgets", verbose)
            continue

        # Determine target group for this descendant, prefer title-based mapping (second segment), fallback to parent dir name
        target_group_key = None
        title = (tpl.get("title") or "")
        parts = [s.strip() for s in title.split(" - ") if s.strip()]
        if len(parts) >= 2:
            target_group_key = _norm(parts[1])

        if not target_group_key:
            # use parent directory name
            try:
                parent_name = p.parent.name
                target_group_key = _norm(parent_name.replace("_", " "))
            except Exception:
                target_group_key = None

        incoming_max_bottom = 0

        if target_group_key and target_group_key in group_map:
            # merge into the group's definition.widgets
            grp = group_map[target_group_key]
            gdef = grp["defn"]
            g_offset = grp["current_y_offset"]

            file_titles: List[str] = []
            for w in incoming:
                layout = ensure_layout(w)
                if stack:
                    layout["y"] = layout.get("y", 0) + g_offset
                bottom = layout.get("y", 0) + layout.get("height", 0)
                if bottom > incoming_max_bottom:
                    incoming_max_bottom = bottom
                # append into group's widgets
                gdef.setdefault("widgets", []).append(w)
                # record title for logging
                file_titles.append(_widget_title(w))

            # update added_summary for this group/file
            gkey = target_group_key
            group_entry = added_summary["groups"].setdefault(gkey, {"group_title": gdef.get("title"), "files": {}, "total": 0})
            group_entry["files"].setdefault(Path(p).name, []).extend(file_titles)
            group_entry["total"] += len(file_titles)

            if stack:
                grp["current_y_offset"] = incoming_max_bottom + 1

            if verbose:
                verbose_print(f"Merged {len(incoming)} widgets from {p} into group '{gdef.get('title')}'", True)
        else:
            # No matching group found; fall back to top-level merge
            file_titles: List[str] = []
            for w in incoming:
                layout = ensure_layout(w)
                if stack:
                    layout["y"] = layout.get("y", 0) + current_y_offset
                bottom = layout.get("y", 0) + layout.get("height", 0)
                if bottom > incoming_max_bottom:
                    incoming_max_bottom = bottom
                file_titles.append(_widget_title(w))
            merged_widgets.extend(incoming)
            if stack:
                current_y_offset = incoming_max_bottom + 1

            # update top-level summary
            added_summary["top_level"]["files"].setdefault(Path(p).name, []).extend(file_titles)
            added_summary["top_level"]["total"] += len(file_titles)

            if verbose:
                verbose_print(f"Merged {len(incoming)} widgets from {p} into top-level (new total: {len(merged_widgets)})", True)

    merged["widgets"] = merged_widgets
    if merged_template_vars:
        merged["template_variables"] = merged_template_vars
    if merged_notify_list:
        merged["notify_list"] = merged_notify_list
    if merged_time is not None:
        merged["time"] = merged_time

    # Expanded verbose summary of additions grouped by target
    if verbose:
        try:
            verbose_print("Merge summary:", True)
            # groups
            for gk, info in added_summary["groups"].items():
                gtitle = info.get("group_title") or gk
                total = info.get("total", 0)
                verbose_print(f"  Group: {gtitle} — added {total} widget(s)", True)
                for fname, titles in info.get("files", {}).items():
                    verbose_print(f"    from file: {fname} ({len(titles)} widgets)", True)
                    for t in titles:
                        verbose_print(f"      - {t}", True)

            # top-level
            top = added_summary["top_level"]
            if top.get("total", 0):
                verbose_print(f"  Top-level (no matching group) — added {top.get('total')} widget(s)", True)
                for fname, titles in top.get("files", {}).items():
                    verbose_print(f"    from file: {fname} ({len(titles)} widgets)", True)
                    for t in titles:
                        verbose_print(f"      - {t}", True)
        except Exception:
            # best-effort logging; ignore failures in verbose reporting
            pass

    if return_summary:
        return merged, added_summary
    return merged


def group_templates_by_base_title(paths: List[Path]) -> List[List[Path]]:
    """Group template files that belong to the same dashboard by base title.

    Heuristic used:
    - Use the dashboard `title` from each template (fallback to filename stem).
    - The base title is the part before the first ' - '. Files sharing the same
      base title are considered part of the same (possibly split) dashboard.

    Returns:
        List of groups where each group is a list of Path objects.
    """
    groups: Dict[str, List[Path]] = {}
    for p in paths:
        try:
            tpl = load_template_file(p)
            title = tpl.get("title") or p.stem
        except Exception:
            title = p.stem
        base = title.split(" - ")[0]
        groups.setdefault(base, []).append(p)
    return list(groups.values())


def choose_top_template(candidate_paths: List[Path]) -> Tuple[Path, Dict[str, Any]]:
    """Decide which path in `candidate_paths` should act as the top-level template.

    Heuristics (same as loader):
      1) template that contains 'is_root'/'top_level'/'root' truthy
      2) template whose title equals the base title
      3) template with the most widgets

    Returns (top_path, loaded_template). Raises RuntimeError on irrecoverable failures.
    """
    base_candidates = []
    base_title = None

    for p in candidate_paths:
        try:
            tpl = load_template_file(p)
            title = tpl.get("title") or p.stem
            if base_title is None:
                base_title = title.split(" - ")[0]
            if tpl.get("is_root") or tpl.get("top_level") or tpl.get("root"):
                base_candidates.append((0, p, tpl))
            if title == base_title:
                base_candidates.append((1, p, tpl))
            widgets = tpl.get("widgets") or []
            base_candidates.append((2 + max(0, len(widgets)), p, tpl))
        except Exception:
            base_candidates.append((99, p, None))

    if not base_candidates:
        raise RuntimeError("No candidate templates provided")

    base_candidates.sort(key=lambda t: (t[0], - (len((t[2] or {}).get("widgets") or []))))
    top_path = base_candidates[0][1]
    try:
        top_tpl = load_template_file(top_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to load top-level template '{top_path.name}': {exc}") from exc

    return top_path, top_tpl


def print_merge_summary(merge_summary: Dict[str, Any], top_path_name: Optional[str] = None) -> None:
    """Print a concise, human-friendly merge summary.

    Format:
      Merged into: <top_path_name>
      Group: <Group Title>
      Widgets:
      - <widget title>
      ...

    This is intentionally simple so callers (like `loader.py`) can display
    the most important user-facing information.
    """
    if top_path_name:
        print(f"Merged into: {top_path_name}")

    groups = merge_summary.get("groups", {})
    for gk, info in groups.items():
        gtitle = info.get("group_title") or gk
        print(f"Group: {gtitle}")
        print("Widgets:")
        for fname, titles in info.get("files", {}).items():
            for t in titles:
                print(f"- {t}")

    top = merge_summary.get("top_level", {})
    if top.get("total", 0):
        print("Top-level Widgets:")
        for fname, titles in top.get("files", {}).items():
            for t in titles:
                print(f"- {t}")
