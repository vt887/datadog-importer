"""Data models for Datadog dashboard templates."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DashboardTemplate:
    """Represents a loaded dashboard template."""
    path: Path
    title: str
    widgets: List[Dict[str, Any]]
    description: str = ""
    layout_type: str = "ordered"
    template_variables: List[Dict[str, Any]] = field(default_factory=list)
    notify_list: List[Any] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)  # Original JSON

    @property
    def base_title(self) -> str:
        """Return the base title (part before ' - ')."""
        return self.title.split(" - ")[0].strip()


@dataclass
class MergeResult:
    """Result of merging multiple templates into one."""
    merged_dashboard: Dict[str, Any]
    groups_summary: Dict[str, Any]  # {"groups": {...}, "top_level": {...}}
    top_template_path: Path
    descendant_paths: List[Path] = field(default_factory=list)


@dataclass
class DeploymentTask:
    """A single dashboard deployment task."""
    template_path: Path
    dashboard_dict: Optional[Dict[str, Any]] = None  # None means load from file
    original_dict: Optional[Dict[str, Any]] = None  # For comparison
    is_merged: bool = False  # True if this task merged multiple files
    merge_result: Optional[MergeResult] = None


@dataclass
class DeploymentResult:
    """Result of deploying a single dashboard."""
    success: bool
    dashboard_id: Optional[str] = None
    dashboard_url: Optional[str] = None
    title: str = ""
    error_message: Optional[str] = None

