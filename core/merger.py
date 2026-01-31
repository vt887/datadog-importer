"""Template merging logic for combining multiple dashboard templates."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from helper import load_template_file, verbose_print, ensure_layout


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

    Heuristics:
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
        return_summary: If True, return (merged, added_summary) instead of merged dict.

    Returns:
        New dictionary representing merged dashboard template, or tuple with summary.
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
            pass

    # Track detailed additions for improved logging
    added_summary = {
        "groups": {},
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

        # Determine target group for this descendant
        target_group_key = None
        title = (tpl.get("title") or "")
        parts = [s.strip() for s in title.split(" - ") if s.strip()]
        if len(parts) >= 2:
            target_group_key = _norm(parts[1])

        if not target_group_key:
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
                gdef.setdefault("widgets", []).append(w)
                file_titles.append(_widget_title(w))

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

    # Expanded verbose summary
    if verbose:
        try:
            verbose_print("Merge summary:", True)
            for gk, info in added_summary["groups"].items():
                gtitle = info.get("group_title") or gk
                total = info.get("total", 0)
                verbose_print(f"  Group: {gtitle} — added {total} widget(s)", True)
                for fname, titles in info.get("files", {}).items():
                    verbose_print(f"    from file: {fname} ({len(titles)} widgets)", True)
                    for t in titles:
                        verbose_print(f"      - {t}", True)

            top = added_summary["top_level"]
            if top.get("total", 0):
                verbose_print(f"  Top-level (no matching group) — added {top.get('total')} widget(s)", True)
                for fname, titles in top.get("files", {}).items():
                    verbose_print(f"    from file: {fname} ({len(titles)} widgets)", True)
                    for t in titles:
                        verbose_print(f"      - {t}", True)
        except Exception:
            pass

    if return_summary:
        return merged, added_summary
    return merged

