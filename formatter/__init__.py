"""Output formatting utilities for user-facing messages."""

from typing import Any, Dict, Optional


def print_merge_summary(merge_summary: Dict[str, Any], top_path_name: Optional[str] = None) -> None:
    """Print a concise, human-friendly merge summary.

    Format:
      Merged into: <top_path_name>
      Group: <Group Title>
      Widgets:
      - <widget title>
      ...

    Args:
        merge_summary: Dictionary with "groups" and "top_level" keys
        top_path_name: Optional name of the top-level template file
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
