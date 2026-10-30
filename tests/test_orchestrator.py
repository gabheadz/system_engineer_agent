import asyncio
import json

import pytest

from system_engineer.orchestrator import RunConfig, run_all
from system_engineer.reporting import (
    STATE_FILENAME,
    StateError,
    count_severities,
    load_state,
    update_summary,
)
from system_engineer.specialists.base import SpecialistResult

REPORT = """# svc — java Analysis

## Executive Summary
- x

## Findings
### Critical
#### Leak
- Evidence: a
### High
None found.
### Medium
#### One
#### Two
### Low
None found.

## Metrics
#### not a finding
"""


def _make(tmp_path, name, marker, content=""):
    d = tmp_path / name
    d.mkdir()
    (d / marker).write_text(content)
    return d


def test_count_severities():
    assert count_severities(REPORT) == {"Critical": 1, "High": 0, "Medium": 2, "Low": 0}


def _run(tmp_path, out, folders, fake, **overrides):
    cfg = RunConfig(
        folders=folders, out_dir=out, mcp_spec={}, concurrency=1,
        cli_stack_models={"elixir": "elixir-model"},
        config_models={"default": "cfg-default"},
        **overrides,
    )
    return asyncio.run(run_all(cfg, fake))


def _fake_cost(cost, captured=None):
    async def fake_runner(folder, spec, model, mcp_spec, max_turns, skills):
        await asyncio.sleep(0)
        if captured is not None:
            captured[folder.name] = {"model": model, "skills": list(skills)}
        if folder.name == "bad-svc":
            raise RuntimeError("boom")
        return SpecialistResult(folder, spec.stack, model, REPORT, cost_usd=cost, skills=list(skills))
    return fake_runner


def test_failure_isolation_and_summary(tmp_path):
    ok = _make(tmp_path, "ok-svc", "pom.xml")
    bad = _make(tmp_path, "bad-svc", "mix.exs")
    unknown = _make(tmp_path, "docs", "readme.txt")
    out = tmp_path / "reports"
    outcomes = _run(tmp_path, out, [ok, bad, unknown, tmp_path / "missing"], _fake_cost(0.5))

    assert [bool(o.markdown) for o in outcomes] == [True, False, False, False]
    assert outcomes[0].report_file and outcomes[0].report_file.endswith(".md")
    summary = (out / "SUMMARY.md").read_text()
    assert "| Scanned at |" in summary and "Cost (USD)" in summary
    assert "ok-svc" in summary and "`cfg-default`" in summary
    assert "| $0.5000 |" in summary and "Total agent cost (all runs):** $0.5000" in summary
    assert "no supported stack detected" in summary and "not a directory" in summary
    assert "boom" in summary
    state = json.loads((out / STATE_FILENAME).read_text())
    assert len(state["runs"]) == 4
    assert sum(1 for r in state["runs"] if r["status"] == "ok") == 1


def test_summary_accumulates_across_runs(tmp_path):
    svc = _make(tmp_path, "svc", "pom.xml")
    out = tmp_path / "reports"
    _run(tmp_path, out, [svc], _fake_cost(0.25))
    first_md = sorted(p.name for p in out.glob("svc-java-*.md"))
    assert len(first_md) == 1

    _run(tmp_path, out, [svc], _fake_cost(0.75))
    both_md = sorted(p.name for p in out.glob("svc-java-*.md"))
    assert len(both_md) == 2, "re-scan must not clobber the earlier report"

    state = json.loads((out / STATE_FILENAME).read_text())
    assert len(state["runs"]) == 2
    assert [r["cost_usd"] for r in state["runs"]] == [0.25, 0.75]

    summary = (out / "SUMMARY.md").read_text()
    assert summary.count("| svc |") == 2
    assert "Total agent cost (all runs):** $1.0000" in summary
    assert "2 total scans across 1 components" in summary


def test_skills_flow_through(tmp_path):
    java = _make(tmp_path, "svc-j", "pom.xml")
    elixir = _make(tmp_path, "svc-e", "mix.exs")
    out = tmp_path / "reports"
    captured = {}
    cfg = RunConfig(
        folders=[java, elixir], out_dir=out, mcp_spec={}, concurrency=1,
        cli_default_skills=["skill-1"],  # falls through to elixir only
        cli_stack_skills={"java": ["skill-2"]},   # overrides default for java
    )
    asyncio.run(run_all(cfg, _fake_cost(0.1, captured)))

    assert captured["svc-j"]["skills"] == ["skill-2"]
    assert captured["svc-e"]["skills"] == ["skill-1"]

    state = json.loads((out / STATE_FILENAME).read_text())
    skills_by_folder = {r["component"]: r["skills"] for r in state["runs"]}
    assert skills_by_folder == {
        "svc-j": ["skill-2"],
        "svc-e": ["skill-1"],
    }
    # Header line in the component report reflects the enabled skills.
    j_report = next(out.glob("svc-j-java-*.md")).read_text()
    assert "skills `skill-2`" in j_report


def test_no_skills_hard_disables(tmp_path):
    java = _make(tmp_path, "svc", "pom.xml")
    out = tmp_path / "reports"
    captured = {}
    cfg = RunConfig(
        folders=[java], out_dir=out, mcp_spec={}, concurrency=1,
        cli_default_skills=["skill-1"],
        cli_no_skills={"java"},
    )
    asyncio.run(run_all(cfg, _fake_cost(0.1, captured)))
    assert captured["svc"]["skills"] == []
    assert "skills `none`" in next(out.glob("svc-java-*.md")).read_text()


def test_skills_block_appears_in_system_prompt_when_set():
    from system_engineer.specialists import SPECIALISTS
    bare = SPECIALISTS["java"].system_prompt()
    with_skills = SPECIALISTS["java"].system_prompt(["my-skill"])
    assert "## Enabled skills" not in bare
    assert "## Enabled skills" in with_skills
    assert "`my-skill`" in with_skills


def test_corrupt_state_aborts(tmp_path):
    svc = _make(tmp_path, "svc", "pom.xml")
    out = tmp_path / "reports"
    out.mkdir()
    (out / STATE_FILENAME).write_text("{not json")
    with pytest.raises(StateError):
        _run(tmp_path, out, [svc], _fake_cost(0.1))
    # File is preserved so the user can inspect/move it aside.
    assert (out / STATE_FILENAME).read_text() == "{not json"
