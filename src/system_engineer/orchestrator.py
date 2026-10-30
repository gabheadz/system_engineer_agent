from __future__ import annotations

import asyncio
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .detect import detect_stack
from .reporting import ComponentOutcome, update_summary, write_component_report
from .specialists import SPECIALISTS, resolve_model, resolve_skills
from .specialists.base import SpecialistResult, run_specialist

Runner = Callable[..., Awaitable[SpecialistResult]]


@dataclass
class RunConfig:
    folders: list[Path]
    out_dir: Path
    mcp_spec: dict
    concurrency: int = 4
    timeout: float = 1800.0
    max_turns: int = 40
    cli_stack_models: dict[str, str] = field(default_factory=dict)
    cli_default_model: str | None = None
    config_models: dict[str, str] = field(default_factory=dict)
    cli_stack_skills: dict[str, list[str]] = field(default_factory=dict)
    cli_default_skills: list[str] | None = None
    cli_no_skills: set[str] = field(default_factory=set)
    config_skills: dict[str, list[str]] = field(default_factory=dict)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def _analyze(folder: Path, cfg: RunConfig, sem: asyncio.Semaphore, runner: Runner) -> ComponentOutcome:
    scanned_at = datetime.now(timezone.utc)
    if not folder.is_dir():
        return ComponentOutcome(folder, None, skipped_reason="not a directory", scanned_at=scanned_at)
    stack = detect_stack(folder)
    if stack is None or stack not in SPECIALISTS:
        return ComponentOutcome(folder, stack, skipped_reason="no supported stack detected", scanned_at=scanned_at)

    model = resolve_model(stack, cfg.cli_stack_models, cfg.cli_default_model, cfg.config_models)
    skills = resolve_skills(
        stack, cfg.cli_stack_skills, cfg.cli_default_skills, cfg.cli_no_skills, cfg.config_skills,
    )
    outcome = ComponentOutcome(folder, stack, model=model, scanned_at=scanned_at, skills=skills)
    async with sem:
        skills_desc = f" skills={skills}" if skills else " skills=none"
        _log(f"[start] {folder.name} ({stack}) model={model}{skills_desc}")
        try:
            result = await asyncio.wait_for(
                runner(folder, SPECIALISTS[stack], model, cfg.mcp_spec, cfg.max_turns, skills),
                timeout=cfg.timeout,
            )
            outcome.markdown = result.markdown
            outcome.cost_usd = result.cost_usd
            outcome.skills = result.skills if result.skills is not None else skills
            _log(f"[done]  {folder.name}")
        except asyncio.TimeoutError:
            outcome.error = f"Timed out after {cfg.timeout:.0f}s"
            _log(f"[fail]  {folder.name}: timeout")
        except Exception as exc:  # isolate per-folder failures
            outcome.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            _log(f"[fail]  {folder.name}: {exc}")
    write_component_report(cfg.out_dir, outcome)
    return outcome


async def run_all(cfg: RunConfig, runner: Runner = run_specialist) -> list[ComponentOutcome]:
    sem = asyncio.Semaphore(max(1, cfg.concurrency))
    outcomes = await asyncio.gather(*(_analyze(f, cfg, sem, runner) for f in cfg.folders))
    update_summary(cfg.out_dir, list(outcomes))
    return list(outcomes)
