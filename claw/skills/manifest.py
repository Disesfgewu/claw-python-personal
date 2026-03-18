from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from claw.skills.base import SkillManifest, SkillRequirements

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


@dataclass
class ParsedSkillMd:
    manifest: SkillManifest
    prompt: str


def parse_skill_md(content: str) -> ParsedSkillMd:
    """解析 SKILL.md 的 frontmatter + prompt body"""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return ParsedSkillMd(
            manifest=SkillManifest(name="unnamed"),
            prompt=content.strip(),
        )

    frontmatter_raw, body = match.group(1), match.group(2)
    try:
        meta: dict[str, Any] = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError:
        meta = {}

    # Support both claw format (requires.bins/env/python)
    # and OpenClaw format (metadata.openclaw.requires.*)
    requires_raw = meta.get("requires", {})
    openclaw_meta = meta.get("metadata", {}).get("openclaw", {})
    openclaw_requires = openclaw_meta.get("requires", {})

    requires = SkillRequirements(
        bins=(
            requires_raw.get("bins", [])
            + openclaw_requires.get("bins", [])
            + openclaw_requires.get("allBins", [])
        ),
        any_bins=openclaw_requires.get("anyBins", []),
        env=requires_raw.get("env", []),
        python=requires_raw.get("python", []),
        os=openclaw_meta.get("os", []),
    )
    raw_install = openclaw_meta.get("install", [])
    install = raw_install if isinstance(raw_install, list) else []
    # Attach openclaw extras to manifest for future use
    openclaw_extras = {
        "emoji": openclaw_meta.get("emoji", ""),
        "install": install,
        "homepage": meta.get("homepage", ""),
    }

    manifest = SkillManifest(
        name=meta.get("name", "unnamed"),
        description=meta.get("description", ""),
        version=str(meta.get("version", "1.0")),
        requires=requires,
        openclaw_extras=openclaw_extras,
    )

    return ParsedSkillMd(manifest=manifest, prompt=body.strip())
