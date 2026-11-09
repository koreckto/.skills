# .skills

[English](README.md) | **中文（简体）**

面向 Koreckto 项目的共享 [Agent Skills](https://agentskills.io/specification)。

## 技能

| 技能 | 版本 | 描述 |
| --- | --- | --- |
| [python-code-style](skills/python-code-style/SKILL.md) | 1.0.0 | 基于共享的代码风格与语言规范，配合 Ruff 编写、审查、格式化和检查 Python 代码。 |

## 安装

请将下方命令中的 `skill-name` 替换为上表中的实际技能名称。

### Skills CLI

推荐使用 [Skills CLI](https://skills.sh/docs/cli) 安装和更新技能。需要 Node.js 22.20+。

```bash
# 列出本仓库中可用的技能
npx skills add koreckto/.skills --list

# 将技能安装到当前项目
npx skills add koreckto/.skills --skill skill-name

# 全局安装技能
npx skills add koreckto/.skills --skill skill-name -g
```

项目级安装会生成 `skills-lock.json` 并写入技能文件，请一并提交到版本库，确保团队成员使用一致的技能内容。

CLI 会记录每个技能的来源，后续可直接就地更新：

```bash
# 检查更新
npx skills check

# 更新指定技能，或更新全部已安装技能
npx skills update skill-name
npx skills update

# 仅更新全局或当前项目的技能
npx skills update -g skill-name
npx skills update -p skill-name
```

### 手动安装

克隆仓库：

```bash
git clone https://github.com/koreckto/.skills.git koreckto-skills
```

将技能目录复制到 agent 扫描的技能路径下。跨客户端通用路径为 `~/.agents/skills/`（全局生效）和项目内的 `.agents/skills/`（仅当前项目生效）：

```bash
# 在克隆的仓库根目录下执行：全局安装
mkdir -p ~/.agents/skills
cp -R skills/skill-name ~/.agents/skills/

# 在目标项目根目录下执行：仅安装到当前项目
mkdir -p .agents/skills
cp -R /path/to/koreckto-skills/skills/skill-name .agents/skills/
```

> [!NOTE]
> 关于 `.agents/skills/` 的规范说明见 [Agent Skills 实现指南](https://agentskills.io/client-implementation/adding-skills-support)，支持该约定的客户端会自动发现其中的技能。若所用客户端不支持该路径，请查阅[支持的客户端](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)列表，改用其原生技能目录。请保持技能目录名不变，Agent 会直接以目录名作为技能名称。

更新手动安装的技能时，拉取最新仓库代码并重新覆盖技能目录即可：

```bash
git -C /path/to/koreckto-skills pull
rm -rf ~/.agents/skills/skill-name
cp -R /path/to/koreckto-skills/skills/skill-name ~/.agents/skills/
```

若为项目级安装，将命令中的 `~/.agents/skills/` 替换为 `.agents/skills/` 即可。

若不想每次更新都重新复制，可直接创建指向克隆仓库的符号链接，后续只需执行 `git pull` 即可同步更新：

```bash
rm -rf ~/.agents/skills/skill-name
ln -sfn /path/to/koreckto-skills/skills/skill-name ~/.agents/skills/skill-name
```

## 使用

当任务与技能描述匹配时，agent 会自动加载对应技能；也可以在提示词中直接指定技能名称来调用，例如：

```text
使用 python-code-style 审查 src/app/service.py。
```

## 许可证

本项目基于 [MIT License](LICENSE) 开源，各技能目录下均附有独立的许可证文件。
