import os
import textwrap

import pytest

from claw.agent.hooks import get_hooks
from claw.skills.base import SkillRequirements
from claw.skills.loader import check_requirements, load_skills
from claw.skills.manifest import parse_skill_md
from claw.tools import registry as tool_registry


def test_parse_skill_md_with_frontmatter():
    content = textwrap.dedent(
        """\
        ---
        name: example
        description: demo
        version: "1.2"
        requires:
          bins: ["bash"]
          env: []
          python: []
        ---
        Hello world
        """
    )
    parsed = parse_skill_md(content)
    assert parsed.manifest.name == "example"
    assert parsed.manifest.description == "demo"
    assert parsed.manifest.version == "1.2"
    assert parsed.prompt == "Hello world"


def test_parse_skill_md_without_frontmatter():
    content = "Just a prompt"
    parsed = parse_skill_md(content)
    assert parsed.manifest.name == "unnamed"
    assert parsed.prompt == "Just a prompt"


def test_parse_skill_md_openclaw_format():
    content = textwrap.dedent(
        """\
        ---
        name: my_skill
        description: A test skill
        homepage: "https://example.com"
        metadata:
          openclaw:
            emoji: 🔧
            requires:
              allBins:
                - jq
              anyBins:
                - curl
            install: "brew install jq"
        ---

        You are a helpful skill.
        """
    )
    parsed = parse_skill_md(content)
    assert parsed.manifest.name == "my_skill"
    assert parsed.manifest.description == "A test skill"
    assert "jq" in parsed.manifest.requires.bins      # allBins → bins
    assert "curl" not in parsed.manifest.requires.bins  # anyBins → any_bins (分離)
    assert "curl" in parsed.manifest.requires.any_bins
    assert parsed.prompt == "You are a helpful skill."


def test_check_requirements_bins():
    missing = check_requirements(SkillRequirements(bins=["definitely_missing_bin_123"]))
    assert "bin:definitely_missing_bin_123" in missing


def test_check_requirements_bins_present():
    missing = check_requirements(SkillRequirements(bins=["bash"]))
    assert "bin:bash" not in missing


def test_check_requirements_any_bins_one_present():
    req = SkillRequirements(any_bins=["bash", "nonexistent_xyz_bin"])
    missing = check_requirements(req)
    assert missing == []


def test_check_requirements_any_bins_none_present():
    req = SkillRequirements(any_bins=["nonexistent_a", "nonexistent_b"])
    missing = check_requirements(req)
    assert len(missing) == 1
    assert "anyBin" in missing[0]


def test_check_requirements_os_current_allowed():
    import platform
    current = platform.system().lower()
    req = SkillRequirements(os=[current])
    assert check_requirements(req) == []


def test_check_requirements_os_not_allowed():
    req = SkillRequirements(os=["nonexistent_os_xyz"])
    missing = check_requirements(req)
    assert any("os:" in m for m in missing)


def test_parse_skill_md_openclaw_bins_key():
    content = textwrap.dedent(
        """\
        ---
        name: github
        description: GitHub skill
        metadata:
          openclaw:
            emoji: "🐙"
            requires:
              bins: ["gh"]
        ---
        Use gh CLI.
        """
    )
    parsed = parse_skill_md(content)
    assert "gh" in parsed.manifest.requires.bins
    assert parsed.manifest.requires.any_bins == []


def test_basedir_substitution(tmp_path):
    skill_dir = tmp_path / "my_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: my_skill
            description: test
            ---
            Run: python3 {baseDir}/scripts/run.py
            """
        )
    )
    reg = load_skills(str(tmp_path))
    skill = reg.get("my_skill")
    assert skill is not None
    assert str(skill_dir) in skill.system_prompt
    assert "{baseDir}" not in skill.system_prompt


def test_openclaw_extras_install_is_list(tmp_path):
    """install 欄位不管原始格式，都應解析成 list"""
    content = textwrap.dedent(
        """\
        ---
        name: myskill
        description: test
        metadata:
          openclaw:
            emoji: "🔧"
            install: "brew install something"
        ---
        body
        """
    )
    parsed = parse_skill_md(content)
    assert isinstance(parsed.manifest.openclaw_extras["install"], list)


@pytest.mark.asyncio
async def test_load_skills_and_prompt_hook(tmp_path):
    hooks = get_hooks()
    hooks.clear()

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    md_dir = skills_dir / "mdskill"
    md_dir.mkdir()
    (md_dir / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: mdskill
            description: md
            version: "1.0"
            requires:
              bins: []
              env: []
              python: []
            ---
            Prompt from md skill
            """
        ),
        encoding="utf-8",
    )

    py_dir = skills_dir / "pyskill"
    py_dir.mkdir()
    (py_dir / "__init__.py").write_text(
        textwrap.dedent(
            """\
            from claw.skills.base import AbstractSkill, SkillManifest
            from claw.tools.registry import tool

            @tool(
                name="py_tool",
                description="py tool",
                parameters={"type": "object", "properties": {}},
            )
            async def py_tool():
                return "ok"

            class PySkill(AbstractSkill):
                @property
                def manifest(self) -> SkillManifest:
                    return SkillManifest(name="py_skill")

                @property
                def tools(self) -> list:
                    return [py_tool]
            """
        ),
        encoding="utf-8",
    )

    orig_registry = tool_registry._registry.copy()
    tool_registry._registry = {}
    try:
        registry = load_skills(str(skills_dir))
        assert registry.get("mdskill") is not None
        assert registry.get("py_skill") is not None

        defs = tool_registry.get_definitions(session_is_main=True)
        assert any(d["function"]["name"] == "py_tool" for d in defs)

        out = await hooks.fire("before_prompt_build", base_prompt="BASE", session_id="agent:main")
        assert "Prompt from md skill" in out
    finally:
        tool_registry._registry = orig_registry
        hooks.clear()


def test_missing_requirement_skill_skipped(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    bad_dir = skills_dir / "badskill"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: badskill
            requires:
              bins: ["definitely_missing_bin_456"]
            ---
            prompt
            """
        ),
        encoding="utf-8",
    )

    registry = load_skills(str(skills_dir))
    assert registry.get("badskill") is None
