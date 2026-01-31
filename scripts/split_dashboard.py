#!/usr/bin/env python3
"""Split a Datadog dashboard template into multiple JSON files.

Creates one file per top-level widget, or if --split-groups is used will
split group widgets into separate files per inner widget.

Usage:
    python scripts/split_dashboard.py templates/backup_file.json --out-dir templates/split --split-groups
"""

from pathlib import Path
import argparse
import json
import copy
import sys

# Ensure the repository root is on sys.path so we can import helper when
# running this script from the repo root (script lives under scripts/).
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from helper import sanitize_dashboard_body, generate_template_filename, load_template_file


def _safe_widget_title(defn: dict, idx: int) -> str:
    t = defn.get("title") or defn.get("name") or defn.get("type")
    if not t:
        return f"widget_{idx}"
    return t


def build_dashboard_for_widget(base_template: dict, widget: dict, new_title: str) -> dict:
    """Return a dashboard dict for a single widget.

    The returned dashboard will include a single widget in the top-level
    `widgets` array. The widget layout x/y will be reset to 0/0 so it
    renders properly in a single-widget dashboard, but width/height are
    preserved (or defaulted) so the visual size is kept.
    """
    tpl = {
        "title": new_title,
        "description": base_template.get("description", ""),
        "widgets": [],
        "layout_type": base_template.get("layout_type", "ordered"),
    }

    w = copy.deepcopy(widget)
    layout = w.get("layout", {})
    # reset x/y for standalone widget
    layout["x"] = 0
    layout["y"] = 0
    # ensure width/height exist
    layout.setdefault("width", 12)
    layout.setdefault("height", 8)
    w["layout"] = layout

    tpl["widgets"] = [w]
    return sanitize_dashboard_body(tpl)


def split_dashboard_file(path: Path, out_dir: Path, split_groups: bool = False, verbose: bool = False) -> list:
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base = load_template_file(path)
    widgets = base.get("widgets", [])
    produced = []

    for idx, top_w in enumerate(widgets):
        defn = top_w.get("definition", {})
        wtype = defn.get("type")
        # Group widget: may have nested widgets under definition.widgets
        if wtype == "group" and split_groups:
            group_title = defn.get("title") or f"group_{idx}"
            inner_widgets = defn.get("widgets", [])
            for j, inner in enumerate(inner_widgets):
                inner_def = inner.get("definition", {})
                inner_title = _safe_widget_title(inner_def, j)
                new_title = f"{base.get('title','dashboard')} - {group_title} - {inner_title}"
                dashboard_obj = build_dashboard_for_widget(base, inner, new_title)
                fname = generate_template_filename(new_title)
                out_path = out_dir / fname
                with out_path.open("w", encoding="utf-8") as f:
                    json.dump(dashboard_obj, f, indent=2, ensure_ascii=False)
                produced.append(str(out_path))
                if verbose:
                    print(f"Wrote: {out_path}")
        else:
            # Top-level widget becomes its own dashboard
            top_title = defn.get("title") or f"{base.get('title','dashboard')}-widget-{idx}"
            new_title = f"{base.get('title','dashboard')} - {top_title}"
            dashboard_obj = build_dashboard_for_widget(base, top_w, new_title)
            fname = generate_template_filename(new_title)
            out_path = out_dir / fname
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(dashboard_obj, f, indent=2, ensure_ascii=False)
            produced.append(str(out_path))
            if verbose:
                print(f"Wrote: {out_path}")

    return produced


def _build_cli():
    p = argparse.ArgumentParser(description="Split a dashboard template into per-widget JSON files")
    p.add_argument("input", help="Path to dashboard JSON template")
    p.add_argument("--out-dir", default="templates/split", help="Output directory for split files")
    p.add_argument("--split-groups", action="store_true", help="If set, split 'group' widgets into their inner widgets")
    p.add_argument("--verbose", action="store_true")
    return p


def main():
    p = _build_cli()
    args = p.parse_args()
    produced = split_dashboard_file(args.input, args.out_dir, split_groups=args.split_groups, verbose=args.verbose)
    if args.verbose:
        print(f"Produced {len(produced)} files")
    else:
        for p in produced:
            print(p)


if __name__ == '__main__':
    main()
