#!/usr/bin/env python3
"""Split a dashboard JSON into a directory per top-level panel.

This script creates a directory named after the base dashboard title under
`--out-dir` (or `templates/<base_title>` by default) and writes one JSON file
per top-level panel. If a panel is a `group` widget, its inner widgets are
written as descendants in the panel directory; otherwise the top-level widget
is written as a descendant file.

Usage:
  python3 scripts/split_into_subdirs.py templates/backup_file.json

The script reuses helper functions from the repo and writes sanitized JSON
files suitable for the loader to discover and merge (loader supports
recursive discovery).
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

# Ensure repo root is on path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from helper import load_template_file, sanitize_dashboard_body, generate_template_filename


def safe_dir_name(s: str) -> str:
    s = s.strip()
    s = s.replace("/", "_")
    s = re.sub(r"[^A-Za-z0-9\-_ ]+", "", s)
    s = s.replace(" ", "_")
    return s.lower()


def write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def build_dashboard_for_widgets(base: dict, widgets: list, new_title: str) -> dict:
    tpl = {
        "title": new_title,
        "description": base.get("description", ""),
        "widgets": [],
        "layout_type": base.get("layout_type", "ordered"),
    }
    # deep-copy incoming widgets to avoid mutating original file
    tpl["widgets"] = [copy.deepcopy(w) for w in widgets]
    return sanitize_dashboard_body(tpl)


def split_into_subdirs(input_path: Path, out_dir: Path, split_groups: bool = False, verbose: bool = False):
    base = load_template_file(input_path)
    base_title = base.get("title") or input_path.stem
    base_dir = out_dir / safe_dir_name(base_title)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Write a root file that contains metadata and an empty widgets list.
    root_obj = {
        "title": base_title,
        "description": base.get("description", ""),
        "widgets": [],
        "layout_type": base.get("layout_type", "ordered"),
    }
    if base.get("template_variables"):
        root_obj["template_variables"] = base.get("template_variables")
    if base.get("notify_list"):
        root_obj["notify_list"] = base.get("notify_list")

    root_fname = generate_template_filename(base_title)
    write_json(base_dir / root_fname, sanitize_dashboard_body(root_obj))
    if verbose:
        print(f"Wrote root: {base_dir / root_fname}")

    widgets = base.get("widgets", [])
    for idx, top_w in enumerate(widgets):
        defn = top_w.get("definition", {})
        wtype = defn.get("type")
        panel_title = defn.get("title") or defn.get("name") or f"panel_{idx}"
        panel_dir = base_dir / safe_dir_name(panel_title)
        panel_dir.mkdir(parents=True, exist_ok=True)

        if wtype == "group":
            inner = defn.get("widgets", [])
            # If split_groups: write one file per inner widget; else bundle all inner widgets
            if split_groups:
                for j, inner_w in enumerate(inner):
                    inner_def = inner_w.get("definition", {})
                    inner_title = inner_def.get("title") or inner_def.get("name") or f"inner_{j}"
                    new_title = f"{base_title} - {panel_title} - {inner_title}"
                    obj = build_dashboard_for_widgets(base, [inner_w], new_title)
                    fname = generate_template_filename(new_title)
                    write_json(panel_dir / fname, obj)
                    if verbose:
                        print(f"Wrote inner widget: {panel_dir / fname}")
            else:
                new_title = f"{base_title} - {panel_title}"
                obj = build_dashboard_for_widgets(base, inner, new_title)
                fname = generate_template_filename(new_title)
                write_json(panel_dir / fname, obj)
                if verbose:
                    print(f"Wrote group panel: {panel_dir / fname}")
        else:
            # Non-group top-level widget becomes its own descendant file
            widget_title = defn.get("title") or f"widget_{idx}"
            new_title = f"{base_title} - {widget_title}"
            obj = build_dashboard_for_widgets(base, [top_w], new_title)
            fname = generate_template_filename(new_title)
            write_json(panel_dir / fname, obj)
            if verbose:
                print(f"Wrote top-level widget panel: {panel_dir / fname}")

    return base_dir


if __name__ == "__main__":
    p = argparse.ArgumentParser("Split dashboard into per-panel subdirectories")
    p.add_argument("input", help="Path to dashboard JSON template")
    p.add_argument("--out-dir", default="templates", help="Base output directory (default: templates)")
    p.add_argument("--split-groups", action="store_true",
                   help="Split group widgets into separate files per inner widget")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    out_base = Path(args.out_dir)
    input_path = Path(args.input)
    base_dir = split_into_subdirs(input_path, out_base, split_groups=args.split_groups, verbose=args.verbose)
    print(f"Split completed: {base_dir}")
