# Reference-App Assembly Overrides

When `scope.type: "reference-app"` in the brief, apply these overrides to the standard assembly of `assets/compile-assembly-rules.md`. The skill's value is an integration pattern (wiring), not a library surface: the default library-export template would force assemblers to remap wiring onto export slots and produce fuzzy counts. These overrides give that value a first-class home.

**Section 4 (Key API Summary), Pattern Surface override:**

Replace the per-function table with an ordered list of wiring steps. Each step names a file, a surface (decorator, build field, lifecycle hook, config key), and a one-line description of what the user does there, not a function signature. The goal is that a reader copying the pattern can follow the list in order.

```markdown
## Pattern Surface

| # | File | Surface | Purpose |
|---|------|---------|---------|
| 1 | {src/main.py} | {@app.startup decorator} | {brief wiring purpose} |
| 2 | {electron.vite.config.ts} | {build.copy field} | {brief wiring purpose} |
| … | … | … | … |
```

Source: the authored pattern surface from extraction + brief `scope.tier_a_include` (when present) or the curated provenance-map entries (when absent). Provenance: cite the originating source files.

**Section 3 (Common Workflows), Adoption Steps override:**

Replace the function-call-chain format with copy-this-wiring narrative. Prefer numbered imperative steps that the user can execute in order, not an API-call sequence. Keep each step's code snippet minimal (5–15 lines): full wiring lives in Tier 2.

```markdown
## Adoption Steps

1. **{Step name}** {an em dash} {one-line description}
   ```{language}
   {minimal wiring snippet}
   ```
2. **{Step name}** {an em dash} {one-line description}
   …
```

**Tier 2 (Full API Reference), pattern-oriented override:**

Replace per-function subsections with `references/pattern-*.md` groupings: one reference file per coherent wiring concern (e.g. `pattern-lifecycle.md`, `pattern-build-config.md`, `pattern-ipc.md`). Each reference file covers every file/surface touched by that concern with full code snippets, gotchas, and provenance. Tier 1 (Pattern Surface) stays index-like; Tier 2 carries the copy-paste-able depth.

**metadata.json, Reference-App stats semantics:**

`stats.exports_documented` is a **library concept** and does not carry over cleanly. When `scope.type: "reference-app"`:

- `stats.exports_documented` MAY be set to the Pattern Surface row count as a proxy, but its semantics change: it counts authored pattern surfaces, not public exports. Emit an adjacent `stats.pattern_surfaces_documented` with the same integer so downstream consumers (test-skill, feasibility, discovery) can discriminate.
- `exports_public_api` / `exports_internal` / `exports_total` are not meaningful for a reference app: omit them, or set all three to the Pattern Surface count with a note in `stats.notes`: `"reference-app: export counts are pattern-surface proxies, not library exports"`.
- Do not fabricate signature / type-coverage data from pattern surfaces. skf-test-skill skips those categories when metadata flags a reference-app (`referenceApp`, the same skip path as `stackSkill`; its `scripts/compute-score.py` redistributes their weights).
- Do not emit `effective_denominator` for reference-app scope (its `effective_denominator_decision` never stores one): `effective_denominator` counts public exports from the authoring-surface barrel, a library concept that `pattern_surfaces_documented` already replaces here: pattern-surface coverage is the reference-app basis, and skf-test-skill skips library-export coverage for it.

**Language / spec-reference sub-shape:** A reference app that documents an engine- or spec-versioned **language** (a query language, grammar, or DSL, e.g. SurrealQL @ SurrealDB, whose value is construct idioms rather than wiring or exports) is a recognized reference-app sub-shape. Keep `scope.type: "reference-app"` (there is no separate enum value), so every carve-out above applies unchanged (`pattern_surfaces_documented` proxy, no `effective_denominator`, test-skill signature/type skip). Adapt the three overrides to the language's surface instead of app wiring:

- **Section 4 (Pattern Surface)** becomes a **construct-area map**, not a wiring list. Each row is a language construct area, where it lives in the source, and what the user writes there:

  ```markdown
  ## Pattern Surface

  | # | Construct Area | Where in Source | Purpose |
  |---|----------------|-----------------|---------|
  | 1 | {statements / DDL} | {sql::statements} | {what the user writes} |
  | 2 | {operators} | {sql::operator} | {…} |
  | … | … | … | … |
  ```

- **Section 3 (Adoption Steps)** becomes **production-task workflows**: ordered tasks a user performs *in the language* (define a schema, write a query, call a built-in function), each with a minimal snippet, not a copy-this-wiring narrative.
- **Tier 2** groups `references/*.md` by **language concern** (e.g. `statements.md`, `functions.md`, `types.md`), one file per construct family, instead of `pattern-*.md` wiring concerns.
- **metadata.json:** `pattern_surfaces_documented` counts the documented construct areas; the no-`effective_denominator` carve-out applies (a language has no export barrel). The brief's `language` field records the **documented** language (e.g. `surrealql`), which may differ from the source language it was extracted from (e.g. `rust`): see `skf-analyze-source/assets/skill-brief-schema.md`.

**When this clause does not apply:** `full-library`, `specific-modules`, `public-api`, `component-library`, or `docs-only`. Those scope types have their own assembly semantics and export-count conventions: do not mix.
