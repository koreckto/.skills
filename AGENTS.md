# AGENTS.md

This repository is a collection of shared Agent Skills. Each skill lives in `skills/<name>/` and is self-contained: `SKILL.md` is the entry point, and `references/`, `assets/`, and `scripts/` are loaded only when needed.

## Writing skills

Read these before creating or changing a skill:

- [Specification](https://agentskills.io/specification)
- [Best practices for skill creators](https://agentskills.io/skill-creation/best-practices)
- [Optimizing skill descriptions](https://agentskills.io/skill-creation/optimizing-descriptions)
- [Using scripts in skills](https://agentskills.io/skill-creation/using-scripts)

For an existing skill, read its `MAINTENANCE.md` first and follow its change impact map.

Hard rules:

- Write repository documentation in English, one line per paragraph or list item; do not hard-wrap prose.
- The frontmatter `name` must match the skill directory name. Keep `SKILL.md` under 500 lines; move detail into `references/`.
- Keep the root `README.md` row in sync with `metadata.version` and `description`.
- Update `CHANGELOG.md` and `metadata.version` together.
- Do not put project-specific rules, secrets, or credentials in a skill.
- After writing or changing a skill, validate that skill with `uvx --from skills-ref agentskills validate skills/<name>` and fix every reported problem before committing.

## Checks

`.mise.toml` requests tools as `latest`; `mise.lock` and `.mise/locks/` record the resolved versions and dependency graphs, so commit them and keep them in sync. One-time setup, then run from the repository root:

```bash
mise trust .
mise install --locked
markdownlint-cli2 "**/*.md"
cspell --no-progress "**/*.md"
tombi check .
tombi format --check .
git diff --check
```

Do not hand-edit `mise.lock` or `.mise/locks/`; refresh them with `mise lock` and review the diff. Fix check failures instead of disabling checks. Add a word to `.cspell.jsonc` only when it is a genuine term.
