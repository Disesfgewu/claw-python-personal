from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import platform
import shutil

from claw.skills.base import AbstractSkill, SkillRequirements
from claw.skills.manifest import parse_skill_md
from claw.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


def check_requirements(req: SkillRequirements) -> list[str]:
    """
    檢查 skill 的依賴是否滿足。
    回傳 missing items 的 list，空 list = 全部滿足。
    """
    missing: list[str] = []
    if req.os:
        current_os = platform.system().lower()
        if current_os not in [o.lower() for o in req.os]:
            missing.append(f"os:{current_os} (requires one of {req.os})")
    for b in req.bins:
        if shutil.which(b) is None:
            missing.append(f"bin:{b}")
    if req.any_bins:
        found_any = any(shutil.which(b) is not None for b in req.any_bins)
        if not found_any:
            missing.append(f"anyBin (need one of: {req.any_bins})")
    for e in req.env:
        if not os.getenv(e):
            missing.append(f"env:{e}")
    for p in req.python:
        try:
            importlib.import_module(p)
        except ImportError:
            missing.append(f"python:{p}")
    return missing


def load_skills(skills_dir: str) -> SkillRegistry:
    """
    掃描 skills_dir，載入所有 skill。
    回傳已初始化的 SkillRegistry。
    """
    registry = SkillRegistry()

    if not os.path.isdir(skills_dir):
        logger.debug(f"skills dir not found: {skills_dir}")
        return registry

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)

        if os.path.isdir(skill_path):
            init_py = os.path.join(skill_path, "__init__.py")
            skill_md = os.path.join(skill_path, "SKILL.md")

            if os.path.exists(init_py):
                _load_python_skill(init_py, entry, registry)
            elif os.path.exists(skill_md):
                _load_md_skill(skill_md, entry, registry)

        elif entry.endswith(".md"):
            _load_md_skill(skill_path, entry[:-3], registry)

    logger.info(f"loaded {len(registry.all())} skills from {skills_dir}")
    return registry


def _load_python_skill(path: str, name: str, registry: SkillRegistry) -> None:
    """載入 Python class-based skill"""
    try:
        spec = importlib.util.spec_from_file_location(f"skills.{name}", path)
        if spec is None or spec.loader is None:
            logger.warning(f"skill {name}: unable to load spec for {path}")
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        skill_cls = None
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, AbstractSkill)
                and obj is not AbstractSkill
            ):
                skill_cls = obj
                break

        if skill_cls is None:
            logger.warning(f"skill {name}: no AbstractSkill subclass found in {path}")
            return

        skill = skill_cls()

        missing = check_requirements(skill.manifest.requires)
        if missing:
            logger.info(f"skill '{skill.manifest.name}' skipped (missing: {missing})")
            return

        registry.register(skill)
        skill.on_load()
        skill.register_hooks()
        logger.info(f"skill loaded: {skill.manifest.name} (python)")

    except Exception as e:
        logger.warning(f"skill {name}: load error: {e}")


def _load_md_skill(path: str, name: str, registry: SkillRegistry) -> None:
    """載入 SKILL.md prompt-only skill"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        parsed = parse_skill_md(content)
        base_dir = os.path.abspath(os.path.dirname(path))
        prompt = parsed.prompt.replace("{baseDir}", base_dir)

        missing = check_requirements(parsed.manifest.requires)
        if missing:
            logger.info(f"skill '{parsed.manifest.name}' skipped (missing: {missing})")
            return

        skill = _PromptSkill(parsed.manifest, prompt)
        registry.register(skill)

        if prompt:
            _register_prompt_hook(parsed.manifest.name, prompt)

        logger.info(f"skill loaded: {parsed.manifest.name} (md)")

    except Exception as e:
        logger.warning(f"skill {name}: md load error: {e}")


def _register_prompt_hook(skill_name: str, prompt: str) -> None:
    """把 skill 的 prompt 注冊到 before_prompt_build hook"""
    from claw.agent.hooks import get_hooks

    async def inject_prompt(session_id: str, base_prompt: str) -> str:
        separator = "\n\n---\n\n"
        return base_prompt + separator + f"# Skill: {skill_name}\n\n{prompt}"

    get_hooks().register("before_prompt_build", inject_prompt)


class _PromptSkill(AbstractSkill):
    """SKILL.md 載入後包裝成這個 class"""

    def __init__(self, mf, prompt: str):
        self._manifest = mf
        self._prompt = prompt

    @property
    def manifest(self):
        return self._manifest

    @property
    def system_prompt(self) -> str:
        return self._prompt
