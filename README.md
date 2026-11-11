# .skills

**English** | [中文（简体）](README.zh-CN.md)

Shared [Agent Skills](https://agentskills.io/specification) for use across Koreckto projects.

## Skills

| Skill | Version | Description |
| --- | --- | --- |
| [python-code-style](skills/python-code-style/SKILL.md) | 1.1.0 | Writes, reviews, formats, and lints Python code against shared style and language standards with Ruff. |

## Installation

`skill-name` in the commands below is a placeholder for a skill from the table above.

### Skills CLI

The [Skills CLI](https://skills.sh/docs/cli) is the recommended way to install and update skills. It requires Node.js 22.20+.

```bash
# List the skills available in this repository
npx skills add koreckto/.skills --list

# Install a skill into the current project
npx skills add koreckto/.skills --skill skill-name

# Install a skill globally
npx skills add koreckto/.skills --skill skill-name -g
```

Project installs write `skills-lock.json` and the installed skill files. Commit them so everyone uses the same skill content.

The CLI records each skill's source, so updates happen in place:

```bash
# Check for updates
npx skills check

# Update one skill, or every installed skill
npx skills update skill-name
npx skills update

# Limit the update to global or project scope
npx skills update -g skill-name
npx skills update -p skill-name
```

### Manual installation

Clone the repository:

```bash
git clone https://github.com/koreckto/.skills.git koreckto-skills
```

Copy the skill directory into a path your agent scans for skills. The cross-client convention is `~/.agents/skills/` for all projects and `.agents/skills/` inside a project:

```bash
# From the cloned repository root: install for all projects
mkdir -p ~/.agents/skills
cp -R skills/skill-name ~/.agents/skills/

# From your project: install for this project only
mkdir -p .agents/skills
cp -R /path/to/koreckto-skills/skills/skill-name .agents/skills/
```

> [!NOTE]
> `.agents/skills/` is described in the [Agent Skills implementation guide](https://agentskills.io/client-implementation/adding-skills-support); any client that scans it will discover the skill. If your client does not, use its native skills directory from the [supported agents](https://github.com/vercel-labs/skills/blob/main/docs/agents.md) table. Keep the skill directory name unchanged: agents use it as the skill name.

To update a manual install, pull the clone and replace the skill directory:

```bash
git -C /path/to/koreckto-skills pull
rm -rf ~/.agents/skills/skill-name
cp -R /path/to/koreckto-skills/skills/skill-name ~/.agents/skills/
```

For a project-level install, use `.agents/skills/` in place of `~/.agents/skills/`.

To avoid copying on every update, symlink the skill directory from the clone instead; `git pull` then updates it in place:

```bash
rm -rf ~/.agents/skills/skill-name
ln -sfn /path/to/koreckto-skills/skills/skill-name ~/.agents/skills/skill-name
```

## Usage

Agents load a skill automatically when a task matches its description. Mention the skill by name to invoke it explicitly, for example:

```text
Use python-code-style to review src/app/service.py.
```

## License

This project is licensed under the [MIT License](LICENSE). Each skill includes its own copy in its directory.
