"""Persistent verification reports.

Every cycle writes a JSON report (machine-readable) and a Markdown summary
(human-readable) under quality_guardian/reports/. The reports are the audit
trail of the Guardian itself.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config

#: How many reports to keep. Older ones are pruned.
MAX_REPORTS = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str, limit: int = 60) -> str:
    keep = [c if c.isalnum() or c in "-_" else "-" for c in text]
    return ("".join(keep).strip("-") or "report")[:limit]


def write_report(payload: dict, root: Path = None, stem: str = "cycle") -> Path:
    """Write the JSON and Markdown report. Returns the JSON path."""
    base = Path(root) if root else config.PROJECT_ROOT
    reports = base / "quality_guardian" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{stamp}-{_slug(stem)}"
    json_path = reports / f"{name}.json"
    md_path = reports / f"{name}.md"
    document = dict(payload)
    document.setdefault("generated_at", _now_iso())
    json_path.write_text(json.dumps(document, indent=2, sort_keys=False, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(document), encoding="utf-8")
    _prune(reports)
    return json_path


def _prune(reports: Path) -> None:
    """Keep only the newest MAX_REPORTS reports."""
    files = sorted(reports.glob("*.json"), key=lambda p: p.name, reverse=True)
    for old in files[MAX_REPORTS:]:
        try:
            old.unlink()
            sibling = old.with_suffix(".md")
            if sibling.exists():
                sibling.unlink()
        except OSError:
            pass


def render_markdown(doc: dict) -> str:
    """Render a report as Markdown."""
    lines = []
    lines.append("# ConsequenceMap — Quality Guardian verification report")
    lines.append("")
    lines.append(f"- **Generated:** {doc.get('generated_at', 'unknown')}")
    lines.append(f"- **Trigger:** {doc.get('trigger', 'manual')}")
    lines.append(f"- **Verdict:** **{doc.get('verdict', 'UNKNOWN')}**")
    lines.append(f"- **Changed files:** {len(doc.get('changed_files', []))}")
    lines.append(f"- **Tests executed:** {doc.get('tests_executed', 0)}")
    lines.append(f"- **Repairs applied:** {len(doc.get('repairs', []))}")
    lines.append("")
    changed = doc.get("changed_files", [])
    lines.append("## Changed files")
    lines.append("")
    if changed:
        for path in changed:
            lines.append(f"- `{path}`")
    else:
        lines.append("_None — no real content change was detected._")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    lines.append("| Check | Verdict | Kind | Detail |")
    lines.append("|---|---|---|---|")
    for check in doc.get("checks", []):
        detail = str(check.get("detail", "")).replace("|", chr(92) + "|")
        lines.append(
            f"| {check.get('name', '')} | **{check.get('verdict', '')}** | "
            f"{check.get('kind') or '—'} | {detail} |"
        )
    lines.append("")
    lines.append("## Test runs")
    lines.append("")
    lines.append("| Module | Verdict | Passed | Failed | Errors | Duration |")
    lines.append("|---|---|---|---|---|---|")
    for run in doc.get("test_runs", []):
        lines.append(
            f"| {run.get('module', '')} | **{run.get('verdict', '')}** | {run.get('passed', 0)} | "
            f"{run.get('failed', 0)} | {run.get('errors', 0)} | {run.get('duration', 0)}s |"
        )
    lines.append("")
    lines.append("## Repairs")
    lines.append("")
    repairs = doc.get("repairs", [])
    if repairs:
        lines.append("| Path | Level | Kind | Applied | Description |")
        lines.append("|---|---|---|---|---|")
        for rep in repairs:
            lines.append(
                f"| `{rep.get('path', '')}` | {rep.get('level', '')} | {rep.get('kind', '')} | "
                f"{'yes' if rep.get('applied') else 'no'} | {rep.get('description', '')} |"
            )
    else:
        lines.append("_None._")
    lines.append("")
    lines.append("## Unresolved issues")
    lines.append("")
    unresolved = doc.get("unresolved", [])
    if unresolved:
        for item in unresolved:
            lines.append(f"- **{item.get('verdict', '')}** — {item.get('name', '')}: {item.get('detail', '')}")
    else:
        lines.append("_None._")
    lines.append("")
    lines.append("## Human decision required")
    lines.append("")
    decision = doc.get("human_decision_required")
    if decision:
        lines.append(str(decision))
    else:
        lines.append("_No — the cycle needed no human decision._")
    lines.append("")
    return "\n".join(lines)


def latest_report(root: Path = None) -> Optional[Path]:
    """The newest JSON report, or None."""
    base = Path(root) if root else config.PROJECT_ROOT
    reports = base / "quality_guardian" / "reports"
    files = sorted(reports.glob("*.json"), key=lambda p: p.name)
    return files[-1] if files else None
