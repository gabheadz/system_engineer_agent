#!/usr/bin/env python3
"""Strip the "Methodology" and "Metrics" sections (## level) from every Markdown
file in an input folder, writing the result to an output folder.

A "section" starts at `## <name>` (case-insensitive, English spelling tolerated
for Methodology/Metodology) and runs until the next `##` or `#` heading, or EOF.
Fenced code blocks (``` or ~~~) are skipped so headings inside them don't match.

Usage:
    python scripts/strip_sections.py -i reports -o reports-clean
    python scripts/strip_sections.py -i reports -o out -r
    python scripts/strip_sections.py -i reports -o out -s Methodology Metrics Appendix
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_SECTIONS = ("Methodology", "Metodology", "Metrics")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FENCE_RE = re.compile(r"^(```|~~~)")
COST_COLUMN_RE = re.compile(r"cost\s*\(usd\)", re.IGNORECASE)
MODEL_COLUMN_RE = re.compile(r"model", re.IGNORECASE)


def strip_sections(markdown: str, targets: list[str]) -> str:
    """Remove every ## section whose title matches one of `targets` (case-insensitive)."""
    wanted = {t.strip().lower() for t in targets}
    out: list[str] = []
    in_fence = False
    skipping = False

    for line in markdown.splitlines(keepends=True):
        stripped = line.lstrip()

        if FENCE_RE.match(stripped):
            in_fence = not in_fence
            if not skipping:
                out.append(line)
            continue

        if not in_fence:
            m = HEADING_RE.match(stripped)
            if m and len(m.group(1)) <= 2:
                level = len(m.group(1))
                title = m.group(2).lower()
                if level == 2 and title in wanted:
                    skipping = True
                    continue
                skipping = False  # any other ## or # ends a skipped section

        if not skipping:
            out.append(line)

    return "".join(out)


def _row_cells(stripped: str) -> list[str]:
    """Split a `| a | b | c |` row into its cell list (leading/trailing empties dropped)."""
    return stripped.strip("|").split("|")


def _row_without_column(line: str, idx: int) -> str:
    """Return the table-row `line` with cell `idx` removed, preserving indentation and EOL."""
    raw = line.rstrip("\n")
    eol = line[len(raw):]
    body = raw.lstrip()
    indent = raw[: len(raw) - len(body)]
    if not (body.startswith("|") and body.endswith("|")):
        return line
    cells = _row_cells(body)
    if idx < len(cells):
        del cells[idx]
    return f"{indent}|{'|'.join(cells)}|{eol}"


def drop_cost_column(markdown: str) -> str:
    """Remove the `Cost (USD)` column from every Markdown table that has one."""
    lines = markdown.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        body = lines[i].strip()
        if body.startswith("|") and body.endswith("|") and COST_COLUMN_RE.search(body):
            cells = _row_cells(body)
            idx = next(
                (j for j, c in enumerate(cells) if COST_COLUMN_RE.search(c)),
                None,
            )
            if idx is None:
                out.append(lines[i])
                i += 1
                continue
            # Drop the column from the header and every contiguous table row that follows.
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append(_row_without_column(lines[i], idx))
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)

def drop_model_column(markdown: str) -> str:
    """Remove the `Model` column from every Markdown table that has one."""
    lines = markdown.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        body = lines[i].strip()
        if body.startswith("|") and body.endswith("|") and MODEL_COLUMN_RE.search(body):
            cells = _row_cells(body)
            idx = next(
                (j for j, c in enumerate(cells) if MODEL_COLUMN_RE.search(c)),
                None,
            )
            if idx is None:
                out.append(lines[i])
                i += 1
                continue
            # Drop the column from the header and every contiguous table row that follows.
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append(_row_without_column(lines[i], idx))
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)

def transform(markdown: str, filename: str, targets: list[str]) -> str:
    """Apply the section stripper, plus the Cost column stripper when `filename` is SUMMARY.md."""
    result = strip_sections(markdown, targets)
    if filename == "SUMMARY.md":
        r = drop_cost_column(result)
        result = drop_model_column(r)

    return result


def process_folder(
    input_dir: Path,
    output_dir: Path,
    targets: list[str],
    recursive: bool,
    pattern: str = "*.md",
) -> tuple[int, int]:
    """Return (processed, skipped). Skipped = non-regular or unreadable paths."""
    if not input_dir.is_dir():
        raise SystemExit(f"error: input folder not found: {input_dir}")

    glob = input_dir.rglob(pattern) if recursive else input_dir.glob(pattern)
    processed = skipped = 0
    for src in glob:
        if not src.is_file():
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"skip  {src}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        rel = src.relative_to(input_dir)
        dest = output_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(transform(text, src.name, targets), encoding="utf-8")
        print(f"wrote {dest}")
        processed += 1

    return processed, skipped


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-i", "--input", required=True, type=Path, help="Input folder containing .md files")
    p.add_argument("-o", "--output", required=True, type=Path, help="Output folder for stripped .md files")
    p.add_argument(
        "-s", "--sections", nargs="+", default=list(DEFAULT_SECTIONS),
        metavar="NAME",
        help=f"Section titles to remove (default: {' '.join(DEFAULT_SECTIONS)})",
    )
    p.add_argument("-r", "--recursive", action="store_true", help="Recurse into subdirectories")
    p.add_argument("--pattern", default="*.md", help="Glob pattern (default: *.md)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    processed, skipped = process_folder(
        args.input.expanduser(), args.output.expanduser(),
        args.sections, args.recursive, args.pattern,
    )
    print(f"\nDone. {processed} file(s) written, {skipped} skipped.")
    return 0 if processed else 1


if __name__ == "__main__":
    raise SystemExit(main())
