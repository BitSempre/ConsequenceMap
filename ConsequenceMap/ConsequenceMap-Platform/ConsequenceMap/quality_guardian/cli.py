"""The Guardian command line.

    python -m quality_guardian.cli verify            # detect + verify
    python -m quality_guardian.cli verify --full     # force the full suite
    python -m quality_guardian.cli verify --changed a.py b.py
    python -m quality_guardian.cli report             # show the latest report
    python -m quality_guardian.cli status             # show the recorded state

Exit code 0 when the worst verdict is PASS, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from quality_guardian import config, detect, guardian, report
else:
    from . import config, detect, guardian, report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="quality-guardian", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="run one verification cycle")
    verify.add_argument("--full", action="store_true", help="force the full regression suite")
    verify.add_argument("--changed", nargs="*", default=None, help="explicit changed paths")
    verify.add_argument("--json", action="store_true", help="print the report payload as JSON")
    verify.add_argument("--trigger", default="manual", help="label recorded in the report")
    sub.add_parser("report", help="print the latest report path")
    sub.add_parser("status", help="print the recorded change-detection state")
    args = parser.parse_args(argv)

    if args.command == "verify":
        cycle = guardian.run_cycle(
            trigger=args.trigger,
            changed=args.changed,
            force_full=args.full,
        )
        payload = guardian.finalize(cycle)
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"verdict: {payload['verdict']}")
            print(f"changed files: {len(payload['changed_files'])}")
            for check in payload["checks"]:
                print(f"  [{check['verdict']:<13}] {check['name']}: {check['detail']}")
            if payload["human_decision_required"]:
                print(f"human decision required: {payload['human_decision_required']}")
        return 0 if payload["verdict"] == "PASS" else 1

    if args.command == "report":
        latest = report.latest_report()
        print(str(latest) if latest else "no report yet")
        return 0

    if args.command == "status":
        state = detect.load_state()
        print(f"tracked files: {len(state)}")
        for path, digest in sorted(state.items()):
            print(f"  {digest[:12]}  {path}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
