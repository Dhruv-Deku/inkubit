"""Inkubit: hand-drawn quantum circuits and networks to verified, running simulations."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent
EXAMPLES_DIR = PROJECT_DIR / "examples"

__version__ = "0.1.0"
