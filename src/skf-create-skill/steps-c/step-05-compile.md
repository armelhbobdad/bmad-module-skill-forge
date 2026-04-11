---
nextStepFile: './step-06-validate.md'
skillSectionsData: 'assets/skill-sections.md'
assemblyRulesData: 'assets/compile-assembly-rules.md'
---

# Step 5: Compile

## STEP GOAL:

To assemble the complete skill content from the extraction inventory and enrichment annotations — building SKILL.md sections, context-snippet.md, metadata.json, and references/ content according to the agentskills.io format.

## Rules

- Focus only on assembling content from extraction inventory + enrichment
- Do not include any content without a provenance citation
- Write all compiled artifacts to the staging directory `_bmad-output/{skill-name}/`. Do not write to `skills/` or `forge-data/` — step-07 promotes staged artifacts to their final versioned locations.
- Do not fabricate examples not found in source tests or docs
- Seed `<!-- [MANUAL] -->` markers for future update-skill compatibility

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Data Files

Load `{skillSectionsData}` and `{assemblyRulesData}` completely. These define the agentskills.io-compliant format and detailed assembly rules for all output artifacts.

### 1a. Create Staging Directory

Create `_bmad-output/{skill-name}/` (and `_bmad-output/{skill-name}/references/`). All artifacts produced in sections 2–7 below are written here:

- `SKILL.md`
- `context-snippet.md`
- `metadata.json`
- `references/*.md`
- `provenance-map.json`
- `evidence-report.md`

This is the `<staging-skill-dir>` referenced by step-06 (`npx skill-check check`, `npx -y tessl skill review`). Step-07 reads from the in-context copies (resynced by step-06 after any `--fix` modifications) and writes to the final versioned layout.

### 1b. Signature Fidelity Rule

**When assembling function signatures, parameter lists, and return types in any SKILL.md section or reference file:**

- **T1 provenance-map entries (AST-extracted) are authoritative** for: function name, parameter names, parameter types, parameter order, return type, and optionality markers (e.g., `?`, `Optional`, `= default`).
- **T2 (QMD-enriched) and T3 (doc-derived) sources may ADD** contextual descriptions, usage notes, behavioral documentation, and examples to function entries, but **MUST NOT REPLACE** structural signature data from T1 entries.
- **On conflict:** If a T2/T3 source provides a different signature than the T1 extraction for the same export (e.g., different parameter count, different types, missing `Partial<>` wrapper), keep the T1 signature and log a warning in the evidence report: "Signature conflict for `{export_name}`: T1 shows `{t1_signature}`, T2/T3 shows `{other_signature}`. T1 used as authoritative."
- **`signature_source` field:** Record `signature_source: "T1" | "T1-low" | "T2" | "T3"` in each provenance-map entry to indicate the highest-confidence tier that contributed the structural signature data (params, return_type). This enables test-skill to verify signature provenance.

This rule applies to ALL sections including Tier 1 Key API Summary, Tier 2 Full API Reference, and Section 4b Migration & Deprecation Warnings.

### 2. Build SKILL.md Content

Assemble each section in order using the assembly rules data file (`{assemblyRulesData}`). The data file specifies frontmatter format, Tier 1 section details (Sections 1-8, including conditional Section 7b for scripts/assets), Tier 2 section details (Sections 9-11), and assembly ordering rules. Follow it exactly. Assemble Section 7b (Scripts & Assets) only if `scripts_inventory` or `assets_inventory` is non-empty.

### 2a. Description Sanitization Pass

**Before writing SKILL.md frontmatter to disk**, scan the assembled `description` string for angle-bracket tokens and substitute them. This prevents `skill-check` and `tessl` deterministic validators from rejecting the description as containing XML tags (which fails the review with 0% description score).

**Detection:** match any substring of the form `<token>` where ALL of these conditions hold:

1. `token` contains only letters, digits, hyphens, underscores, or dots (e.g., `<name>`, `<component-id>`, `<file.ts>`).
2. The character immediately before `<` is NOT an ASCII letter or digit. This excludes TypeScript / C++ / Rust generics such as `Array<T>`, `Promise<string>`, `Vec<u8>` where the `<` is attached to an identifier. Inline generics are NOT XML tags — validators do not reject them — and wrapping them in backticks would corrupt the surrounding prose into broken markdown.
3. The token does not contain whitespace (e.g., `<unsigned int>` is a type expression, not a placeholder — skip).
4. The angle-bracket substring is NOT already inside a backtick span (`` `...` ``). Backticks already protect the content from XML-tag parsing. Example: `` `npx foo add <name>` `` is safe as-is.

**Anchor positions where the rule IS intended to match:** start of the description, after a space, after punctuation (`.`, `,`, `;`, `:`, `(`, `[`, `/`, `-`, newline). These are the positions where a standalone placeholder token typically appears.

**Anchor positions where the rule is NOT intended to match:** immediately after a word character (generics position). This is the discriminator between "standalone `<name>` placeholder" and "inline `Array<T>` generic."

**Substitution:**

For each match that passes the detection rules above, wrap the entire angle-bracket token in backticks: `<name>` → `` `<name>` ``. This is the only substitution — no uppercase renaming, no curly-brace conversion. The backtick form preserves visual intent and is invariant under future tessl / skill-check rule changes (backticked content is always literal).

Perform this pass on the final assembled description in context before it is written to `SKILL.md`. Record the count of substitutions (if any) in context as `description_sanitizations: {count}` for the evidence report.

**Rationale:** The LTS-stable guarantee is that no angle-bracket token reaches step-06 validation. The assembly rules in `{assemblyRulesData}` define this as a drafting rule; this step makes it an enforced pass so authors and reviewers don't have to remember it. See the description rule in `{assemblyRulesData}` for the full rationale.

### 3. Build context-snippet.md Content

Vercel-aligned indexed format for CLAUDE.md managed section (~80-120 tokens):

```markdown
[{skill-name} v{version}]|root: skills/{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top exports with () for functions, comma-separated}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

**Derivation rules:**

- **version**: From source detection (reconciled in step-03), not brief default
- **api**: Top 10 exports from extraction inventory, append `()` to function names
- **key-types**: Inline summary of most important enum/type values from Key Types section
- **gotchas**: Derived from T2-future annotations (breaking changes), async requirements, version-specific behavior changes. If no gotchas available, omit the gotchas line.
- **Section anchors** (`#quick-start`, `#key-types`): Must match actual heading slugs in the assembled SKILL.md

### 4. Build metadata.json Content

Following the structure from the skill-sections data file:
- Populate all fields from brief_data, extraction inventory, and tier
- Set `generation_date` to current ISO-8601 timestamp
- Set `source_commit` from resolved source (if available)
- Set `source_ref` from resolved source ref (tag name, branch, or `HEAD`; null if unavailable)
- Set `stats` from extraction aggregate counts:
  - `exports_documented`: count of exports with documentation in the assembled SKILL.md
  - `exports_public_api`: count of exports from public entry points (`__init__.py`, `index.ts`, `lib.rs`, or equivalent) — derive this from step-03's entry-point validation (section 4b), NOT from the provenance-map entry count (which may be incomplete if extraction patterns missed some export types)
  - `exports_internal`: count of all other non-underscore-prefixed exports (internal modules, helpers, adapters)
  - `exports_total`: `exports_public_api` + `exports_internal`
  - `public_api_coverage`: `exports_documented / exports_public_api` (1.0 when all public API exports are documented; `null` if `exports_public_api` is 0)
  - `total_coverage`: `exports_documented / exports_total` (may be low for large codebases — this is expected; `null` if `exports_total` is 0)
- Set `description` from the SKILL.md frontmatter `description` field (already assembled in section 2)
- Set `language` from source analysis (e.g., `"typescript"`, `"python"`) — use the primary language of the entry point file
- Set `ast_node_count` from extraction stats if ast-grep was used (Forge/Deep tier), otherwise omit
- Set `tool_versions` based on tier and available tools. Resolve `{skf_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `{project-root}/_bmad/skf/package.json` → read `.version` field
  2. `node -p "require('./node_modules/bmad-module-skill-forge/package.json').version"`
  3. `{project-root}/_bmad/skf/VERSION` → read plain text file (single line containing version string, written by the SKF installer)
  4. `"unknown"` (final fallback — add a warning to the evidence report)
  Never hardcode the version.
- Resolve `{ast_grep_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `ast-grep --version` → parse version string from output (e.g., `ast-grep 0.41.1` → `"0.41.1"`)
  2. `mcp__ast-grep__find_code` tool metadata (if version is exposed by the MCP server)
  3. `"unknown"` (final fallback — add a warning to the evidence report)
- Resolve `{qmd_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `qmd --version` → parse version string from output (e.g., `qmd 2.0.1` → `"2.0.1"`)
  2. `mcp__plugin_qmd-plugin_qmd__status` → parse version if exposed in status output
  3. `"unknown"` (final fallback — add a warning to the evidence report)
  Note: QMD is a Bun/Node package (`@tobilu/qmd`). Install via `bun install -g @tobilu/qmd`.
- Store `commit_short` = first 8 characters of `source_commit` (or `"unknown"` if unavailable) for use in step-08 report.
- If `scripts_inventory` is non-empty, populate `scripts[]` array and set `stats.scripts_count`. If `assets_inventory` is non-empty, populate `assets[]` array and set `stats.assets_count`. Omit these fields entirely when inventories are empty.

### 5. Build references/ Content

Create one reference file per major function group or type:
- Full function signatures with detailed parameter descriptions
- Complete usage examples (from source only)
- Related functions cross-references
- Temporal annotations (Deep tier: T2-past, T2-future)

Group functions logically by module, file, or functional area.

### 6. Build provenance-map.json Content

One entry per extracted export: export_name, export_type, params[] (typed strings), return_type, source_file, source_line, confidence tier (T1/T1-low/T2), extraction_method, ast_node_type, signature_source ("T1"|"T1-low"|"T2"|"T3" — indicates which tier contributed the structural signature).

**File entries** — emit one `file_entries[]` row per tracked non-code file when any of these inventories are non-empty:

- `scripts_inventory` → `file_type: "script"`, `extraction_method: "file-copy"`, stored in `{skill_package}/scripts/` by step-07
- `assets_inventory` → `file_type: "asset"`, `extraction_method: "file-copy"`, stored in `{skill_package}/assets/` by step-07
- `promoted_docs` (from step-03 §2a) → `file_type: "doc"`, `extraction_method: "promoted-authoritative"`, **NOT** copied into the skill package by step-07. The source file stays at its original path; only the provenance tracking entry is written. `content_hash` was pre-computed by §2a.

Each `file_entries[]` row has the same shape regardless of `file_type`: `{file_name, file_type, source_file, content_hash, confidence, extraction_method}`. See `{skillSectionsData}` for full schema and the canonical list of `file_type` values.

### 7. Build evidence-report.md Content

Compilation audit trail: generation date, forge tier, source info, tool versions, extraction summary (files/exports/confidence), warnings. For validation-specific fields (Schema, Body, Security, Content Quality, tessl, Metadata), insert the placeholder text `[PENDING — populated by step-06]`. Step-06 will replace these placeholders with actual results. See `{skillSectionsData}` for full template. Use the same `{skf_version}` value resolved in section 4 when populating the Tool Versions block.

### 8. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After all content is assembled in context and written to the staging directory, immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed assembly step with no user choices
- All content must be both in context and in `_bmad-output/{skill-name}/` — no final files in `skills/` or `forge-data/` yet
- Proceed directly to validation after assembly is complete

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all 6 content artifacts (SKILL.md, context-snippet.md, metadata.json, references/, provenance-map.json, evidence-report.md) are assembled in context AND written to the staging directory `_bmad-output/{skill-name}/` will you proceed to load `{nextStepFile}` for spec validation. Note: extraction-rules.yaml is generated by step-07 from extraction data, not assembled here.

