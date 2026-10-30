import json

import pytest

from system_engineer.config import ConfigError, FileConfig, load_file_config, resolve_mcp_spec
from system_engineer.specialists import DEFAULT_MODEL, resolve_model, resolve_skills


def test_mcp_cli_beats_toml_beats_claude_json(tmp_path):
    cj = tmp_path / "claude.json"
    cj.write_text(json.dumps({"mcpServers": {"codebase-memory-mcp": {"command": "from-json"}}}))
    cfg = FileConfig(mcp={"command": "from-toml", "args": ["x"]})
    assert resolve_mcp_spec("from-cli", ["a"], cfg, cj)["command"] == "from-cli"
    assert resolve_mcp_spec(None, None, cfg, cj)["command"] == "from-toml"
    assert resolve_mcp_spec(None, None, FileConfig(), cj)["command"] == "from-json"


def test_mcp_unresolvable_raises(tmp_path):
    with pytest.raises(ConfigError):
        resolve_mcp_spec(None, None, FileConfig(), tmp_path / "missing.json")


def test_file_config_earlier_path_wins(tmp_path):
    a, b = tmp_path / "a.toml", tmp_path / "b.toml"
    a.write_text('[models]\njava = "A"\n')
    b.write_text('[models]\njava = "B"\nelixir = "B2"\n')
    cfg = load_file_config((a, b))
    assert cfg.models == {"java": "A", "elixir": "B2"}


def test_model_precedence():
    cfg = {"default": "cfg-default", "java": "cfg-java"}
    assert resolve_model("java", {"java": "cli-java"}, "cli-def", cfg) == "cli-java"
    assert resolve_model("java", {}, "cli-def", cfg) == "cli-def"
    assert resolve_model("java", {}, None, cfg) == "cfg-java"
    assert resolve_model("elixir", {}, None, cfg) == "cfg-default"
    assert resolve_model("elixir", {}, None, {}) == DEFAULT_MODEL


def test_skills_precedence():
    cfg = {"default": ["cfg-def-a"], "java": ["cfg-java-a", "cfg-java-b"]}
    # 1. --skill-<stack> wins over everything else
    assert resolve_skills("java", {"java": ["cli-a"]}, ["cli-def"], set(), cfg) == ["cli-a"]
    # 2. --no-skills-<stack> hard-disables even against a config default
    assert resolve_skills("java", {}, ["cli-def"], {"java"}, cfg) == []
    # 3. --default-skill replaces config
    assert resolve_skills("java", {}, ["cli-def"], set(), cfg) == ["cli-def"]
    # 4. config [skills] stack beats config default
    assert resolve_skills("java", {}, None, set(), cfg) == ["cfg-java-a", "cfg-java-b"]
    # 5. config default applies when no stack entry
    assert resolve_skills("elixir", {}, None, set(), cfg) == ["cfg-def-a"]
    # 6. empty fallback — no skills configured anywhere
    assert resolve_skills("elixir", {}, None, set(), {}) == []


def test_skills_loaded_from_toml(tmp_path):
    a = tmp_path / "a.toml"
    a.write_text('[skills]\ndefault = ["x"]\njava = ["y", "z"]\n')
    cfg = load_file_config((a,))
    assert cfg.skills == {"default": ["x"], "java": ["y", "z"]}
