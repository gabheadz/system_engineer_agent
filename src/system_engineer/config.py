from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MCP_SERVER_NAME = "codebase-memory-mcp"
CONFIG_PATHS = (
    Path.cwd() / "system_engineer.toml",
    Path.home() / ".config" / "system_engineer" / "config.toml",
)


class ConfigError(RuntimeError):
    pass


@dataclass
class FileConfig:
    mcp: dict = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)
    skills: dict[str, list[str]] = field(default_factory=dict)


def load_file_config(paths: tuple[Path, ...] | None = None) -> FileConfig:
    """Merge config files; earlier paths win."""
    merged = FileConfig()
    for path in reversed(paths if paths is not None else CONFIG_PATHS):
        if not path.is_file():
            continue
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        merged.mcp.update(data.get("mcp", {}))
        merged.models.update(data.get("models", {}))
        for key, value in (data.get("skills") or {}).items():
            if isinstance(value, list):
                merged.skills[key] = [str(v) for v in value]
    return merged


def resolve_mcp_spec(
    cli_command: str | None,
    cli_args: list[str] | None,
    file_config: FileConfig,
    claude_json: Path | None = None,
) -> dict:
    """Resolve the stdio spec for codebase-memory-mcp: flags > toml > ~/.claude.json."""
    if cli_command:
        return {"type": "stdio", "command": cli_command, "args": list(cli_args or [])}
    if file_config.mcp.get("command"):
        return {
            "type": "stdio",
            "command": file_config.mcp["command"],
            "args": list(file_config.mcp.get("args", [])),
            **({"env": file_config.mcp["env"]} if file_config.mcp.get("env") else {}),
        }
    path = claude_json or Path.home() / ".claude.json"
    if path.is_file():
        try:
            server = json.loads(path.read_text()).get("mcpServers", {}).get(MCP_SERVER_NAME)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Could not parse {path}: {exc}") from exc
        if server and server.get("command"):
            spec = {"type": "stdio", "command": server["command"], "args": list(server.get("args", []))}
            if server.get("env"):
                spec["env"] = server["env"]
            return spec
    raise ConfigError(
        f"Cannot locate the '{MCP_SERVER_NAME}' MCP server. Pass --mcp-command, add an [mcp] "
        "section to system_engineer.toml, or configure it in ~/.claude.json."
    )
