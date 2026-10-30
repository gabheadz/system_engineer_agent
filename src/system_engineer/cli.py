from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import ConfigError, load_file_config, resolve_mcp_spec
from .orchestrator import RunConfig, run_all
from .reporting import StateError
from .specialists import DEFAULT_MODEL, SPECIALISTS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="system-engineer",
        description="Analyze software components with stack-specialized Claude agents.",
    )
    p.add_argument("folders", nargs="+", type=Path, help="One or more component folders")
    p.add_argument("-o", "--output-dir", type=Path, default=Path("reports"))
    p.add_argument("--concurrency", type=int, default=4, help="Max parallel specialists")
    p.add_argument("--timeout", type=float, default=1800, help="Per-component timeout (seconds)")
    p.add_argument("--max-turns", type=int, default=40)
    p.add_argument("--default-model", help=f"Model for all specialists (built-in default: {DEFAULT_MODEL})")
    for stack in SPECIALISTS:
        p.add_argument(f"--model-{stack}", help=f"Model for the {stack} specialist")
    p.add_argument(
        "--default-skill", action="append", default=None, metavar="NAME",
        help="Skill to enable for every specialist (repeatable). Overridden by --skill-<stack>/--no-skills-<stack>.",
    )
    for stack in SPECIALISTS:
        p.add_argument(
            f"--skill-{stack}", action="append", default=None, metavar="NAME",
            help=f"Skill for the {stack} specialist (repeatable; replaces defaults).",
        )
        p.add_argument(
            f"--no-skills-{stack}", action="store_true", default=False,
            help=f"Hard-disable all skills for the {stack} specialist.",
        )
    p.add_argument("--mcp-command", help="Executable for the codebase-memory-mcp server")
    p.add_argument("--mcp-args", nargs="*", default=None, help="Arguments for --mcp-command")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    file_cfg = load_file_config()
    try:
        mcp_spec = resolve_mcp_spec(args.mcp_command, args.mcp_args, file_cfg)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cfg = RunConfig(
        folders=[f.expanduser() for f in args.folders],
        out_dir=args.output_dir,
        mcp_spec=mcp_spec,
        concurrency=args.concurrency,
        timeout=args.timeout,
        max_turns=args.max_turns,
        cli_stack_models={s: getattr(args, f"model_{s}") for s in SPECIALISTS if getattr(args, f"model_{s}")},
        cli_default_model=args.default_model,
        config_models=file_cfg.models,
        cli_stack_skills={
            s: list(getattr(args, f"skill_{s}"))
            for s in SPECIALISTS
            if getattr(args, f"skill_{s}") is not None
        },
        cli_default_skills=list(args.default_skill) if args.default_skill is not None else None,
        cli_no_skills={s for s in SPECIALISTS if getattr(args, f"no_skills_{s}")},
        config_skills=file_cfg.skills,
    )
    try:
        outcomes = asyncio.run(run_all(cfg))
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    failed = [o for o in outcomes if not o.markdown]
    print(f"Reports written to {cfg.out_dir.resolve()} ({len(outcomes) - len(failed)} ok, {len(failed)} incomplete)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
