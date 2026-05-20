#!/usr/bin/env python
"""Run Django tests in a CI-friendly way.

This script exists because the GitHub Actions workflow expects a single
entrypoint that can accept a target test module and print a concise report.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Django tests with a report")
    parser.add_argument(
        "--target",
        default="",
        help="Optional Django test target, for example appointments.tests",
    )
    parser.add_argument(
        "--verbosity",
        default="2",
        help="Django test verbosity level",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    project_root = Path(__file__).resolve().parent
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "medqueue_project.settings")

    command = [sys.executable, "manage.py", "test"]
    if args.target:
        command.append(args.target)
    command.extend(["--verbosity", str(args.verbosity)])

    completed = subprocess.run(command, cwd=project_root)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())