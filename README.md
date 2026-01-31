# datadog-importer — framework for Datadog dashboards

A framework to author, validate, merge, deploy, and delete Datadog dashboards using JSON templates. The framework is focused on reproducible, reviewable dashboard definitions and safe deployments to the Datadog API.

---

## Getting Started

1. **Understand the workflow** — Read the "Framework Workflow" section above
2. **JSON Template Best Practices** — Read the [JSON Template Best Practices](documentation/TEMPLATES_BEST_PRACTICES.md) document 
3. **Templates Best Practices** - Use [Quick Reference Guide](documentation/TEMPLATES_QUICK_REFERENCE.md) document for implementing best practices in JSON templates
4. **Review the architecture** — Check "Project Architecture" section
5. **Explore the code** — Start with `core/merger.py` or `loader.py`
6. **Run tests** — `pytest -q` should show 35 passing

---

## Quick Start

```bash
# Deploy all templates
python3 loader.py

# Preview changes without deploying
python3 loader.py --dry-run

# Delete a specific dashboard
python3 loader.py -D 59i-vd3-sqh

# Deploy with backups and verbose output
python3 loader.py --backup --verbose
```

---

## Core Concepts

**Template file** — A JSON file in `templates/` representing a Datadog dashboard. Includes `title` and `widgets`.

**Base title** — The part of `title` before the first ` - `. Templates sharing the same base title are merged into one deployed dashboard.
- Example: `ABC_Monitoring - Overview` and `ABC_Monitoring - Jobs` both have base title `ABC_Monitoring`

**Top-level template** — The "container" template in a group that receives widgets from descendant templates.

**Dry-run** — Preview mode that shows planned changes without calling the Datadog API.

---

## Framework Workflow

The framework executes these steps in order for each dashboard:

### 1. Discover templates
Scans `templates/*.json` (or files selected via `--files`/`--pattern`).

### 2. Group templates by base title
Files with matching base titles are grouped together.
- Single-file groups = single dashboard
- Multi-file groups = merged dashboard

### 3. Choose top-level template
Selects the "container" template using these heuristics (in order):
1. Any template with `is_root` / `top_level` / `root` flag
2. A template whose title exactly equals the base title
3. The file with the most widgets

### 4. Load and merge descendants
- Appends descendant widgets to the top template
- Stacks widgets vertically to prevent overlaps (default behavior)
- Merges collections: `template_variables`, `notify_list`, `time` block
- Sets merged dashboard title to the base title

### 5. Validate and sanitize widgets
- Ensures layout constraints (clamp width, adjust x position)
- Removes deprecated/incompatible API fields

### 6. Backup (optional)
If `--backup` is provided:
- Writes `.bak.<timestamp>` files with original templates
- Persists sanitized/merged versions
- Dry-run mode skips this step

### 7. Create or update via Datadog API
- Finds existing dashboard by title (if exists, updates; otherwise creates)
- Prints diagnostics and HTTP info (with `--verbose`)

### 8. Post-deploy
- Prints dashboard URL on success
- Prints helpful error messages on failure
- Continues with next deployment (failures don't stop the run)

---

## CLI Reference

| Option | Purpose |
|--------|---------|
| `python3 loader.py` | Deploy all templates in `templates/` |
| `--dry-run` | Preview changes without calling API |
| `--pattern <GLOB>` | Select templates matching glob pattern |
| `--files <FILE>...` | Deploy specific files (can repeat) |
| `--backup` | Write `.bak.<timestamp>` backups |
| `-D, --delete <ID>` | Delete dashboard by ID (can repeat) |
| `-y, --force` | Skip confirmation prompts |
| `-v, --verbose` | Print timestamped diagnostics and HTTP details |

---

## Dashboard ID Format

Datadog IDs are alphanumeric segments separated by hyphens. Format: `xxx-yyy-zzz`

Examples:
```bash
python3 loader.py -D 59i-vd3-sqh
python3 loader.py -D mjq-dq4-mmx -D id-123 -y  # Multiple IDs, enforce the confirmation
```

The framework validates IDs and prompts for confirmation before deletion (unless `--force` is used).

---

## Delete Workflow

The delete workflow is **safe by design**:

* **Explicit ID required** — `-D` requires an ID; errors if no value given  
* **ID validation** — Validates format and warns about suspicious IDs  
* **Confirmation prompts** — You must confirm each ID unless `--force` is used  
* **Dashboard verification** — Checks that dashboard exists before deleting  

**Why this design?** Prevents accidental mass-deletion from mistakes like `python3 loader.py -D -y` or passing a filename.

---

## Directory structure

The codebase is organized into focused, modular components:

```
datadog-importer/
├── config.py                 # Configuration & constants
├── helper.py                 # Utilities (HTTP, logging, file I/O, API client)
├── loader.py                 # CLI entry point & orchestration
│
├── models/
│   └── __init__.py           # Data classes (DashboardTemplate, MergeResult, etc.)
│
├── core/
│   ├── __init__.py           # Validation logic
│   └── merger.py             # Merge & grouping logic
│
├── formatter/
│   └── __init__.py           # Output formatting
│
├── templates/                # Dashboard template JSON files
├── tests/                    # Unit tests (35/35 passing)
└── scripts/                  # Utility scripts
```

---

## Module functionalities

### config.py
**Configuration & constants** (single source of truth)
- `TEMPLATES_DIR_DEFAULT` — default templates directory
- `DASHBOARD_GRID_WIDTH` — grid width for widget layout
- `DEPRECATED_KEYS` — API fields to remove before deployment

### helper.py (Utilities only)
**Generic utility functions**
- File operations: `resolve_selected_files()`, `load_template_file()`
- HTTP utilities: `print_http_info_from_exception()`, `print_http_info_from_response()`
- Logging: `verbose_print()`, `get_utc_date()`
- Data helpers: `ensure_layout()`, `generate_dashboard_diff()`
- API client: `DatadogDashboardManager` class

### models/__init__.py
**Type-safe data structures (dataclasses)**
- `DashboardTemplate` — represents a loaded template
- `MergeResult` — result of merging multiple templates
- `DeploymentTask` — deployment operation
- `DeploymentResult` — result of deployed dashboard

### core/__init__.py
**Validation & sanitization business logic**
- `validate_widgets()` — clamp widget sizes to grid limits
- `sanitize_dashboard_body()` — remove deprecated API fields
- `validate_dashboard_id_format()` — heuristic ID validation

### core/merger.py
**Dashboard merging & grouping logic**
- `merge_templates()` — merge descendants into parent template
- `group_templates_by_base_title()` — group related files
- `choose_top_template()` — select root template from group

### formatter/__init__.py
**Output formatting**
- `print_merge_summary()` — human-friendly merge results

### loader.py
**CLI orchestration layer**
- `deploy_templates()` — main deployment orchestrator
- `_build_cli()` — CLI argument parser
- `main()` — entry point

---

## Key Statistics

| Metric | Value |
|--------|-------|
| **Modules** | 6 focused modules |
| **Tests** | 35/35 passing |
| **Avg module size** | ~100 lines |
| **Functional changes** | 0 (pure refactoring) |
| **Before refactoring** | 2 monolithic files (1000+ lines) |
| **After refactoring** | 6 modular files (~100 lines each) |

