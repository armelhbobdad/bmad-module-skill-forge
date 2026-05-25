<!-- Config: communicate in {communication_language}. -->

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

  1. **Prefer `metadata.json.stats.effective_denominator`** when present. `skf-create-skill` step 5 §4 writes this field for stratified-scope skills. When set, use it directly as the `exports_public_api` count for coverage scoring — **subject to the deflation guard below**.

     **Denominator deflation guard (when `effective_denominator` is used).** `effective_denominator` is a stored count, and a gap-driven `skf-update-skill` run can lower it — legitimately (a real rescope expressed in the brief) or by gaming (deleting in-scope public exports from `metadata`/provenance and setting `effective_denominator` to the documented total to force 100% coverage). When source is readable (State 1, or State ≥ 2 with remote tools), validate it: re-derive the public surface from `scope.include` filtered by `scope.exclude` — the same union step 2 computes — and compare. If the re-derived source barrel exceeds `effective_denominator` by **more than 25%** AND the brief carries no `scope.tier_a_include` (the only legitimate narrowing mechanism), treat `effective_denominator` as **deflated**: use the re-derived source-barrel count as `total_exports` instead, and emit a **Medium**-severity gap `denominator deflation — effective_denominator below source public surface without tier_a_include` reporting both counts (`effective_denominator: {N}`, `re-derived source barrel: {M}`, `{percent}% below source`). A legitimate scope reduction is expressed in the brief — via `scope.tier_a_include`, or by adding the removed exports to `scope.exclude` so the re-derived barrel shrinks to match (the mechanism `skf-update-skill` gap-driven rescope uses) — **never** by editing `metadata.stats` to equal the documented count. This is the directional counterpart to the inflation check in step 3: inflation fires when the coarse surface is too large, deflation when the stored denominator is suspiciously small. When source is unavailable, skip the guard and annotate the report: `effective_denominator used unverified — no source access to re-derive the barrel`.

     **Rust barrel re-derivation (when ast-grep `pub`-fn extraction is unreliable).** The Rust-skill condition documents the ast-grep `pub-fn` extractor as unreliable, so re-deriving a crate's barrel surface — for this guard or for the live fallback below — falls back to grep. A naive `pub`-token sweep over-counts badly: it pulls in `pub(crate)`/`pub(super)` internals, impl-block associated consts and methods, test modules, and foreign re-export files (such sweeps routinely land 30–40% above the true barrel). Enumerate deterministically instead:

     - Trace the `pub use` re-export chain from the crate root (`lib.rs` / `mod.rs`) to find which modules the barrel actually re-exports; count from those, not from every file containing a `pub` token.
     - Count only **unrestricted, module-level (column-0) `pub`** item declarations: `pub struct` / `pub enum` / `pub trait` / `pub type` / `pub const` / `pub fn` (free functions) that start at column 0.
     - Exclude `pub(crate)` / `pub(super)` / `pub(in …)` (crate-internal, not barrel surface); anything indented (impl-block associated consts and methods are not free barrel items); `*tests.rs` and `#[cfg(test)]` modules; and files listed under `scope.exclude` (e.g. foreign re-export files).

     **TypeScript / JavaScript barrel re-derivation (multi-line re-export blocks).** When re-deriving a TS/JS barrel — for the deflation guard above or the live fallback below — a line-oriented `^export` regex undercounts: a named re-export block spans continuation lines (`export type {\n  A,\n  B,\n} from "./x"`), and a single-line match captures only the opening line, dropping every member listed on the continuation lines. Enumerate the full block instead:

     - For each `export { … }` / `export type { … }` (including the `import`-then-`export` re-export form), accumulate named members across continuation lines until the closing `}` — count every identifier in the brace list, not only those on the opening line. A renamed re-export (`export { A as B }`) counts once under its public name (`B`).
     - Resolve `export * from "…"` to the target module's own public names — a star re-export contributes that module's surface, not a single entry.
     - Prefer a `tsc` / `ts-morph` / AST entry-point resolution over the line regex when a TS toolchain is reachable; it resolves multi-line blocks and star re-exports natively. Fall back to the brace-accumulation grep only when no AST tool is available — the same grep-fallback posture the Rust note above takes.
  2. **Fall back to live re-derivation** when `effective_denominator` is absent (older skills, quick-tier output, or skills compiled before this rule existed). Read the brief's scope globs from `forge-data/{skill_name}/skill-brief.yaml`, resolve them against `source_path`, filter out files matching `scope.exclude`, and compute the source API surface as the **union of named exports across the matched files only**. The skill brief's `scope.notes` field should document the stratification strategy (e.g., "Tier A: fully documented; Tier B: deferred to references; Tier C: excluded") — when present, treat it as confirmation that the curated subset is by design, not a scope gap.

     **Honor `scope.tier_a_include` when present.** When re-deriving, prefer the brief-level `scope.tier_a_include` narrow include list over the coarse `scope.include`. `tier_a_include` is an optional brief field that lists only the authoring surface the brief actually intends to document (tier A), letting the denominator match the brief's authoring-vs-installing intent even when `scope.include` uses coarse globs that also match internal infrastructure. When `tier_a_include` is present, resolve its globs (still filtered by `scope.exclude`), compute the union across those files, and use that count as the denominator. When absent, fall back to resolving `scope.include`.

     **Exclude umbrella barrel files from a `tier_a_include` re-derivation.** A barrel file (`lib.rs`, `mod.rs`, `index.ts`/`index.js`, `__init__.py`) whose public surface is dominated by `pub use` / re-export leaves re-exports the *entire* crate/package surface. Including such a file in the resolved `tier_a_include` set makes the union **grow** rather than shrink — defeating the narrowing and producing a denominator larger than `scope.include` would have. Detect an umbrella barrel as a file whose exported names are mostly (>50%) re-exports of symbols defined in other files. When a `tier_a_include` file set resolves to include an umbrella barrel, drop the barrel and count only the concrete-definition files; if dropping it leaves no meaningful surface, prefer `effective_denominator` (priority 1) instead of the inflated `tier_a_include` union.

  3. **Denominator inflation check (absent `tier_a_include`).** If re-derivation used `scope.include` because no `tier_a_include` was provided, compare the resulting union count against the provenance-map entry count (when provenance-map exists). If the `scope.include` union is more than 25% larger than the provenance-map entry count, the coarse globs are almost certainly sweeping in internal infrastructure that the brief did not intend to document. Emit a **Medium**-severity gap titled `denominator inflation — coarse scope.include union exceeds authored surface` that points the user at the brief for rescoping via `scope.tier_a_include`. **When the package's barrel is an umbrella re-export file** (public surface mostly `pub use` / re-export leaves — see the umbrella-barrel note in step 2), recommend `stats.effective_denominator` (priority 1) as the **primary** remediation instead of `tier_a_include`: a `tier_a_include` that lists the umbrella barrel would recount *larger* than `scope.include`, not smaller, so it cannot clear the inflation. Report both counts (`scope.include union: {N}`, `provenance-map entries: {M}`, `{percent}% inflation`) and state that the coverage score it produced is driven by denominator inflation rather than documentation gaps. The check is skipped when provenance-map is unavailable (there is no baseline to compare against).

  Leave `analysis_confidence` unchanged (still `full` or `provenance-map` per the waterfall) — stratified scope does not degrade confidence, only the denominator. Annotate the coverage report with: `Stratified scope — denominator: {effective_denominator | tier_a_include union | scope.include union} ({N} files matched, {M} exports union)`.

  **When this clause does NOT apply:** `scope.type: "full-library"` skills, single-package repositories, or stratified briefs where the full monorepo is intentionally in scope. For those, use the standard barrel-based denominator — **unless** the single-package repo is a pattern-reference app (see next bullet).

- **Pattern-reference apps (non-library source):** If the source is a single-package repo whose purpose is demonstrating an integration pattern rather than distributing a library API — typical markers are `scope.type: "full-library"` **without** a barrel file at any recognized entry-point path (`__init__.py`, `index.ts`/`index.js`, `lib.rs`, `mod.rs`) AND without a monorepo layout — the skill's value lives in wiring patterns, not exports. None of the preceding three clauses fits: there is no barrel to count from, no empty-barrel `scope.include` to consult, and no monorepo stratification to re-derive.

  **Trigger (either fires):**

  1. `scope.notes` in `forge-data/{skill_name}/skill-brief.yaml` flags pattern-reference intent (phrases such as "Reference app, not a library", "pattern-reference", "embedded-pattern skill", or "skill value is the … pattern"). The `scope.notes` field is authoritative when the author wrote it.
  2. Source tree lacks a barrel file at every recognized entry-point path AND the repo is not a monorepo (no `packages/`, `workspaces`, `lerna.json`, `rush.json`, `nx.json`, or Cargo `[workspace]`). Detected at test time by filesystem inspection of `{source_path}`.

  **Denominator:** canonicalized provenance-map entry count (same canonicalization as the "Provenance-map canonicalization" section below). `skf-create-skill`'s extraction pass has already curated the provenance-map to the authored pattern surface; treat it as the authoritative enumeration of the skill's documented reach.

  **Recommendation — prefer `tier_a_include`:** authors should add `scope.tier_a_include` to the brief listing the files that constitute the authored pattern surface, the same way stratified-scope briefs do. When `tier_a_include` is present, use its re-derived union (filtered by `scope.exclude`) as the denominator exactly as in the stratified-scope clause. When absent, fall back to the canonicalized provenance-map count — do not fabricate a denominator from arbitrary source-tree sweeps.

  **Confidence:** leave `analysis_confidence` unchanged (still `full` or `provenance-map` per the waterfall). Pattern-reference does not degrade confidence — the surface is smaller than a library barrel, not lower quality. Annotate the coverage report with: `Pattern-reference — denominator: {tier_a_include union | canonicalized provenance-map count} ({N} pattern surfaces)`.

  **When this clause does NOT apply:** any repo with a non-empty barrel file, any monorepo (use the stratified-scope clause), or any single-package repo whose `scope.type` is explicitly `public-api` / `specific-modules` / `component-library` / `docs-only` (those scope types have their own denominator semantics). Also does NOT apply when `scope.type: "reference-app"` — that scope type carries its own pattern-surface denominator semantics (the brief speaks for itself), so this clause's filesystem trigger is moot.

- **Single-crate curated subset (`scope.type: "specific-modules"`):** If the source is a single-package (non-monorepo) repo whose skill brief sets `scope.type: "specific-modules"` and uses `scope.include`/`scope.exclude` to carve a subset of the crate's public surface, the coverage denominator is the **in-scope reachable barrel** — not the full barrel.

  **Resolution:** Derive the barrel as normal for the language (e.g., Rust: `pub use` chain from `lib.rs`), then filter:

  1. **Exclude** any modules or items that fall under `scope.exclude` patterns.
  2. **Include only** items reachable from the modules listed in `scope.include`.
  3. **Respect module visibility:** items behind `mod` (not `pub mod`) boundaries that are not re-exported through the barrel are unreachable and excluded. For Rust: count only unrestricted, module-level (column-0) `pub` item declarations in barrel-reachable modules; exclude `pub(crate)` / `pub(super)` / `pub(in …)` restricted items.

  The resulting count is the denominator. Annotate the coverage report with: `Specific-modules subset — denominator: in-scope reachable barrel ({N} items from {M} modules, after scope.include/exclude filtering)`.

  **When `effective_denominator` is present:** prefer `metadata.json.stats.effective_denominator` (same priority-1 rule as the stratified-scope clause), subject to the same deflation guard.

  **When this clause does NOT apply:** monorepo packages (use the stratified-scope clause), `scope.type: "full-library"` (use the standard barrel), or empty-barrel packages (use the empty-barrel clause). This clause is specifically for single-crate repos where the brief intentionally documents a curated subset rather than the full public surface.

Internal module symbols are **excluded** from the coverage denominator unless they are explicitly documented in SKILL.md (in which case they count as documented extras, not missing coverage).

This matches the extraction-patterns.md convention used during skill creation: coverage measures how well SKILL.md documents what users actually import, not the entire internal codebase.

### Provenance-map canonicalization

When the test-side intersects documented SKILL.md exports against a stratified-scope provenance-map, raw provenance-map entry names may include **bookkeeping variants** of the same underlying export. These variants are artifacts of how the source library structures its registry (e.g., Storybook's component-plus-story decomposition, accessibility renderer shadowing, exact-match versus fuzzy-match renderer disambiguation). Counting them as separate exports inflates the denominator and produces false "missing documentation" findings for names that are structurally duplicates of an already-documented base export.

Before intersecting documented names against the provenance-map entry list, **fold bookkeeping variants back to their base name** using the rules below. This matches the convention `skf-create-skill` records in `metadata.json.stats.effective_denominator_source` (e.g., `"provenance-map canonicalized count (ThemesGlobals_def folds with ThemesGlobals under _def convention)"`) — the base form is authoritative; the variant form is a sibling record, not an independent export.

**Folding rules (apply in order, case-sensitive):**

1. **Suffix `_def`** — registry definition twin. `ThemesGlobals_def` folds to `ThemesGlobals`. Common in Storybook-style component registries where the definition object and the rendered component share the same public name.
2. **Suffix `_exact`** — exact-match variant. `ButtonSpec_exact` folds to `ButtonSpec`. Common in matcher/renderer registries where an `_exact` sibling signals a stricter resolution path.
3. **Prefix `a11y_`** — accessibility renderer shadow. `a11y_Checkbox` folds to `Checkbox`. Common in accessibility-wrapper layers that re-export every component under a parallel prefixed namespace.
4. **Other renderer-prefix disambiguation** — when the library uses a prefix-namespace convention (e.g., `mobile_`, `web_`, `ssr_`) to shadow the base export, fold the prefix form back to the base. **Only apply when the base form is also present in the provenance-map** — otherwise the prefix form is the real export and should be kept. Document the specific prefix used in the test report so the rule is auditable.

**How to apply:**

1. Read all entry names from the provenance-map.
2. Build a canonical-name set by applying the folding rules above — each variant maps to its base. Retain the original variant → base mapping for reporting.
3. Intersect the documented SKILL.md export names against the **canonical** set, not the raw entry list.
4. When computing `Export Coverage`, use the **canonical count** as the denominator — not the raw provenance-map entry count. This aligns the denominator with `metadata.json.stats.effective_denominator` (when present), which `skf-create-skill` already writes as the canonicalized count.
5. In the test report, note the fold summary: `Provenance-map canonicalization: {N} raw entries → {M} canonical bases ({N−M} bookkeeping variants folded: _def×{a}, _exact×{b}, a11y_×{c}, other×{d})`. This makes the reduction auditable by future testers and update runs.

**When to skip canonicalization:**

- If the library's public surface genuinely distinguishes the variants (e.g., `a11y_Checkbox` is a separately-documented, separately-installed component and not a shadow), do not fold — the variant is a real export. Check SKILL.md for explicit documentation of the variant before folding. When in doubt, err on the side of not folding and report both forms.
- If `metadata.json.stats.effective_denominator` is present and the provenance-map raw count matches it (no drift), canonicalization is not needed — the denominator is already canonical. Fold only when raw count > `effective_denominator` and the drift corresponds to recognizable bookkeeping suffixes/prefixes.
- If drift remains after folding (e.g., raw 222 → canonical 215 but `effective_denominator` says 216), record the residual 1-count drift as an unexplained-reconciliation note in the test report. Do not fabricate additional fold rules to close the gap.

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

**State 2 limitations:** Signature verification at State 2 is **string comparison only**, not semantic. Provenance-map stores parameters as flat string arrays (e.g., `["data: Union[BinaryIO, list, str]"]`), so `str` vs `String` or `list` vs `List[Any]` would be treated as mismatches even when semantically equivalent. For full type-aware verification (handling type aliases, generic equivalence), State 1 (local source) with AST re-parsing is required. When the SKILL.md was compiled from the same provenance-map (typical for create-then-test flows), most strings will match. However, enrichment (step 4) and doc-fetching (step 3c) during compilation may alter parameter descriptions, add type annotations, or normalize signatures, causing mismatches even in create-then-test flows. Expect some string-level mismatches and treat them as compilation artifacts, not source drift signals, until signature fidelity is enforced by step 5's Signature Fidelity Rule (see `signature_source` field in provenance-map entries).

**State 3 — No provenance-map, metadata exports exist (quick-skill path):**
If no provenance-map.json exists (typical for quick-skill output), fall back to `metadata.json`'s `exports[]` array for the export name list. Coverage check becomes a self-consistency comparison: are all names in `exports[]` documented in SKILL.md with description, parameters, and return type? Signatures cannot be verified. If remote reading tools are available, supplement by reading the entry point for live export comparison. Set `analysis_confidence: metadata-only`.

**State 4 — No local source, no forge-data, remote tools available:**
If neither provenance-map nor metadata exports provide a usable baseline, but remote reading tools (zread, deepwiki, gh API, or similar) are available and `source_repo` is set in metadata.json, read the entry point remotely to build the export inventory from scratch. Name-matching only — no AST. Set `analysis_confidence: remote-only`.

**State 5 — No source access at all:**
If none of the above succeed, fall through to docs-only mode (as defined in coverage-check.md Section 0: pre-analysis source type detection). Set `analysis_confidence: docs-only`. Warn: "**No source access available.** Coverage check evaluates documentation self-consistency only. Re-run with local clone or remote access for source-backed verification."

Set `analysis_confidence` in context for use in Section 2 analysis depth, step 5 output, and step 5 scoring.

**Confidence tier mapping:** `full` = T1, `provenance-map` = T1, `metadata-only` = T1-low, `remote-only` = T1-low, `docs-only` = T3. This aligns with the T1/T1-low/T2/T3 scale used across all SKF workflows.

**Degradation notice rules:** When `analysis_confidence` is `provenance-map`, check the `confidence` field of provenance-map entries before emitting a degradation recommendation:

- **All/most entries T1 (AST-verified):** The provenance-map data is already at highest confidence. Do NOT recommend re-running with a local clone — it would produce identical results. Use: "Resolved via: provenance-map (T1 AST-verified at compilation time). Local clone not required — provenance data is already at highest confidence."
- **Mixed T1/T1-low entries:** Report the breakdown. Recommend local clone only for the T1-low entries: "Resolved via: provenance-map ({n} T1, {m} T1-low). Re-run with local clone to upgrade T1-low entries to full AST verification."
- **All/most entries T1-low or lower:** Keep the standard recommendation: "Re-run with local clone for full AST-backed verification."
