# Context Snippet Format (Vercel-Aligned Indexed Format)

**A house-style copy** of this file (`snippet_format_path` in `customize.toml`) keeps the lines scripts parse: line 1 with its `root:` field, line 2's `|IMPORTANT:` start and skill name, the `|api:` label, the `|gotchas:` label with its `; ` separator and its `[CARRIED]` marker, which the rebuild helper's `gotchas` action reads back, and no bare `|` line. That setting's comment says which script reads each one.

## Single Skill Snippet Template

```markdown
[{skill-name} v{version}]|root: {skill_root}{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {ranked exports, each with () or bare as step 2's api ranking gives it, comma-separated}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {at most 3 pitfalls, separated by `; `}
```

## Stack Skill Snippet Template

```markdown
[{project}-stack v{version}]|root: {skill_root}{project}-stack/
|IMPORTANT: {project}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {at most 3 pitfalls, separated by `; `}
```
