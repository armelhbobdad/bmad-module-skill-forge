# Context Snippet Format (Vercel-Aligned Indexed Format)

## Skill Root Path

The snippet `root:` path must reflect the IDE's actual skill directory — its `skill_root` from the IDE → Context File Mapping table in `managed-section-format.md`. Each IDE has its own skill directory (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`).

The root path in context-snippet.md on disk uses the **`skill_root` of the first entry in `target_context_files`** (resolved in step 1 from config.yaml IDE mapping). When assembling managed sections for other context files, step 4 rewrites root paths to match the target context file's skill root.

**Authoring-repo override:** If `snippet_skill_root_override` is set in `config.yaml`, or for one run by step 1's snippet-root option (d), it replaces the IDE-mapped value for snippet generation and becomes every row's root in step 4. See the "Resolution rules" section in `managed-section-format.md` for the full semantics.

**A house-style copy** of this file (`snippet_format_path` in `customize.toml`) keeps the lines scripts parse: line 1 with its `root:` field, line 2's `|IMPORTANT:` start and skill name, the `|gotchas:` label with its `[CARRIED]` marker, and no bare `|` line. That setting's comment says which script reads each one.

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
- **Line 4 (api):** The ranked exports (see the api line rule below), with `()` for functions
- **Line 5 (key-types):** Anchor pointer + inline summary of most important type/enum values
- **Line 6 (gotchas):** At most 3 pitfalls, separated by `; `, derived from the current sources (see the gotchas line rule below)

## Stack Skill Snippet Template

```markdown
[{project}-stack v{version}]|root: {skill_root}{project}-stack/
|IMPORTANT: {project}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {2-3 most critical integration pitfalls, inline}
```

## Rules

- **api line**: Ranked, so the line stays the same from export to export: the prior snippet's `|api:` names in order, then the names of SKILL.md's `## Key API Summary` rows in row order (a component library's `## Component Catalog` rows, a reference app's `## Pattern Surface` rows), then metadata.json `exports` in order. A row's name is matched without backticks, a module qualifier or generic parameters, and a cell naming several is split on `/`. Each name once, only when `exports` lists it, and never one the current SKILL.md marks deprecated or removed (a deprecation, migration or breaking-changes bullet gives it as the old name, or its Key API Summary row's purpose says deprecated or removed). The first 10 for Deep tier, 5 for all other tiers; above the 300-token ceiling, names drop from the end. Append `()` to a name whose provenance `export_type` is a function, or else when the prior `|api:` line wrote it with `()`. Comma-separated.
- **key-types line**: Anchor to `#key-types` section + inline summary (~10 words) of the most important type values
- **gotchas line**: At most 3 pitfalls, separated by `; ` (the separator step 3 splits a prior line on). A pitfall never holds the separator: in every pitfall the line writes, a prior one kept or carried included, a `; ` outside a code span is written as `, ` (a code span keeps its `; `). Derived from the current sources: a T2-future annotation in the evidence report (breaking changes, async requirements, version-specific behavior); the current SKILL.md, through a bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections, a `## Key API Summary` row whose purpose says deprecated or removed, and an async requirement its Quick Start shows; and a prior pitfall, already carried or not, that a T2-future annotation states or that the current SKILL.md still says anywhere (its frontmatter description and its whole body), kept in its prior wording without the `[CARRIED]` marker. SKILL.md says a pitfall when it states the pitfall's main claim (what to do or avoid, with any version or name the pitfall gives) in SKILL.md's own words. New gotchas come only from the evidence report's T2-future annotations and those SKILL.md places: a gotchas-type section's bullets, a deprecated or removed `## Key API Summary` row and an async requirement the Quick Start shows. A pitfall that joins several pitfalls, such as a value step 3 reads whole, is still stated only when one T2-future annotation or one of those bullets, rows or Quick Start calls states it whole, not when SKILL.md states its pitfalls only apart or only in other prose, and a prior pitfall one of those states is written once, never also as a new gotcha. The prior pitfalls still stated come first, in their prior order, then the new ones in source order. `[CARRIED]` marks only a prior pitfall no current source backs, which takes a free slot for one export (one-cycle expiry). If no gotchas are available, omit the line.
- **stack line**: Component versions from metadata.json `components` for stack skills
- **integrations line**: Co-import patterns from metadata.json `integrations` for stack skills
- If fewer exports than the limit, list all available
- If no exports data available, omit the api line
- Section anchors must be verified against actual SKILL.md headings during generation. Keep `SKILL.md#{slug}` when SKILL.md has the heading. Only when SKILL.md lacks it and the skill is split-body (`references/` exists and the `## Full` headings are absent or stubs; not a stack skill's structural references), point the anchor at the `references/{file}.md#{slug}` that holds it. Omit the anchor line when neither SKILL.md nor `references/*.md` holds the heading
- Skill path is relative to project root and uses the IDE's `skill_root` prefix (see **Skill Root Path** above, and the IDE → Context File Mapping table in `managed-section-format.md`)
