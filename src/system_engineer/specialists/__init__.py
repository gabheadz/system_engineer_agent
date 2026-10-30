from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class SpecialistSpec:
    stack: str
    prompt_file: str
    default_model: str | None = None  # stack-preferred model; loses to CLI/config
    skills: tuple[str, ...] = field(default_factory=tuple)  # loses to CLI/config

    def system_prompt(self, skills: list[str] | None = None) -> str:
        common = (PROMPTS_DIR / "common.md").read_text()
        stack = (PROMPTS_DIR / self.prompt_file).read_text()
        prompt = f"{common}\n\n{stack}"
        if skills:
            names = "\n".join(f"- `{name}`" for name in skills)
            prompt += (
                "\n\n## Enabled skills\n\n"
                "You have the following Claude Code skills available via the `Skill` tool. "
                "Invoke a skill when it is clearly the right fit for the current step; "
                "they are optional, not required.\n\n"
                f"{names}\n"
            )
        return prompt


SPECIALISTS: dict[str, SpecialistSpec] = {
    "java": SpecialistSpec("java", "java.md"),
    "elixir": SpecialistSpec("elixir", "elixir.md"),
    "python": SpecialistSpec("python", "python.md"),
}


def resolve_model(
    stack: str,
    cli_stack_models: dict[str, str],
    cli_default_model: str | None,
    config_models: dict[str, str],
) -> str:
    """Precedence: --model-<stack> > --default-model > config [models] stack > config default
    > spec default_model > built-in default."""
    if stack in cli_stack_models:
        return cli_stack_models[stack]
    if cli_default_model:
        return cli_default_model
    if stack in config_models:
        return config_models[stack]
    if "default" in config_models:
        return config_models["default"]
    spec = SPECIALISTS.get(stack)
    if spec and spec.default_model:
        return spec.default_model
    return DEFAULT_MODEL


def resolve_skills(
    stack: str,
    cli_stack_skills: dict[str, list[str]],
    cli_default_skills: list[str] | None,
    cli_no_skills: set[str],
    config_skills: dict[str, list[str]],
) -> list[str]:
    """Precedence (full replacement at each tier):
    --skill-<stack> > --no-skills-<stack> (forces []) > --default-skill
    > config [skills] stack > config [skills] default > SpecialistSpec.skills > []."""
    if stack in cli_stack_skills:
        return list(cli_stack_skills[stack])
    if stack in cli_no_skills:
        return []
    if cli_default_skills is not None:
        return list(cli_default_skills)
    if stack in config_skills:
        return list(config_skills[stack])
    if "default" in config_skills:
        return list(config_skills["default"])
    spec = SPECIALISTS.get(stack)
    if spec and spec.skills:
        return list(spec.skills)
    return []
