# Source Access Protocol

## Source API Surface Definition

**Source API surface** = the package's top-level public exports. These are the symbols reachable from the primary entry point without importing internal modules:

- **Python:** symbols exported in `__init__.py` (including re-exports) — exclude private (`_prefixed`) names
- **TypeScript/JavaScript:** named exports from `index.ts` / `index.js` — exclude unexported locals
- **Go:** exported identifiers (capitalized) from the package's public-facing files
- **Rust:** items in `pub use` from `lib.rs` or `mod.rs`

Internal module symbols are **excluded** from the coverage denominator unless they are explicitly documented in SKILL.md (in which case they count as documented extras, not missing coverage).

This matches the extraction-patterns.md convention used during skill creation: coverage measures how well SKILL.md documents what users actually import, not the entire internal codebase.

## Source Access Resolution

Before analysis, determine source access level. Walk through these states in order — use the first that succeeds:

**State 1 — Local source available:**
Check if `{source_path}` (from metadata.json `source_root`) exists on disk. If yes → full analysis at detected tier (AST + signatures). Set `analysis_confidence: full`.

**State 2 — Local absent, provenance-map exists:**
Check `{forge_data_folder}/{skill_name}/provenance-map.json`. If present, use it as the baseline export inventory — each entry contains structured fields: `export_name`, `export_type`, `params[]`, `return_type`, `source_file`, `source_line`, `confidence`, and `ast_node_type`. Cross-reference against SKILL.md documented exports for name-matching and param-by-param coverage. Signature verification compares SKILL.md's documented params/return types against provenance-map entries directly. If remote reading tools are available (zread, deepwiki, gh API, or similar), supplement by reading the entry point file for live signature verification. Set `analysis_confidence: provenance-map`.

**State 2 limitations:** Signature verification at State 2 is **string comparison only**, not semantic. Provenance-map stores parameters as flat string arrays (e.g., `["data: Union[BinaryIO, list, str]"]`), so `str` vs `String` or `list` vs `List[Any]` would be treated as mismatches even when semantically equivalent. For full type-aware verification (handling type aliases, generic equivalence), State 1 (local source) with AST re-parsing is required. When the SKILL.md was compiled from the same provenance-map (typical for create-then-test flows), strings match exactly and this limitation has no practical effect.

**State 3 — No provenance-map, metadata exports exist (quick-skill path):**
If no provenance-map.json exists (typical for quick-skill output), fall back to `metadata.json`'s `exports[]` array for the export name list. Coverage check becomes a self-consistency comparison: are all names in `exports[]` documented in SKILL.md with description, parameters, and return type? Signatures cannot be verified. If remote reading tools are available, supplement by reading the entry point for live export comparison. Set `analysis_confidence: metadata-only`.

**State 4 — No local source, no forge-data, remote tools available:**
If neither provenance-map nor metadata exports provide a usable baseline, but remote reading tools (zread, deepwiki, gh API, or similar) are available and `source_repo` is set in metadata.json, read the entry point remotely to build the export inventory from scratch. Name-matching only — no AST. Set `analysis_confidence: remote-only`.

**State 5 — No source access at all:**
If none of the above succeed, fall through to docs-only mode (section 0 already handles this). Set `analysis_confidence: docs-only`. Warn: "**No source access available.** Coverage check evaluates documentation self-consistency only. Re-run with local clone or remote access for source-backed verification."

Set `analysis_confidence` in context for use in Section 2 analysis depth, step-05 output, and step-05 scoring.

**Confidence tier mapping:** `full` = T1, `provenance-map` = T1, `metadata-only` = T1-low, `remote-only` = T1-low, `docs-only` = T3. This aligns with the T1/T1-low/T2/T3 scale used across all SKF workflows.

**Degradation notice rules:** When `analysis_confidence` is `provenance-map`, check the `confidence` field of provenance-map entries before emitting a degradation recommendation:

- **All/most entries T1 (AST-verified):** The provenance-map data is already at highest confidence. Do NOT recommend re-running with a local clone — it would produce identical results. Use: "Resolved via: provenance-map (T1 AST-verified at compilation time). Local clone not required — provenance data is already at highest confidence."
- **Mixed T1/T1-low entries:** Report the breakdown. Recommend local clone only for the T1-low entries: "Resolved via: provenance-map ({n} T1, {m} T1-low). Re-run with local clone to upgrade T1-low entries to full AST verification."
- **All/most entries T1-low or lower:** Keep the standard recommendation: "Re-run with local clone for full AST-backed verification."
