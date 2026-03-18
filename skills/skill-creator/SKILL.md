---
name: skill-creator
description: "Author, edit, or audit a skill in claw-python. Use when: (1) creating a new skill from scratch, (2) improving or reviewing an existing SKILL.md, (3) restructuring a skill directory. Triggers on: 'create a skill', 'write a skill', 'improve this skill', 'review the skill', 'audit the skill', 'tidy up a skill'."
metadata:
  { "openclaw": { "emoji": "🧩", "requires": {} } }
---

# Skill Creator

A skill is a directory under `skills/<name>/` containing a `SKILL.md` file.

## SKILL.md structure

```markdown
---
name: <skill-name>
description: "One sentence: what the skill does + when to trigger it."
metadata:
  { "openclaw": { "emoji": "🔧", "requires": { "bins": ["tool"] }, "install": [] } }
---

# Body

Instructions injected into the system prompt when this skill is active.
Use `{baseDir}` where you need the absolute path to this skill directory.
```

## `metadata.openclaw` fields

| Field | Type | Meaning |
|---|---|---|
| `emoji` | string | Display icon |
| `requires.bins` | list | ALL must be present or skill is skipped |
| `requires.anyBins` | list | AT LEAST ONE must be present or skill is skipped |
| `requires.env` | list | Env vars that must be set |
| `os` | list | `darwin`, `linux` — limits to those platforms |
| `install` | list of dicts | How to install missing bins (display only) |

## `{baseDir}` substitution

At load time `{baseDir}` is replaced with the skill directory's absolute path.
Use it to reference bundled scripts:

```bash
python {baseDir}/scripts/run.py
```

## Directory layout

```
skills/<name>/
├── SKILL.md          # required — frontmatter + instructions
├── scripts/          # optional — executable helpers
└── references/       # optional — docs loaded on demand
```

## Tips

- The `description` field is the only thing read to decide whether to activate the skill — make it comprehensive and include trigger phrases.
- Keep the body under 200 lines to minimize context cost.
- Put large reference material in `references/` and link from the body.
- Put executable helpers in `scripts/` and call them with `{baseDir}/scripts/<file>`.
- Do NOT add README.md or other auxiliary files — only files the agent needs.
