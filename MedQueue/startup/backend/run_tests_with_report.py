import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path


def _parse_counts(output: str):
    total_tests = None
    failures = 0
    errors = 0

    ran_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if ran_match:
        total_tests = int(ran_match.group(1))

    failed_match = re.search(r"FAILED\s*\(([^)]*)\)", output)
    if failed_match:
        details = failed_match.group(1)
        f_match = re.search(r"failures=(\d+)", details)
        e_match = re.search(r"errors=(\d+)", details)
        if f_match:
            failures = int(f_match.group(1))
        if e_match:
            errors = int(e_match.group(1))

    return total_tests, failures, errors


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def main():
    parser = argparse.ArgumentParser(description="Run Django tests and write a human-readable report")
    parser.add_argument(
        "--target",
        default="appointments.tests",
        help="Django test target (default: appointments.tests)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    report_dir = root / "test_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    started_at = dt.datetime.now()
    cmd = [sys.executable, "manage.py", "test", args.target, "-v", "2"]

    print(_color("=" * 68, "36"))
    print(_color(" MEDQUEUE TEST RUN ", "36"))
    print(_color("=" * 68, "36"))
    print(f"Start: {started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    full_output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    total_tests, failures, errors = _parse_counts(full_output)

    ended_at = dt.datetime.now()
    duration = (ended_at - started_at).total_seconds()
    passed = result.returncode == 0

    status_line = "STATUS: PASSED" if passed else "STATUS: FAILED"
    status_colored = _color(status_line, "32" if passed else "31")

    print(status_colored)
    print(f"Tests run: {total_tests if total_tests is not None else 'unknown'}")
    print(f"Failures: {failures}")
    print(f"Errors: {errors}")
    print(f"Duration: {duration:.2f}s")
    print(_color("=" * 68, "36"))

    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"test_report_{timestamp}.txt"
    latest_report_path = report_dir / "latest_test_report.txt"

    report_header = [
        "MEDQUEUE TEST REPORT",
        "=" * 68,
        f"Start: {started_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"End:   {ended_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Duration: {duration:.2f}s",
        f"Command: {' '.join(cmd)}",
        f"{status_line}",
        f"Tests run: {total_tests if total_tests is not None else 'unknown'}",
        f"Failures: {failures}",
        f"Errors: {errors}",
        "=" * 68,
        "",
        "RAW OUTPUT:",
        "-" * 68,
        full_output,
        "",
    ]

    report_text = "\n".join(report_header)
    report_path.write_text(report_text, encoding="utf-8")
    latest_report_path.write_text(report_text, encoding="utf-8")

    print(f"Report saved: {report_path}")
    print(f"Latest report: {latest_report_path}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
