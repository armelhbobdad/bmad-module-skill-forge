# SKILL.md Compilation Assembly Rules

## Frontmatter (agentskills.io compliance)

```yaml
---
name: {brief.name}
description: >
  {Trigger-optimized description from brief and extraction data.
  Include what it does, when to use it, and what NOT to use it for.
  1-1024 chars, optimized for agent discovery.}
---
```

**Frontmatter rules:**

- `name`: lowercase alphanumeric + hyphens only, must match the skill output directory name. Prefer gerund form (`processing-pdfs`, `analyzing-spreadsheets`) for clarity.
- `description`: non-empty, max 1024 chars, optimized for agent discovery. Use third-person voice ("Processes Excel files..." not "I can help you..." or "You can use this to...") and include a trigger phrase so agents know when to match. **The description must contain a literal `Use when` clause somewhere** — `skill-check`'s `description.use_when_phrase` rule tests for that exact phrase anywhere in the string, so `Triggers on …` or `Reach for this when …` on their own score below 100 with a `description should contain "Use when" phrasing` warning. The lead is still free: a descriptive opener followed by a `Use when …` clause (`Charts and visualizations powered by D3.js. Use when plotting data …`) passes cleanly, and the other two phrases are fine as *additional* text. When using `Use when `, follow with a **gerund** (`Use when building/processing/analyzing X…`) or a noun-phrase clause (`Use when the user requests to "X"`); never a bare indicative verb like `builds`/`processes`, because `skill-check --fix` will prepend a literal `Use when ` to a description missing the trigger phrase, producing ungrammatical output (`Use when builds X…`). Inconsistent point-of-view or a missing trigger phrase causes discovery problems since the description is injected into the system prompt. See `skf-brief-skill/assets/description-voice-examples.md` for the canonical voice palette.
- **The `description` cannot contain angle brackets** — neither standalone placeholders like `<name>`, `<component>`, `<path>`, nor inline generics like `` `Array<T>` `` or `` `Meta<typeof X>` ``. The Claude platform does not accept a skill description that contains XML tags, and the description is read as a raw string, so backticks do not protect content here. No validator SKF runs catches this (skill-check has no such rule and Tessl Review accepts angle brackets), so SKF enforces it itself. When the natural phrasing would use angle brackets:
  - Prefer the curly-brace form in prose: `{name}`, `{component-id}`, `{path}` — readable and free of angle brackets.
  - Uppercase placeholders are also acceptable: `NAME`, `COMPONENT_ID`.
  - For code-ish fragments, use curly braces in place of angle brackets inside the backticks: `` `Meta{typeof X}` ``, `` `Array{T}` ``.

  Step 5 §2a enforces it on the SKILL.md it writes, and step 6 §6 checks it again. The rule holds only for the `description`: the body, code examples and reference files keep their angle brackets, since they are read as Markdown, where backticks do protect content.
- Only `name` and `description` in frontmatter — `version` and `author` go in metadata.json
- No other frontmatter fields for standard skills (only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted by spec)

## Two-Tier Assembly

**Two-tier assembly.** SKILL.md must retain actionable inline content that survives `split-body` extraction. Assemble Tier 1 sections first (always inline), then Tier 2 sections (reference-eligible, may be extracted by split-body).

### Tier 1 — Always Inline (must survive split-body)

These sections form the essential standalone body. Target: **under 300 lines total** for Tier 1. An agent loading only SKILL.md (without references) must get enough to act.

**Section 1 — Overview (~10 lines):**
- 1-line summary of what the library does
- Source repo, version, branch
- Forge tier used for compilation
- Export count and confidence summary

**Section 2 — Quick Start (~30 lines):**
- Select the 3-5 most commonly used functions (by import frequency or documentation prominence)
- One runnable code example showing a typical end-to-end flow (e.g., `add → process → search`)
- Minimal usage examples — ONLY from source tests or official docs
- If no examples exist in source, show signature-only quick start
- Provenance citation for each function

**Section 3 — Common Workflows (~30 lines):**
- 4-5 patterns showing typical function call sequences
- Each pattern: 1-line bold description + function call chain with key params
- Focus on the most common developer tasks, not exhaustive coverage
- Format example:
  ```
  **Add and process data:**
  `await cognee.add(data) → await cognee.cognify() → await cognee.search(query)`
  ```

**Section 4 — Key API Summary (~20 lines):**
- Table of top 10-15 functions: name, purpose, key parameters
- One row per function — no full signatures, just enough for discovery
- Provenance citation per function

**Section 4b — Migration & Deprecation Warnings (~10 lines, Deep tier only):**
- Emit the heading verbatim as `## Migration & Deprecation Warnings`. Downstream gates match that exact text, so a naturally-retitled section (`## Deprecations & pre-1.0 hazards`, `## v2 → v3 breaking changes`) is reported as *missing* while its bullets are re-emitted as duplicate `## CORRECTION` blocks.
- Only populated when step 4 enrichment produced **T2-future** annotations (deprecation warnings, breaking changes, planned renames)
- List each warning as a single-line bullet: function name, what changed or will change, source citation
- Max 10 lines — just the actionable warnings, not full context
- Link to Tier 2 Full API Reference for details: "See Full API Reference for migration details."
- **Skip entirely** for Quick/Forge tiers or when no T2-future annotations exist — do not emit an empty section
- This section survives split-body, ensuring agents always see critical migration context

**Section 5 — Key Types (~20 lines):**
- Most important enum/type definitions inline (e.g., SearchType values, config options)
- Only types that appear in Quick Start or Common Workflows
- Full type details go in Tier 2

**Section 6 — Architecture at a Glance (~10 lines):**
- Bullet list of major subsystem categories (e.g., "Graph DBs: Neo4j, Kuzu, Neptune")
- Adapter/driver overview — what's available, not how it works
- Skip for Quick tier or small libraries with < 5 modules

**Section 7 — CLI (~10 lines, if applicable):**
- Basic CLI commands if the library has a CLI interface
- Skip if no CLI exists

**Section 7b — Scripts & Assets (~10 lines, if applicable):**
- Manifest table of included scripts with filename, one-line purpose, and provenance citation
- Manifest table of included assets with filename, one-line purpose, and provenance citation
- Each entry: `scripts/{filename}` or `assets/{filename}`, purpose, `[SRC:{source_path}:L1]`
- Include a note: "Load scripts from `scripts/` and assets from `assets/` when directed by the instructions above."
- **Skip entirely** when no scripts or assets detected in extraction inventory — do not emit an empty section
- Like Sections 4b and 7, parsers must treat this section as optional

**Section 8 — Manual Sections:**
- Seed empty `<!-- [MANUAL] -->` markers:
```markdown
<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->
```
- Place after Quick Start and after Key API Summary sections
- **Carry an earlier build's blocks.** Step 7 replaces an earlier build of this version whole, so when `{skills_output_folder}/{name}/{version}/{name}/SKILL.md` exists (`{version}` with build metadata stripped, as step 7 §1 does), carry its hand-written blocks into this SKILL.md. A block runs from `<!-- [MANUAL:<id>] -->` to the first `<!-- [/MANUAL:<id>] -->` after it, and it is hand-written unless it holds nothing but whitespace or the seeded note above (a note of the user's own in an HTML comment is hand-written). Put each hand-written block's interior, byte for byte, in place of the seeded note of the marker with its id, and append a block whose id has no marker here at the end of this section. Step 6 then validates SKILL.md with the blocks in, and step 7's promotion checks each one arrived and carries the earlier build's `scripts/[MANUAL]/` and `assets/[MANUAL]/` files. When the earlier build holds a hand-written block or such a file, record the decision: stage `{"step": "compile", "gate": "manual-carry-forward", "decision": "carry", "rationale": "<the earlier build's folder, its block ids and its [MANUAL]/ files>"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.

### Tier 2 — Reference-Eligible (can be extracted by split-body)

Assemble Sections 9-11 (Full API Reference, Full Type Definitions, Full Integration Patterns) as defined in the skill-sections data file, for the exports the provenance map holds. These contain full detail and are split into `references/` when the body exceeds 500 lines. Include T2 annotations from enrichment in the Full API Reference (Deep tier only).

**Tier 2 differentiation from Tier 1:** Tier 2 Full API Reference must contain content that is not present in Tier 1's Key API Summary. Specifically:

- **Full parameter tables** with types, defaults, and required/optional flags (Tier 1 only lists key params)
- **Return value details** including structure, types, and error conditions
- **T2 temporal annotations** — migration notes, deprecation details, breaking change context (Deep tier)
- **Usage examples** from source tests or documentation (Tier 1 has signature-only references)
- **Edge cases and constraints** — parameter validation rules, size limits, behavioral notes

Do not repeat Tier 1's name/purpose/key-params table format in Tier 2. Tier 2 is a deep reference, not a reformatted summary.

### Assembly Rules

1. Assemble all Tier 1 sections first — these form the essential standalone body
2. Assemble all Tier 2 sections after — these are progressive disclosure detail
3. Tier 1 content stays under 300 lines (excluding frontmatter)
4. If Tier 1 alone exceeds 300 lines, reduce Key API Summary and Architecture at a Glance
5. Tier 1 sections are kept short enough that `split-body` targets the larger Tier 2 sections (`## Full ...` headings) instead
6. After split-body, SKILL.md must still contain all Tier 1 sections with actionable content
7. **Signature fidelity:** in every section, Tier 1 Key API Summary, Tier 2 Full API Reference and Section 4b Migration & Deprecation Warnings included, and in every reference file, a function's T1 provenance-map entry (AST-extracted) is authoritative for its name, parameter names, parameter types, parameter order, return type and optionality markers (`?`, `Optional`, `= default`): take them from that entry's `params` and `return_type`, never from documentation, README examples or enrichment annotations. T2 (QMD-enriched) and T3 (doc-derived) sources may add descriptions, usage notes, behavioral documentation and examples, never structure. When a T2 or T3 source gives a different signature than the T1 entry for the same export (another parameter count, other types, a missing `Partial<>` wrapper), keep the T1 signature and log in the evidence report: "Signature conflict for `{export_name}`: T1 shows `{t1_signature}`, T2/T3 shows `{other_signature}`. T1 used as authoritative."

### Content Quality Rules

These SKF-specific rules apply to all content assembled in SKILL.md and reference files.

**Zero-hallucination examples:** Include input/output or usage examples ONLY when concrete pairs exist in source tests or official docs — 2-3 such pairs convey the desired style and detail more clearly than a description alone. If no examples exist in source, note the gap rather than fabricating pairs — zero hallucination applies.

**Generic-plus-signature code spans:** When documenting a generic class constructor or factory signature, do not place the generic brackets and the parameter list inside a single inline code span. `skill-check`'s `links.local_markdown_resolves` validator parses `` `ClassName[T](key: str)` `` as a broken markdown link (`[T]` becomes the link text, `(key: str)` becomes the URL) and emits a `broken local link` warning on the Links axis, regardless of the surrounding backticks. This applies to Tier 1 Key Types, Tier 2 Full API Reference, and reference files. Safe alternatives:
- Split into two code spans: `` `ClassName[T]` — dataclass with fields `(key: str, value: int)` ``
- Drop the explicit constructor and describe fields in prose: `` `ClassName[T]` — generic container parameterized by `T`, with field `key: str` ``
- Use the curly-brace substitution used for frontmatter: `` `ClassName{T}(key: str)` `` (readable, avoids both markdown-link and angle-bracket parsing)
