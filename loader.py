"""Deploy Datadog dashboard JSON templates.

This module loads all ``*.json`` files from the ``templates/`` directory
and creates or updates Datadog dashboards using :class:`DatadogDashboardManager`.

Usage:
    python3 loader.py            # deploy all templates
    python3 loader.py --dry-run  # show what would be done without calling the API
"""

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional, Union, List, Dict
from datetime import datetime, timezone

from helper import (
    DatadogDashboardManager,
    resolve_selected_files,
    load_template_file,
    sanitize_dashboard_body,
    generate_dashboard_diff,
    verbose_print,
    print_http_info_from_response,
    print_http_info_from_exception,
    get_utc_date,
)
from core.merger import merge_templates, group_templates_by_base_title, choose_top_template
from core import validate_widgets, validate_dashboard_id_format
from formatter import print_merge_summary


def deploy_templates(
        templates_dir: Union[Path, str] = Path(__file__).parent / "templates",
        dry_run: bool = False,
        selected_files: Optional[Iterable[str]] = None,
        pattern: Optional[str] = None,
        verbose: bool = False,
        backup: bool = False,
) -> None:
    """Find and deploy JSON dashboard templates to Datadog.

    This is the main deployment function that orchestrates the entire process
    of discovering, validating, and deploying dashboard templates. It supports
    various modes including dry-run for safe testing and interactive confirmation.

    It now also automatically supports multi-file dashboards: if multiple
    templates share the same base title (prefix before " - ") they are merged
    into a single top-level dashboard and deployed as one.

    Args:
        templates_dir: Directory containing JSON template files (default: ./templates)
        dry_run: If True, only show planned actions without calling Datadog API
        selected_files: Optional list of specific files to deploy
        pattern: Optional glob pattern to select files (e.g., "monitoring_*.json")
        verbose: Enable detailed diagnostic output with timestamps
        backup: Create timestamped backups and persist sanitized templates to disk
    """
    import json as _json

    templates_dir = Path(templates_dir)
    pattern_matches = []

    if pattern:
        # Use recursive glob so patterns match files in subdirectories as well
        pattern_matches = sorted(templates_dir.rglob(pattern))
        verbose_print(f"Pattern '{pattern}' matched {len(pattern_matches)} files", verbose)

    selected_paths = resolve_selected_files(templates_dir, selected_files) if selected_files else []

    if selected_paths:
        template_files = sorted(selected_paths)
        verbose_print(f"Using {len(template_files)} explicitly selected files", verbose)
    elif pattern_matches:
        template_files = sorted(pattern_matches)
    else:
        # Discover templates recursively so nested template directories are supported
        template_files = sorted(templates_dir.rglob("*.json"))

    if not template_files:
        verbose_print(f"No JSON templates found in {templates_dir}", verbose)
        return

    # Group templates that likely belong to the same dashboard (split outputs)
    groups = group_templates_by_base_title(list(map(Path, template_files)))

    # Build a list of deployment tasks. Each task is (main_path, merged_template_or_None, original_template_or_None, is_merged_flag)
    template_iter = []

    for group in groups:
        if len(group) == 1:
            # Single-file dashboard: deploy normally
            template_iter.append((group[0], None, None, False))
            continue

        # Multi-file group: choose top template and descendants using helper
        try:
            top_path, top_template = choose_top_template(group)
        except Exception as exc:
            verbose_print(str(exc), verbose)
            # fallback: deploy each file separately
            for p in group:
                template_iter.append((p, None, None, False))
            continue

        # descendants are the other files in the group
        descendant_paths = [p for p in group if p != top_path]

        if verbose:
            verbose_print(f"Auto-merging {len(descendant_paths)} files into {Path(top_path).name}", True)

        # Request a summary so we can always report which groups and widgets were added
        merged_result = merge_templates(top_template, descendant_paths, stack=True, verbose=verbose, return_summary=True)
        if isinstance(merged_result, tuple):
            merged_template, merge_summary = merged_result
        else:
            merged_template = merged_result
            merge_summary = None

        # Print a concise, consistent merge summary using helper
        if merge_summary:
            try:
                print_merge_summary(merge_summary, Path(top_path).name)
            except Exception:
                # best-effort printing
                pass

        # register a single deployment task for the merged dashboard
        template_iter.append((top_path, merged_template, top_template.copy(), True))

    verbose_print(f"Processing {len(template_iter)} template grouping(s) from {templates_dir}", verbose)
    manager: Optional[DatadogDashboardManager] = None

    if verbose:
        verbose_print(f"Deployment session started: {get_utc_date()}", True)

    for template_path, preset_dashboard_template, preset_original_template, merged_flag in template_iter:
        verbose_print(f"Processing template: {Path(template_path).name}", verbose)

        try:
            if preset_dashboard_template is None:
                dashboard_template = load_template_file(Path(template_path))
            else:
                dashboard_template = preset_dashboard_template
        except Exception as exc:
            verbose_print(f"Failed to load template '{Path(template_path).name}': {exc}", verbose)
            continue

        title = dashboard_template.get("title")
        widgets = dashboard_template.get("widgets")

        if not title or widgets is None:
            verbose_print(f"Skipping '{Path(template_path).name}': missing required 'title' or 'widgets' fields", verbose)
            continue

        if preset_original_template is None:
            original_template = dashboard_template.copy()
        else:
            original_template = preset_original_template

        clamped_widgets, widgets_changed = validate_widgets(widgets, max_width=12)

        if widgets_changed:
            dashboard_template = dashboard_template.copy()
            dashboard_template["widgets"] = clamped_widgets

        if dry_run:
            diff = generate_dashboard_diff(original_template, dashboard_template)
            verbose_print(f"[DRY-RUN] Would deploy dashboard: '{title}' from {Path(template_path).name}", verbose)
            verbose_print(f"[DRY-RUN] Widget count: {len(widgets)}", verbose)

            if diff:
                verbose_print("[DRY-RUN] Template modifications applied:", verbose)
                verbose_print(diff, verbose)
            else:
                verbose_print("[DRY-RUN] No template modifications required", verbose)

            if backup:
                if merged_flag:
                    verbose_print(f"[DRY-RUN] Backup requested but skipped for merged template {Path(template_path).name} (dry-run mode)", verbose)
                else:
                    verbose_print(f"[DRY-RUN] Backup requested but skipped for {Path(template_path).name} (dry-run mode)", verbose)

            continue

        if manager is None:
            manager = DatadogDashboardManager()

        verbose_print(f"Deploying dashboard: {title}", verbose)

        try:
            dashboard_body = dict(dashboard_template)
            dashboard_body.setdefault("title", title)
            dashboard_body.setdefault("widgets", widgets)
            dashboard_body.setdefault("description", dashboard_template.get("description", ""))
            dashboard_body.setdefault("layout_type", dashboard_template.get("layout_type", "ordered"))
            dashboard_body = sanitize_dashboard_body(dashboard_body)

            if backup and not merged_flag:
                if dry_run:
                    verbose_print(f"[DRY-RUN] Would persist sanitized template for {Path(template_path).name}", verbose)
                else:
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    backup_filename = f"{Path(template_path).name}.bak.{timestamp}"
                    backup_path = Path(template_path).with_name(backup_filename)

                    try:
                        with backup_path.open("w", encoding="utf-8") as backup_file:
                            backup_file.write(_json.dumps(original_template, indent=2, ensure_ascii=False))

                        with Path(template_path).open("w", encoding="utf-8") as template_file:
                            template_file.write(_json.dumps(dashboard_body, indent=2, ensure_ascii=False))

                        verbose_print(f"Template sanitized and backed up: {Path(template_path).name} -> {backup_filename}", verbose)
                        verbose_print(f"Backup timestamp: {timestamp}", verbose)
                    except Exception as backup_exc:
                        verbose_print(f"Failed to create backup for {Path(template_path).name}: {backup_exc}", verbose)

            if backup and merged_flag:
                if dry_run:
                    verbose_print(f"[DRY-RUN] Would persist merged sanitized template for {Path(template_path).name}", verbose)
                else:
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    backup_filename = f"{Path(template_path).name}.bak.{timestamp}"
                    backup_path = Path(template_path).with_name(backup_filename)
                    try:
                        with backup_path.open("w", encoding="utf-8") as backup_file:
                            backup_file.write(_json.dumps(original_template, indent=2, ensure_ascii=False))

                        with Path(template_path).open("w", encoding="utf-8") as template_file:
                            template_file.write(_json.dumps(dashboard_body, indent=2, ensure_ascii=False))

                        verbose_print(f"Merged template persisted and backed up: {Path(template_path).name} -> {backup_filename}", verbose)
                        verbose_print(f"Backup timestamp: {timestamp}", verbose)
                    except Exception as backup_exc:
                        verbose_print(f"Failed to create merged backup for {Path(template_path).name}: {backup_exc}", verbose)

            extra_kwargs = {k: v for k, v in dashboard_body.items() if k not in ("title", "description", "widgets", "layout_type")}

            response = manager.create_or_update(
                title=dashboard_body.get("title"),
                description=dashboard_body.get("description", ""),
                widgets=dashboard_body.get("widgets", []),
                layout_type=dashboard_body.get("layout_type", "ordered"),
                **extra_kwargs,
            )

            dashboard_url = None
            if isinstance(response, dict):
                dashboard_url = response.get("url")
            else:
                dashboard_url = getattr(response, "url", None)

            verbose_print(f"Dashboard deployed successfully: {dashboard_url}", verbose)

            if verbose:
                try:
                    print_http_info_from_response(response, verbose=True)
                except Exception:
                    pass

        except Exception as deploy_exc:
            verbose_print(f"Deployment failed for '{Path(template_path).name}': {deploy_exc}", verbose)
            if verbose:
                try:
                    print_http_info_from_exception(deploy_exc, verbose=True)
                except Exception:
                    # Best-effort error logging
                    pass


def _build_cli() -> argparse.ArgumentParser:
    """Build and configure the command-line argument parser.

    Creates an ArgumentParser with all supported options for dashboard deployment,
    including file selection, deployment modes, and configuration options.

    Returns:
        Configured ArgumentParser ready for parse_args() calls
    """
    parser = argparse.ArgumentParser(
        description="Deploy Datadog dashboard JSON templates",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    selection_group = parser.add_argument_group('Template selection')
    selection_group.add_argument(
        "--templates-dir", "-d",
        default=Path(__file__).parent / "templates",
        type=Path,
        help="Directory with JSON template files"
    )
    selection_group.add_argument(
        "--files", "-f",
        nargs="+",
        help="Specific template files to deploy (relative to templates dir or absolute)"
    )
    selection_group.add_argument(
        "--pattern", "-p",
        default="*.json",
        help="Glob pattern to select files inside templates dir (e.g., monitoring_*.json')"
    )

    mode_group = parser.add_argument_group('Deployment modes')
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned actions without calling Datadog API (safe preview mode)"
    )
    mode_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed diagnostic output with timestamps and HTTP info"
    )
    mode_group.add_argument(
        "--backup", "-b",
        action="store_true",
        help="Create timestamped backups (.bak.<timestamp>) and persist templates locally"
    )
    mode_group.add_argument(
        "--list", "-l",
        action="store_true",
        help="List already deployed dashboards"
    )
    mode_group.add_argument(
        "--delete", "-D",
        metavar="DASHBOARD_ID",
        action="append",
        help="Delete dashboard by id or title (can be specified multiple times).",
    )
    mode_group.add_argument(
        "--force", "-y",
        action="store_true",
        help="Bypass confirmation prompt for destructive operations like --delete.",
    )
    return parser


def main():
    """Main entry point for the deployment script.

    Handles command-line parsing and orchestrates the deployment process.
    This function is called when the script is executed directly.
    """
    parser = _build_cli()
    args = parser.parse_args()

    templates_dir = Path(args.templates_dir)
    selected_files = args.files if args.files else None

    if args.list:
        try:
            mgr = DatadogDashboardManager()
            resp = mgr.list_dashboards()
            try:
                if isinstance(resp, dict):
                    print(json.dumps(resp, indent=2, ensure_ascii=False))
                elif hasattr(resp, "to_dict"):
                    print(json.dumps(resp.to_dict(), indent=2, ensure_ascii=False))
                else:
                    # Fallback: print repr
                    print(repr(resp))
            except Exception:
                print(repr(resp))

            if args.verbose:
                try:
                    print_http_info_from_response(resp, verbose=True)
                except Exception:
                    pass
            return
        except Exception as exc:
            print(f"Failed to list dashboards: {exc}")
            if args.verbose:
                try:
                    print_http_info_from_exception(exc, verbose=True)
                except Exception:
                    pass
            return

    if args.delete:
        targets = args.delete
        try:
            mgr = DatadogDashboardManager()
        except Exception as exc:
            print(f"Failed to initialize Datadog client: {exc}")
            if args.verbose:
                try:
                    print_http_info_from_exception(exc, verbose=True)
                except Exception:
                    pass
            return

        # Iterate and handle each delete target (each target must be an explicit dashboard ID)
        for target in targets:
            if not target:
                print("Delete target must be a dashboard id; please specify an ID after -D")
                continue
            if isinstance(target, str) and target.startswith("-"):
                print(f"Invalid delete target '{target}': expected a dashboard id (you likely passed an option like '-y' immediately after -D). Use: -D <DASHBOARD_ID> -D <OTHER_ID> -y to force.")
                return

            # Heuristic check: warn if the id does not look like a typical dashboard id
            if not validate_dashboard_id_format(target):
                msg = (
                    f"Warning: delete target '{target}' does not match expected dashboard id format. "
                    "This may be a typo."
                )
                print(msg)
                if not args.force:
                    try:
                        answer = input("Type 'yes' to proceed with this id, anything else to skip: ")
                    except EOFError:
                        print("No input available; aborting deletion.")
                        return

                    if answer.strip().lower() not in ("y", "yes"):
                        print("Aborted by user.")
                        continue

            # Require an explicit dashboard id for deletion. Use get_dashboard(id)
            try:
                dashboard_obj = mgr.get_dashboard(target)
            except Exception:
                print(f"No dashboard found with id '{target}'")
                continue

            dashboard_id = target
            dashboard_title = None
            if isinstance(dashboard_obj, dict):
                dashboard_title = dashboard_obj.get("title")
            else:
                dashboard_title = getattr(dashboard_obj, "title", None)

            # Dry-run: print what would be deleted and continue
            if args.dry_run:
                print(f"[DRY-RUN] Would delete dashboard: {dashboard_title or '<unknown title>'} (id={dashboard_id})")
                if args.verbose:
                    try:
                        print(mgr.format_dashboard(dashboard_obj))
                    except Exception:
                        pass
                continue

            # Prompt per-target unless --force was supplied
            if not args.force:
                try:
                    answer = input(f"Are you sure you want to delete dashboard '{dashboard_title or dashboard_id}' (id={dashboard_id})? Type 'yes' to confirm: ")
                except EOFError:
                    print("No input available; aborting deletion.")
                    return

                if answer.strip().lower() not in ("y", "yes"):
                    print("Aborted by user.")
                    continue

            # Perform deletion
            try:
                resp = mgr.delete_dashboard(dashboard_id)
                print(f"Deleted dashboard: {dashboard_title or dashboard_id} (id={dashboard_id})")
                if args.verbose:
                    try:
                        print_http_info_from_response(resp, verbose=True)
                    except Exception:
                        pass
            except Exception as exc:
                print(f"Failed to delete dashboard {dashboard_id}: {exc}")
                if args.verbose:
                    try:
                        print_http_info_from_exception(exc, verbose=True)
                    except Exception:
                        pass

        return

    deploy_templates(
        templates_dir=templates_dir,
        dry_run=args.dry_run,
        selected_files=selected_files,
        pattern=args.pattern,
        verbose=args.verbose,
        backup=args.backup,
    )


if __name__ == "__main__":
    main()
