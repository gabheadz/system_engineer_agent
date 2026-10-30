from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITIES = ("Critical", "High", "Medium", "Low")
STATE_FILENAME = ".summary_state.json"


class StateError(RuntimeError):
    """Raised when the SUMMARY state file is unreadable; we refuse to overwrite it."""


@dataclass
class ComponentOutcome:
    folder: Path
    stack: str | None
    model: str | None = None
    report_file: str | None = None
    markdown: str | None = None
    error: str | None = None
    skipped_reason: str | None = None
    cost_usd: float | None = None
    severity_counts: dict[str, int] | None = None
    scanned_at: datetime | None = None
    skills: list[str] | None = None


def slugify(folder: Path, stack: str | None) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", folder.resolve().name).strip("-").lower() or "component"
    return f"{base}-{stack}" if stack else base


def _file_timestamp(scanned_at: datetime) -> str:
    return scanned_at.strftime("%Y%m%dT%H%M%S%f")


def count_severities(markdown: str) -> dict[str, int]:
    """Count '#### ' finding blocks under each '### <Severity>' heading."""
    counts = {s: 0 for s in SEVERITIES}
    current: str | None = None
    for line in markdown.splitlines():
        m = re.match(r"^###\s+(\w+)\s*$", line)
        if m:
            current = m.group(1) if m.group(1) in counts else None
        elif re.match(r"^##\s", line):
            current = None
        elif current and line.startswith("#### "):
            counts[current] += 1
    return counts


def _header(outcome: ComponentOutcome) -> str:
    stamp = (outcome.scanned_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    skills_part = (
        f" · skills `{', '.join(outcome.skills)}`" if outcome.skills else " · skills `none`"
    )
    return (
        f"> Generated {stamp} · model `{outcome.model}` · source "
        f"`{outcome.folder.resolve()}`{skills_part}\n\n"
    )


def write_component_report(out_dir: Path, outcome: ComponentOutcome) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if outcome.scanned_at is None:
        outcome.scanned_at = datetime.now(timezone.utc)
    name = f"{slugify(outcome.folder, outcome.stack)}-{_file_timestamp(outcome.scanned_at)}.md"
    if outcome.markdown:
        outcome.severity_counts = count_severities(outcome.markdown)
        body = _inject_header(outcome.markdown, _header(outcome))
    else:
        body = (
            f"# {outcome.folder.resolve().name} — Analysis FAILED\n\n{_header(outcome)}"
            f"```\n{outcome.error or outcome.skipped_reason or 'unknown error'}\n```\n"
        )
    (out_dir / name).write_text(body)
    outcome.report_file = name


def _inject_header(markdown: str, header: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join([lines[0], "", header.rstrip(), *lines[1:]]) + "\n"
    return header + markdown + "\n"


# --- Persistent summary state -------------------------------------------------


def outcome_to_entry(outcome: ComponentOutcome) -> dict[str, Any]:
    if outcome.markdown:
        status, reason = "ok", None
    elif outcome.skipped_reason:
        status, reason = "skipped", outcome.skipped_reason
    else:
        status, reason = "failed", (outcome.error or "").splitlines()[0] if outcome.error else "failed"
    scanned_at = outcome.scanned_at or datetime.now(timezone.utc)
    return {
        "scanned_at": scanned_at.isoformat(),
        "component": outcome.folder.resolve().name,
        "folder": str(outcome.folder.resolve()),
        "stack": outcome.stack,
        "model": outcome.model,
        "skills": list(outcome.skills) if outcome.skills else [],
        "severity_counts": outcome.severity_counts or {s: 0 for s in SEVERITIES},
        "cost_usd": outcome.cost_usd,
        "report_file": outcome.report_file,
        "status": status,
        "reason": reason,
    }


def load_state(out_dir: Path) -> list[dict[str, Any]]:
    """Return the list of historical entries, or raise StateError on corruption."""
    path = out_dir / STATE_FILENAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise StateError(f"Cannot parse {path}: {exc}. Move it aside before re-running.") from exc
    runs = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        raise StateError(f"{path} is not in the expected shape (missing 'runs' list).")
    return runs


def save_state(out_dir: Path, entries: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / STATE_FILENAME
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"runs": entries}, indent=2, sort_keys=True))
    os.replace(tmp, path)


# --- SUMMARY.md rendering -----------------------------------------------------


_SEV_HEADERS = " | ".join(SEVERITIES)
_SEV_DIVIDER = "---|" * len(SEVERITIES)


def _fmt_cost(value: Any) -> str:
    return f"${float(value):.4f}" if isinstance(value, (int, float)) else "—"


def _fmt_scanned_at(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def render_summary(entries: list[dict[str, Any]]) -> str:
    done = [e for e in entries if e.get("status") == "ok"]
    incomplete = [e for e in entries if e.get("status") != "ok"]
    done.sort(key=lambda e: e.get("scanned_at") or "")
    incomplete.sort(key=lambda e: e.get("scanned_at") or "")
    total_cost = sum(float(e["cost_usd"]) for e in entries if isinstance(e.get("cost_usd"), (int, float)))
    unique_components = {(e.get("folder"), e.get("stack")) for e in entries}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Analysis Summary",
        "",
        f"_Last updated {stamp} · {len(entries)} total scans across {len(unique_components)} components_",
        "",
        "## Components",
        "",
        f"| Scanned at | Component | Stack | Model | {_SEV_HEADERS} | Cost (USD) | Report |",
        f"|---|---|---|---|{_SEV_DIVIDER}---|---|",
    ]
    if done:
        for e in done:
            counts = e.get("severity_counts") or {}
            sev_cells = " | ".join(str(counts.get(s, 0)) for s in SEVERITIES)
            report = e.get("report_file") or ""
            report_cell = f"[{report}]({report})" if report else "—"
            lines.append(
                f"| {_fmt_scanned_at(e.get('scanned_at'))} | {e.get('component', '')} | "
                f"{e.get('stack') or '—'} | `{e.get('model') or '—'}` | {sev_cells} | "
                f"{_fmt_cost(e.get('cost_usd'))} | {report_cell} |"
            )
    else:
        lines.append("| _none_ |" + " |" * (6 + len(SEVERITIES)))

    lines += ["", f"**Total agent cost (all runs):** ${total_cost:.4f}", "", "## Incomplete", ""]
    if incomplete:
        lines += [
            "| Scanned at | Component | Stack | Reason | Report |",
            "|---|---|---|---|---|",
        ]
        for e in incomplete:
            report = e.get("report_file") or ""
            report_cell = f"[{report}]({report})" if report else "—"
            reason = e.get("reason") or e.get("status") or "incomplete"
            lines.append(
                f"| {_fmt_scanned_at(e.get('scanned_at'))} | {e.get('component', '')} | "
                f"{e.get('stack') or '—'} | {reason} | {report_cell} |"
            )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def update_summary(out_dir: Path, outcomes: list[ComponentOutcome]) -> Path:
    """Append outcomes to the persistent state and re-render SUMMARY.md."""
    entries = load_state(out_dir)
    for outcome in outcomes:
        entries.append(outcome_to_entry(outcome))
    save_state(out_dir, entries)
    path = out_dir / "SUMMARY.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary(entries))
    return path
