# Maintaining Python Code Style

This file is not loaded during normal coding tasks. It explains how to change the skill without breaking its rules, links, version data, or examples.

## Audience and scope

This document is for the people who maintain the shared defaults. It is not a coding standard and must not be added to the runtime routing in [SKILL.md](SKILL.md#routing). Keep project-specific rules in the project, not in this directory.

## Change impact map

Read this table before editing. It lists the files that usually need a matching change.

| Changed | Also update |
| --- | --- |
| `SKILL.md` routing table | The matching reference headings and anchors |
| A rule in `references/style-rules.md` | `references/ruff-config.md` rule set map; the section's example; `CHANGELOG.md` |
| A rule in `references/language-rules.md` | `references/ruff-config.md` rule set map; the section's example; `CHANGELOG.md` |
| A section heading in a reference | `SKILL.md` routing link; every cross-link to that anchor |
| Section order or category headings in a reference | `SKILL.md` References table; [Document map](#document-map); [Where a rule goes](#where-a-rule-goes); `CHANGELOG.md` |
| `assets/pyproject.ruff.toml` | `references/ruff-config.md` rule set map and ignore tables; the owning rule sections; `CHANGELOG.md` |
| A per-file ignore | `references/ruff-config.md` per-file ignore table; the rule section's scope; the test or fixture that needs it |
| `references/version-compatibility.md` | `Since:` tags in the rule references; the CI matrix; the verification date |
| A new reference file | `SKILL.md` routing and References table; every cross-link |
| `SKILL.md` description | Manual trigger check with the prompts in [Description and triggering](#description-and-triggering) |
| A rule level change | The unreleased `CHANGELOG.md` entry (next release is major); the verification tag and `ruff-config.md` mapping |
| A new code example | The rule bullet's example block; the manual example check in [Code examples](#code-examples); `CHANGELOG.md` |
| A section-level integrated example | Only when it shows several rules; label it `Integrated example`. |
| `README.md` skill index | The skill's `SKILL.md` path, version, and one-line description |
| `metadata.version` | `CHANGELOG.md`; the release heading and date; the annotated tag `skills/python-code-style/v<version>` |
| A new technical term in Markdown | `.cspell.jsonc` `words`, only when `cspell` flags it |

## Document map

| File | Audience | Owns |
| --- | --- | --- |
| `SKILL.md` | agent | routing, workflow, levels, verification tags, non-negotiables, priorities, task validation |
| `references/style-rules.md` | agent | layout, imports, exports, naming, formatting, docstrings, comments, code examples |
| `references/language-rules.md` | agent | typing, data modeling, functions, pattern matching, comprehensions, async, exceptions, date and time, I/O, paths, testing, security, performance, suppressions |
| `references/ruff-config.md` | agent and maintainer | Ruff configuration, rule set map, ignores, formatter, adoption |
| `references/version-compatibility.md` | agent and maintainer | supported versions, minimum-version detection, feature matrix, EOL |
| `assets/pyproject.ruff.toml` | tooling | shared Ruff rule set template |
| `CHANGELOG.md` | maintainer and user | version history |
| `LICENSE` | legal | MIT license |

## Where a rule goes

| The rule is about | Owning file |
| --- | --- |
| Module layout, imports, exports, naming, formatting, docstrings, comments, code examples | `references/style-rules.md` |
| Typing, data modeling, functions, pattern matching, comprehensions, async, exceptions, date and time, I/O, path handling, tests, security, logging, performance, suppressions | `references/language-rules.md` |
| Ruff configuration, rule codes, ignores, formatter, adoption | `references/ruff-config.md` |
| Supported versions, feature availability, compatibility patterns, EOL | `references/version-compatibility.md` |

Each rule has one owning section. Other documents link to it; they do not restate it. When a rule spans two concerns, split it and put each part in the section that owns it.

Within each reference, sections are grouped under category headings that follow the writing workflow. Place a new section under the heading whose scope matches; add a new heading only when no existing heading fits.

## Classifying a rule

Use the levels and verification tags defined in [SKILL.md](SKILL.md#rule-conventions):

- Assign the level by impact, never by tooling. A rule whose violation is a security, privacy, data-loss, wrong-behavior, hidden-failure, resource-leak, or compatibility defect is `MUST` or `MUST NOT`.
- A rule whose violation costs readability, maintainability, consistency, documentation quality, or test clarity is `SHOULD` or `SHOULD NOT`.
- A preference with no default is `MAY`.
- A rule that mixes severities must be split. Do not put a `MUST` and a `SHOULD` obligation in one bullet.
- Then choose the verification tag. Name an automated check when it covers the whole rule. Add `Review` when no check exists or the check covers only part.
- An important rule without a check is a `MUST` with `Review`, not a `SHOULD`. A trivial rule with a check is a `SHOULD` with the check tag, not a `MUST`.
- Never raise or lower a level to match the tooling.

The level describes impact, not verifiability. Use [Priorities](SKILL.md#priorities) to resolve conflicts between rules.

## MUST suppression loop

A `# noqa` or type-checker ignore on a `MUST` rule is not an exception. It is a reported violation:

- The review report lists every suppressed `MUST` with its file, line, rule, reason, approver, and follow-up.
- A project-specific exception is recorded in the project rules as an explicit override, not as an inline suppression. The shared level does not change.
- A shared rule that is too strict for legitimate use is downgraded in this skill, with an entry in the unreleased `CHANGELOG.md`; the next release is a major version.
- An emergency suppression is temporary and still a reported violation. It needs an owner, a review report entry, and a linked level change or fix; the level change is mandatory before the suppression becomes routine.

Repeated `MUST` suppressions are a drift signal, not a stable pattern.

## Adding or changing a rule

1. Choose the owning file and section from [Where a rule goes](#where-a-rule-goes).
2. Check whether the rule already exists. Update the existing bullet instead of adding a second copy.
3. Write one rule per bullet in the section's style: bold sentence-initial modal, imperative verb without an actor or pronoun, and a parenthesized verification tag (separated by semicolons, for example `Ruff: ANN`; `Review`; `Since: 3.12`). Every bullet gets a tag; use `Review` when no automated check covers the rule.
4. Choose the level by impact: `MUST` for a defect, `SHOULD` for a default, `MAY` for a preference.
5. Add the strongest verification available. An automated check is preferred but not required; a `MUST` may carry `Review`. A warning-only check cannot be the sole verification for a `MUST`.
6. Add or update an example only if it clarifies the rule, and attach a multi-line example under the rule bullet. Keep it short.
7. Update [Where a rule goes](#where-a-rule-goes) only if the new rule starts a new topic.
8. Update the rule set map in `references/ruff-config.md` if the rule maps to a Ruff family.
9. Fold the change into the unreleased `CHANGELOG.md` entry; the SemVer bump is chosen at release.
10. Run the [Release checklist](#release-checklist).

## Adding a section or reference

Add a section first. Split a reference into a new file only when it exceeds roughly 700 lines, when one topic exceeds roughly 200 lines, or when different tasks load different halves of the file. Examples do not by themselves justify a split; split by topic, not by line count alone. Do not split just because a file has many short sections. A split is a structural change, not a content change.

When adding a section:

1. Add the heading to the reference under the matching category heading.
2. Add `**Applies to.**` and `**Verified by.**` lines.
3. Add a routing row in [SKILL.md](SKILL.md#routing) if the section is a new task entry point.
4. Add cross-links from related sections instead of duplicating the rule.

When adding a reference:

1. Create the file under `references/`.
2. Add it to the `SKILL.md` routing table and References table.
3. Add a concise scope summary under the title.
4. Update `README.md` if the skill index exposes the file.
5. Search for every anchor that moved and update it.

Keep anchors stable. If a heading must change, update every link in the same change.

## Changing the Ruff template

The template is `assets/pyproject.ruff.toml`. It contains only `[tool.ruff*]` sections; it is not a complete `pyproject.toml`.

1. Edit the template.
2. Validate the TOML with `tombi` or `python -c "import tomllib; ..."`.
3. Update the rule set map and the intentional-ignore table in `references/ruff-config.md`.
4. Update the owning rule section in `style-rules.md` or `language-rules.md` for any rule whose behavior or level changed.
5. Test the template against a small fixture project:
   - `ruff check --show-settings`
   - `ruff check`
   - `ruff format --check`
6. Check the interaction notes in [Common conflicts](references/ruff-config.md#common-conflicts).
7. Record a breaking change in the unreleased `CHANGELOG.md` entry; the next release is a major version.

Do not add a rule to the template without an owning rule section. Do not remove a rule from the template without updating the rule map and the changelog.

## Adding a Python version

1. Update the support table, feature matrix, and EOL notes in `references/version-compatibility.md`.
2. Update the verification date.
3. Check every `Since:` tag in the rule references. A rule that was gated on a newer minimum version may now apply to more projects, or the alternative may no longer be needed.
4. Update the CI matrix if the repository runs one.
5. Run the examples and tests on the new minimum and maximum versions.
6. Record the change in the unreleased `CHANGELOG.md` entry; the next release is a minor version unless it removes support, which is a major version.

Do not describe a version as supported until it is in the table and the feature claims are verified against the CPython documentation.

## Adding a tool

A new tool needs a home and a reason. Keep `references/ruff-config.md` focused on Ruff.

1. Decide whether the tool belongs in an existing reference or needs a new one.
2. Add a section with `Applies to`, `Verified by`, and rules.
3. Add a routing row in `SKILL.md`.
4. Add the check command to the [Release checklist](#release-checklist) if the repository should run it.
5. Add the tool to the `compatibility` frontmatter if it is required at runtime.
6. Record the tool in the unreleased `CHANGELOG.md` entry; the next release is a minor version.

A tool that only produces warnings cannot be the sole verification for a `MUST`. Pair it with `Review`, or keep the rule at `SHOULD`.

## Code examples

Examples are part of the standard. Review them manually before release:

- Multi-line examples are attached to the rule bullet they illustrate. A section-level block is used only for a multi-rule flow and labeled `Integrated example`. Do not repeat the same example at both levels.
- Every fenced block has a language tag. `markdownlint` MD040 checks this.
- A `python` fence is valid Python on the skill's minimum version (3.11), or carries a `# Python 3.x+` marker with the 3.11-compatible alternative nearby.
- A `text` fence is used for pseudo-code, intentionally invalid code, or output.
- A good/bad pair is labeled, and the bad example states why it is wrong.
- Statement-level examples are separated by a single blank line; two blank lines surround top-level definitions and classes.
- The example follows the rules it illustrates and does not contradict a rule it omits.
- Imports and definitions needed to understand the example are present, or the elision is marked with `...`.
- No realistic secrets, credentials, or personal data appear in an example.
- A bad example in a linted file is moved to documentation or excluded from the check instead of being suppressed.

Docstring examples are formatted by `ruff format` because the template enables `docstring-code-format`. Markdown fences are not formatted by Ruff; review them for readability and the project's line length.

## Markdown formatting

Write one line per paragraph and one line per list item. Do not hard-wrap prose to a fixed column. Keep tables, headings, frontmatter, and fenced code blocks as they are. This keeps a diff local to the sentence that changed.

`markdownlint` MD013 is disabled, so long lines are expected. The `.editorconfig` `[*.md]` section sets `max_line_length = off` so editors do not re-wrap the file.

## Description and triggering

The `description` in `SKILL.md` is the only metadata an agent sees before it loads the skill. Keep it specific and in the third person.

Before changing it, write down:

1. One sentence for what the skill does.
2. Three prompts that should trigger the skill, such as a style review, a Ruff configuration request, and a version-compatibility question.
3. Three prompts that should not trigger it, such as a JavaScript task, a package-publishing workflow, and a pure product-requirements question.

Run the prompts against the new description. Check that the skill triggers on the first three and not on the last three. Update the description if it over-triggers on unrelated tasks or under-triggers on Python style, Ruff, and version questions.

Keep the description under 1,024 characters. Do not use XML angle brackets. Keep the `name` field identical to the directory name.

## Versioning and deprecation

Follow the repository [versioning and deprecation policy](../../AGENTS.md#versioning-and-deprecation). The version under development is provisional until the release tag exists.

## Release checklist

Before releasing a skill change:

- [ ] `markdownlint-cli2` passes on the changed Markdown files.
- [ ] `cspell` passes; add only the terms it flags, do not disable the checker.
- [ ] `tombi` or a TOML parser validates `assets/pyproject.ruff.toml`.
- [ ] Internal links and anchors resolve.
- [ ] Every rule has a verification tag; every rule without a full automated check carries `Review`.
- [ ] Every `MUST` and `MUST NOT` is justified by impact, not by the presence of a check.
- [ ] Every `Review`-tagged `MUST` is phrased as an objective, reviewer-decidable condition.
- [ ] No `MUST` rule relies on a routine suppression; suppressed MUSTs are reported and have a level decision.
- [ ] Every selected Ruff family maps to a rule section or an intentional ignore in `references/ruff-config.md`.
- [ ] No rule is duplicated across sections or files.
- [ ] The frontmatter `name` matches the directory name.
- [ ] `metadata.version`, the latest `CHANGELOG.md` heading and date, and the root README version match.
- [ ] The version matrix has a current verification date.
- [ ] The description was checked against the three should-trigger and three should-not-trigger prompts.
- [ ] Every multi-line example is attached to its rule or labeled `Integrated example`; no example is duplicated at both levels.
- [ ] Code examples have language tags, Python 3.11-compatible syntax (or a `# Python 3.x+` marker), and no realistic secrets.
- [ ] `README.md` lists the skill, version, and description.
- [ ] No project-specific rule was written into the skill directory.
- [ ] `git diff --check` reports no whitespace errors.
- [ ] Create the annotated tag `skills/python-code-style/v<version>` on the release commit; without it, the version remains unreleased.

## Review rubric

Use this rubric when reviewing a skill change:

1. **Trigger clarity**: does the description cover Python style, language, Ruff, and version tasks without over-triggering on unrelated work?
2. **Normative accuracy**: do the rules match the Ruff configuration and the Python documentation for the minimum version?
3. **Level accuracy and verification**: do levels reflect impact rather than tooling? Does every rule name its verification tag, and is every `Review`-tagged `MUST` objectively decidable?
4. **Consistency**: one term per concept, one owning section per rule, valid anchors, and every section under the matching category heading.
5. **Scope**: shared Python style, language, and tooling standards only; project-specific rules, package publishing, release engineering, and project architecture stay out.
6. **Freshness**: the version matrix is dated, examples still parse, and no stale API claims remain.
7. **Context economy**: `SKILL.md` stays under 500 lines, references stay focused, and prose does not repeat what Ruff already enforces.

## Signs of drift

Watch for these failure modes:

- `SKILL.md` grows past 500 lines or starts duplicating reference content.
- A rule appears in two references.
- A rule is `MUST` only because a check exists, or `SHOULD` only because it lacks one.
- A non-mechanical rule has no `Review` tag, or `Review` is treated as a severity level.
- A `MUST` rule is kept alive by routine suppressions instead of a level decision.
- A selected Ruff rule has no rule section.
- A routing link or anchor no longer resolves.
- An example uses syntax that does not parse on the minimum Python version without a version marker.
- The version matrix date is stale, or a feature claim is no longer true.
- The description over-triggers on unrelated tasks or under-triggers on style.
- Project-specific rules creep into the shared skill.
- Examples contain realistic secrets or personal data.
- Counts or lists are maintained by hand and disagree with the files.

## Update loop

1. Make the change in the owning file.
2. Update the change impact map's dependents.
3. Run the static checks from the [Release checklist](#release-checklist).
4. Run the manual trigger and example checks.
5. Review the diff for accidental rewrites and unrelated files.
6. Fold the change into the unreleased `CHANGELOG.md` entry; update `metadata.version` only at release.
7. Release by creating the annotated tag `skills/python-code-style/v<version>`, or hand off for review.
