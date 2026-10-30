# system-engineer-agent

Analyzes software components (Java, Elixir) with stack-specialized Claude agents built on the
Claude Agent SDK. Specialists never read source files directly: they index the component into the
`codebase-memory-mcp` knowledge graph and query it, pulling at most 15 code snippets to confirm findings.

## Setup

```bash
uv venv && uv pip install -e ".[dev]"      # add --system-certs behind a TLS-intercepting proxy
```

Requires the `codebase-memory-mcp` server. It is auto-discovered from `~/.claude.json`, or set it via
`--mcp-command`, or an `[mcp]` section in `system_engineer.toml` (see `system_engineer.toml.example`).

## Usage

```bash
.venv/bin/system-engineer ./svc-a ./svc-b ./svc-c -o reports --concurrency 3
.venv/bin/system-engineer ./svc-a --model-java claude-opus-5-5 --model-elixir claude-sonnet-5-5
```

Output: `reports/<component>-<stack>.md` per folder plus `reports/SUMMARY.md` (severity table and an
"Incomplete" section for failed or skipped folders). Exit code is 1 if any folder is incomplete.

## Model selection (first match wins)

1. `--model-<stack>`  2. `--default-model`  3. `[models]` in `system_engineer.toml`
(stack key, then `default`)  4. built-in `claude-opus-5-5`.

## Adding a stack

1. Add markers/extensions to `STACK_MARKERS` in `detect.py`.
2. Add `specialists/prompts/<stack>.md` (role + graph recipes).
3. Register it in `SPECIALISTS` in `specialists/__init__.py`. The `--model-<stack>` flag appears automatically.

## Tests

```bash
.venv/bin/python -m pytest
```
