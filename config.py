"""Configuration and constants for Datadog importer."""

from pathlib import Path

# Directories
TEMPLATES_DIR_DEFAULT = Path(__file__).parent / "templates"

# Dashboard settings
DASHBOARD_GRID_WIDTH = 12
DASHBOARD_LAYOUT_TYPE_DEFAULT = "ordered"

# Validation & sanitization
DEPRECATED_KEYS = {"is_read_only", "display"}

# Selection heuristics for top-level template
TOP_TEMPLATE_PRIORITY_ROOT_FLAG = 0  # Highest: is_root/top_level/root
TOP_TEMPLATE_PRIORITY_TITLE_MATCH = 1  # Second: title matches base title
TOP_TEMPLATE_PRIORITY_WIDGET_COUNT = 2  # Third: widget count (higher is better)
TOP_TEMPLATE_PRIORITY_FALLBACK = 99  # Lowest: load error

# Output formatting
VERBOSE_LOG_PREFIX_FORMAT = "[{time}] {message}"
