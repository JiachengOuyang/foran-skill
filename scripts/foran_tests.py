# -*- coding: utf-8 -*-
"""Run the skill's offline unit tests (no FORAN GUI is started)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main(argv=None) -> int:
    root = Path(__file__).resolve().parent.parent / "tests"
    if not root.is_dir():
        print(f"tests folder not found: {root}", file=sys.stderr)
        return 2
    suite = unittest.TestLoader().discover(
        str(root), pattern="test_*.py", top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
