from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "_build", "deps", "target", "build", ".gradle",
    ".idea", ".elixir_ls", "__pycache__", ".venv", "acceptance_test"
}

# stack -> (marker build files, source extensions); order = detection priority
STACK_MARKERS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "java": (("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"), (".java",)),
    "elixir": (("mix.exs",), (".ex", ".exs")),
    "python": (("pyproject.toml", "requirements.txt", "setup.py"), (".py",)),
}


def detect_stack(folder: Path, max_files: int = 20000) -> str | None:
    """Return the stack with the most source files, or None if nothing matches."""
    counts = {stack: 0 for stack in STACK_MARKERS}
    seen = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            seen += 1
            for stack, (markers, exts) in STACK_MARKERS.items():
                if name in markers:
                    counts[stack] += 5
                elif name.endswith(exts):
                    counts[stack] += 1
            if seen >= max_files:
                break
        if seen >= max_files:
            break
    best = max(counts, key=lambda s: counts[s])
    return best if counts[best] > 0 else None
