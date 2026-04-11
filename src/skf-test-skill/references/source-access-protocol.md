# Source Access Protocol

## Source API Surface Definition

**Source API surface** = the package's top-level public exports. These are the symbols reachable from the primary entry point without importing internal modules:

- **Python:** symbols exported in `__init__.py` (including re-exports) — exclude private (`_prefixed`) names
- **TypeScript/JavaScript:** named exports from `index.ts` / `index.js` — exclude unexported locals
- **Go:** exported identifiers (capitalized) from the package's public-facing files
- **Rust:** items in `pub use` from `lib.rs` or `mod.rs`
- **Empty-barrel packages (copy-paste / subpath-only distribution):** If the primary entry point is empty or re-exports nothing (e.g., `export {};` in `index.ts`, an empty `__init__.py`, `lib.rs` with no `pub use`), the package does not expose a barrel API. Do **not** compute coverage against the empty barrel — the denominator would be zero and the score meaningless. Instead, consult the skill brief's `scope.include` globs (`forge-data/{skill_name}/skill-brief.yaml`) to identify the authorized entry points, and build the public API surface from the **union of named exports across those files**. The skill brief's `scope.notes` field should document this distribution model explicitly; if present, treat it as confirmation that the empty barrel is by design rather than a bug. If no skill brief is available and the barrel is empty, set `analysis_confidence: docs-only` and report that the source API surface could not be determined.

- **Stratified-scope monorepo packages (curated subsets of multi-package repos):** If the source is a monorepo (detect via `packages/` layout, `workspaces` field in root `package.json`, `lerna.json`, `rush.json`, `nx.json`, or Cargo `[workspace]`) AND the skill brief's `scope.include` lists a curated file/directory subset rather than the full workspace, the coverage denominator must reflect only the authored surface, not the monorepo's global export count. This is distinct from the empty-barrel case: each workspace package may have a non-empty barrel, but the skill intentionally documents only a tiered subset.

  **Resolution order:**

  1. **Prefer `metadata.json.stats.effective_denominator`** when present. `skf-create-skill` step-05 §4 writes this field for stratified-scope skills. When set, use it directly as the `exports_public_api` count for coverage scoring.
  2. **Fall back to live re-derivation** when `effective_denominator` is absent (older skills, quick-tier output, or skills compiled before this rule existed). Read the brief's scope globs from `forge-data/{skill_name}/skill-brief.yaml`, resolve them against `source_path`, filter out files matching `scope.exclude`, and compute the source API surface as the **union of named exports across the matched files only**. The skill brief's `scope.notes` field should document the stratification strategy (e.g., "Tier A: fully documented; Tier B: deferred to references; Tier C: excluded") — when present, treat it as confirmation that the curated subset is by design, not a scope gap.

     **Honor `scope.tier_a_include` when present.** When re-deriving, prefer the brief-level `scope.tier_a_include` narrow include list over the coarse `scope.include`. `tier_a_include` is an optional brief field that lists only the authoring surface the brief actually intends to document (tier A), letting the denominator match the brief's authoring-vs-installing intent even when `scope.include` uses coarse globs that also match internal infrastructure. When `tier_a_include` is present, resolve its globs (still filtered by `scope.exclude`), compute the union across those files, and use that count as the denominator. When absent, fall back to resolving `scope.include`.

  3. **Denominator inflation check (absent `tier_a_include`).** If re-derivation used `scope.include` because no `tier_a_include` was provided, compare the resulting union count against the provenance-map entry count (when provenance-map exists). If the `scope.include` union is more than 25% larger than the provenance-map entry count, the coarse globs are almost certainly sweeping in internal infrastructure that the brief did not intend to document. Emit a **Medium**-severity gap titled `denominator inflation — coarse scope.include union exceeds authored surface` that points the user at the brief for rescoping via `scope.tier_a_include`. Report both counts (`scope.include union: {N}`, `provenance-map entries: {M}`, `{percent}% inflation`) and state that the coverage score it produced is driven by denominator inflation rather than documentation gaps. The check is skipped when provenance-map is unavailable (there is no baseline to compare against).

  Leave `analysis_confidence` unchanged (still `full` or `provenance-map` per the waterfall) — stratified scope does not degrade confidence, only the denominator. Annotate the coverage report with: `Stratified scope — denominator: {effective_denominator | tier_a_include union | scope.include union} ({N} files matched, {M} exports union)`.

  **When this clause does NOT apply:** `scope.type: "full-library"` skills, single-package repositories, or stratified briefs where the full monorepo is intentionally in scope. For those, use the standard barrel-based denominator.

Internal module symbols are **excluded** from the coverage denominator unless they are explicitly documented in SKILL.md (in which case they count as documented extras, not missing coverage).

This matches the extraction-patterns.md convention used during skill creation: coverage measures how well SKILL.md documents what users actually import, not the entire internal codebase.

## Source Access Resolution

Before analysis, determine source access level. Walk through these states in order — use the first that succeeds:

**State 1 — Local source available:**
Check if `{source_path}` (from metadata.json `source_root`) exists on disk. If yes → full analysis at detected tier (AST + signatures). Set `analysis_confidence: full`.

**State 2 — Local absent, provenance-map exists:**
Check `{forge_data_folder}/{skill_name}/provenance-map.json`. If present AND contains at least 1 entry, use it as the baseline export inventory — each entry contains structured fields: `export_name`, `export_type`, `params[]`, `return_type`, `source_file`, `source_line`, `confidence`, and `ast_node_type`. Cross-reference against SKILL.md documented exports for name-matching and param-by-param coverage. Signature verification compares SKILL.md's documented params/return types against provenance-map entries directly.

**Cross-reference with metadata.json:** After loading provenance-map entries, compare the entry count against `metadata.json`'s `exports[]` array length and `stats.exports_public_api` count. If metadata reports more exports than provenance-map entries:
- Compute `gap = metadata.exports.length - provenance_map.entries.length`
- Report: "Provenance-map contains {pmap_count} entries but metadata.json lists {meta_count} exports ({gap} gap). Coverage denominator uses the union."
- Build the coverage denominator from the **union** of provenance-map entry names and metadata.json `exports[]` names. Exports present in metadata but absent from provenance-map are counted as "missing documentation" in the coverage calculation.
- If metadata.json is unavailable or has no `exports[]` array, use provenance-map count alone with a note: "Coverage denominator is provenance-map only — may undercount if extraction was incomplete." If remote reading tools are available (zread, deepwiki, gh API, or similar), supplement by reading the entry point file for live signature verification. Set `analysis_confidence: provenance-map`.

**State 2 limitations:** Signature verification at State 2 is **string comparison only**, not semantic. Provenance-map stores parameters as flat string arrays (e.g., `["data: Union[BinaryIO, list, str]"]`), so `str` vs `String` or `list` vs `List[Any]` would be treated as mismatches even when semantically equivalent. For full type-aware verification (handling type aliases, generic equivalence), State 1 (local source) with AST re-parsing is required. When the SKILL.md was compiled from the same provenance-map (typical for create-then-test flows), most strings will match. However, enrichment (step-04) and doc-fetching (step-03c) during compilation may alter parameter descriptions, add type annotations, or normalize signatures, causing mismatches even in create-then-test flows. Expect some string-level mismatches and treat them as compilation artifacts, not source drift signals, until signature fidelity is enforced by step-05's Signature Fidelity Rule (see `signature_source` field in provenance-map entries).

**State 3 — No provenance-map, metadata exports exist (quick-skill path):**
If no provenance-map.json exists (typical for quick-skill output), fall back to `metadata.json`'s `exports[]` array for the export name list. Coverage check becomes a self-consistency comparison: are all names in `exports[]` documented in SKILL.md with description, parameters, and return type? Signatures cannot be verified. If remote reading tools are available, supplement by reading the entry point for live export comparison. Set `analysis_confidence: metadata-only`.

**State 4 — No local source, no forge-data, remote tools available:**
If neither provenance-map nor metadata exports provide a usable baseline, but remote reading tools (zread, deepwiki, gh API, or similar) are available and `source_repo` is set in metadata.json, read the entry point remotely to build the export inventory from scratch. Name-matching only — no AST. Set `analysis_confidence: remote-only`.

**State 5 — No source access at all:**
If none of the above succeed, fall through to docs-only mode (as defined in step-03-coverage-check.md Section 0: pre-analysis source type detection). Set `analysis_confidence: docs-only`. Warn: "**No source access available.** Coverage check evaluates documentation self-consistency only. Re-run with local clone or remote access for source-backed verification."

Set `analysis_confidence` in context for use in Section 2 analysis depth, step-05 output, and step-05 scoring.

**Confidence tier mapping:** `full` = T1, `provenance-map` = T1, `metadata-only` = T1-low, `remote-only` = T1-low, `docs-only` = T3. This aligns with the T1/T1-low/T2/T3 scale used across all SKF workflows.

**Degradation notice rules:** When `analysis_confidence` is `provenance-map`, check the `confidence` field of provenance-map entries before emitting a degradation recommendation:

- **All/most entries T1 (AST-verified):** The provenance-map data is already at highest confidence. Do NOT recommend re-running with a local clone — it would produce identical results. Use: "Resolved via: provenance-map (T1 AST-verified at compilation time). Local clone not required — provenance data is already at highest confidence."
- **Mixed T1/T1-low entries:** Report the breakdown. Recommend local clone only for the T1-low entries: "Resolved via: provenance-map ({n} T1, {m} T1-low). Re-run with local clone to upgrade T1-low entries to full AST verification."
- **All/most entries T1-low or lower:** Keep the standard recommendation: "Re-run with local clone for full AST-backed verification."
