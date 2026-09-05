#!/usr/bin/env python3
"""Compile platform YAML through the canonical data compiler."""

import sys
from compile_data import compile_platforms


def main() -> int:
    compile_platforms()
    return 0


if __name__ == "__main__":
    sys.exit(main())
