from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from . import SpecialistSpec
from ..config import MCP_SERVER_NAME

GRAPH_TOOLS = (
    "index_repository", "index_status", "check_index_coverage", "get_architecture",
    "search_graph", "query_graph", "trace_path", "get_code_snippet", "search_code",
)
ALLOWED_TOOLS = [f"mcp__{MCP_SERVER_NAME}__{name}" for name in GRAPH_TOOLS]


@dataclass
class SpecialistResult:
    folder: Path
    stack: str
    model: str
    markdown: str
    cost_usd: float | None = None
    turns: int | None = None
    skills: list[str] | None = None


class SpecialistError(RuntimeError):
    pass


def project_name(folder: Path) -> str:
    digest = hashlib.sha1(str(folder.resolve()).encode()).hexdigest()[:8]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", folder.resolve().name).strip("-").lower() or "component"
    return f"{slug}-{digest}"


def build_options(
    folder: Path,
    spec: SpecialistSpec,
    model: str,
    mcp_spec: dict,
    max_turns: int,
    skills: list[str] | None = None,
) -> ClaudeAgentOptions:
    skills = skills or []
    # The SDK auto-adds the "Skill" tool to allowed_tools when `skills` is non-None.
    # When skills are off we pass [] (deterministic no-skills); when on we also allow
    # the user's project/user skill sources to be discovered.
    return ClaudeAgentOptions(
        model=model,
        cwd=str(folder),
        system_prompt=spec.system_prompt(skills),
        mcp_servers={MCP_SERVER_NAME: mcp_spec},
        strict_mcp_config=True,
        tools=[],  # no built-in tools: no Read/Bash/Grep, graph only
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="dontAsk",
        setting_sources=["user", "project"] if skills else [],
        skills=skills,
        max_turns=max_turns,
    )


def build_prompt(folder: Path, spec: SpecialistSpec) -> str:
    return (
        f"Analyze the {spec.stack} component located at:\n{folder.resolve()}\n\n"
        f"Use project name `{project_name(folder)}` for index_repository. "
        f"Component name for the report title: {folder.resolve().name}. "
        "Follow the mandatory workflow and finish with the Markdown report only."
    )


async def run_specialist(
    folder: Path,
    spec: SpecialistSpec,
    model: str,
    mcp_spec: dict,
    max_turns: int = 40,
    skills: list[str] | None = None,
) -> SpecialistResult:
    skills = list(skills or [])
    options = build_options(folder, spec, model, mcp_spec, max_turns, skills)
    last_text = ""
    result: ResultMessage | None = None
    # Drain the generator completely so the MCP subprocess exits cleanly.
    async for message in query(prompt=build_prompt(folder, spec), options=options):
        if isinstance(message, AssistantMessage):
            text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
            if text.strip():
                last_text = text
        elif isinstance(message, ResultMessage):
            result = message
    if result is None:
        raise SpecialistError("Agent finished without a result message")
    if result.is_error or result.subtype != "success":
        raise SpecialistError(
            f"Agent ended with {result.subtype}: {'; '.join(result.errors or []) or result.stop_reason}"
        )
    markdown = (result.result or last_text).strip()
    if not markdown:
        raise SpecialistError("Agent returned an empty report")
    return SpecialistResult(
        folder=folder, stack=spec.stack, model=model, markdown=markdown,
        cost_usd=result.total_cost_usd, turns=result.num_turns, skills=skills,
    )
