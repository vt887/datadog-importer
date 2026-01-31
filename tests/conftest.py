"""
Pytest configuration and fixtures.

This module configures the test environment to ensure the project root is on
sys.path so that tests can import modules like `helper`, `loader`, `core.merger`,
etc. without needing to install the package in development mode.

Why needed:
- Tests run from the tests/ directory but need to import from the project root
- pytest doesn't automatically add the project root to sys.path
- Adding it here ensures all tests can import project modules directly
"""

from pathlib import Path
import sys

# Get the project root directory (parent of tests/)
ROOT = Path(__file__).resolve().parent.parent

# Add project root to sys.path if not already present
# This allows test imports like: `import helper`, `from core import validate_widgets`
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
