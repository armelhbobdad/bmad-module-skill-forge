# Context Snippet Format (Vercel-Aligned Indexed Format)

## Skill Root Path

The snippet `root:` path must reflect the IDE's actual skill directory — its `skill_root` from the IDE → Context File Mapping table in `managed-section-format.md`. Each IDE has its own skill directory (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`).

The root path in context-snippet.md on disk uses the **`skill_root` of the first entry in `target_context_files`** (resolved in step-01 from config.yaml IDE mapping). When assembling managed sections for other context files, step-04 rewrites root paths to match the target context file's skill root.

**Authoring-repo override:** If `snippet_skill_root_override` is set in `config.yaml`, it replaces the IDE-mapped value for snippet generation and freezes matching prefixes against step-04 rewrites. See the "Resolution rules" section in `managed-section-format.md` for the full semantics.

## Format Rules

- Indexed pipe-delimited format per skill — retrieval instruction + file map + inline gotchas
- ~80-120 tokens per skill target (up from ~50-80, justified by Vercel research). Deep tier may exceed 120 tokens when gotchas are load-bearing (substantive breaking-change notices, deprecated-API lists); the hard ceiling is 300 tokens.
- T1-now content only (AST-current, no annotations)
- Line 2 (IMPORTANT) is the RETRIEVAL INSTRUCTION — always present, tells agent to read SKILL.md
- Section anchors (`#quick-start`, `#key-types`) must match actual SKILL.md heading slugs
- gotchas line prevents common mistakes without requiring a file read
- Version comes from source detection, not brief default

## Single Skill Snippet Template

```markdown
[{skill-name} v{version}]|root: {skill_root}{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top exports with () for functions, comma-separated}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

- **Line 1:** Skill name + version + platform-aware root path — version signals training data staleness
- **Line 2 (IMPORTANT):** Retrieval instruction — always present
- **Line 3 (quick-start):** Anchor pointer to Quick Start section
- **Line 4 (api):** Top exports from metadata.json `exports` array (up to 10, with `()` for functions)
- **Line 5 (key-types):** Anchor pointer + inline summary of most important type/enum values
- **Line 6 (gotchas):** 2-3 most critical pitfalls — derived from T2-future annotations, async requirements, breaking changes

## Stack Skill Snippet Template

```markdown
[{project}-stack v{version}]|root: {skill_root}{project}-stack/
|IMPORTANT: {project}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {2-3 most critical integration pitfalls, inline}
```

## Rules

- **api line**: Top exports from metadata.json `exports` array (up to 10 for Deep tier, up to 5 for all other tiers). Append `()` to function names. Comma-separated.
- **key-types line**: Anchor to `#key-types` section + inline summary (~10 words) of the most important type values
- **gotchas line**: Derived from: T2-future annotations (breaking changes), async requirements, version-specific behavior. If no gotchas available, omit the line.
- **stack line**: Component versions from metadata.json `components` for stack skills
- **integrations line**: Co-import patterns from metadata.json `integrations` for stack skills
- If fewer exports than the limit, list all available
- If no exports data available, omit the api line
- Section anchors must be verified against actual SKILL.md headings during generation. For split-body skills (where `references/` exists and `## Full` headings are stubs), if a heading is missing from SKILL.md, rewrite the anchor to point to the reference file path (preferred). Omit the anchor line only if the heading cannot be found in either SKILL.md or `references/*.md`
- Skill path is relative to project root and uses the IDE's `skill_root` prefix (see **Skill Root Path** above, and the IDE → Context File Mapping table in `managed-section-format.md`)
