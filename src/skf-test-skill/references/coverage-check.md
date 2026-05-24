---
nextStepFile: 'coherence-check.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
scoringRulesFile: 'references/scoring-rules.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Coverage Check

## STEP GOAL:

Compare the exports, functions, classes, types, and interfaces documented in SKILL.md against the actual source code API surface. Identify missing documentation, undocumented exports, and signature mismatches. Analysis depth scales with forge tier.

### 0. Check for Docs-Only Mode

**If all SKILL.md citations are `[EXT:...]` format (no local source citations):**

Set `docs_only_mode: true` in context for step 5 scoring. Coverage scoring adapts: instead of comparing SKILL.md against source code exports, compare SKILL.md documented items against themselves for internal completeness (every documented function has a description, parameters, and return type). Score based on documentation completeness rather than source coverage.

**Quick-tier weight adjustment:** If `confidence_tier` is also `"Quick"`, apply Quick-tier weight redistribution (zeroing Signature Accuracy and Type Coverage) as an additional step per `{scoringRulesFile}`.

"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than source code coverage."

**If source-based skill:** Continue with standard coverage check below.

### 0b. Load Source Access Protocol

Load `{sourceAccessProtocol}` and follow both sections:
1. **Source API Surface Definition** — determines what counts as the public API for coverage denominator
2. **Source Access Resolution** — 5-state waterfall to determine how source files will be read and sets `analysis_confidence`

### 1. Extract Documented Exports from SKILL.md

<!-- Subagent delegation: read SKILL.md + references/*.md, return compact JSON inventory -->

Delegate reading of the skill under test to a subagent. The subagent receives the path to SKILL.md (and the `references/` directory path if it exists) and MUST:
1. Read SKILL.md
2. If a `references/` directory exists alongside SKILL.md and SKILL.md's `## Full` headings are absent or stubs, also read all `references/*.md` files
3. ONLY return this compact JSON inventory — no prose, no extra commentary:

```json
{
  "exports": [
    {"name": "functionName", "kind": "function", "params": "...", "return_type": "...", "description": "..."},
    {"name": "ClassName", "kind": "class", "methods": ["..."], "properties": ["..."]},
    {"name": "TypeName", "kind": "type", "fields": ["..."]},
    {"name": "CONST_NAME", "kind": "constant", "values": ["..."]},
    {"name": "useHook", "kind": "hook", "usage_signature": "..."}
  ],
  "capabilities": ["brief capability descriptions from the skill overview"],
  "references": ["references/api-reference.md", "references/type-definitions.md"],
  "cross_check_mismatches": [
    {
      "export": "functionName",
      "skill_md_line": 42,
      "reference_file": "references/api-reference.md",
      "reference_line": 18,
      "issue": "description of the signature mismatch"
    }
  ]
}
```

**Parent uses this JSON summary as the documented inventory.** Do not load SKILL.md or references file contents into parent context.

#### 1a. Parent-Side Schema Validation + Spot-Check (MANDATORY)

test-skill is a quality gate — it MUST NOT trust subagent output blindly. Before any downstream step consumes the inventory, the parent performs two checks and HALTs on any failure:

**Schema validation (required keys + types):**

1. Strip wrapping markdown fences before parsing. Subagents frequently return JSON wrapped in a code fence — a line of three backticks (optionally followed by a language tag like `json`) preceding the JSON and a closing line of three backticks after it — despite prompt instructions to return raw JSON. When the first non-empty line of the response is three backticks (optionally with a language tag) and the last non-empty line is three backticks, remove those two fence lines before parsing. Then parse the remaining content as JSON. On parse failure of the inner content → HALT "coverage-check: subagent response not valid JSON".
2. Required keys present: `exports` (list), `cross_check_mismatches` (list — may be empty). Missing key or wrong type → HALT "coverage-check: subagent JSON schema invalid — missing/typo: {key}". Note: the parent already knows the skill name from workflow context (`{resolved_skill_package}` from step 1) — the subagent is not required to echo it back, and doing so introduces a contract-drift surface without improving verification.
3. Each `exports[]` entry must be a dict with at minimum `name` (non-empty string) and `kind` (one of `function|class|type|constant|hook|interface|method|struct|enum|trait|macro|adapter`). The enum spans the constructs SKF actually documents across languages and skill types: JS/TS (`function`/`class`/`type`/`constant`/`hook`/`interface`/`method`), Rust public-API items (`struct`/`enum`/`trait`/`macro` — alongside the shared `type`/`constant`/`function`), and stack-composition scaffolds (`adapter`). Reject entries violating this; if >0 rejections, HALT "coverage-check: subagent returned malformed export entries — {count} entries do not match schema".
4. `cross_check_mismatches[]` entries (when non-empty) must carry `export`, `skill_md_line`, `reference_file`, `reference_line`, `issue`. Missing fields → HALT.

**Spot-check (ground-truth verification, zero-hallucination guard):**

1. If `len(exports) == 0`: skip the spot-check (no names to verify). Zero-exports policy is handled in the §2b zero-exports guard.
2. Otherwise, sample `min(3, len(exports))` exports deterministically — by default take indices `[0, len//2, len-1]` (first, middle, last) from the `exports` array after a stable sort by `name`.
3. For each sampled export, grep for the name across SKILL.md **and every reference file the subagent listed in its `references[]` array** (the documented surface of a split-body skill spans both): `grep -n "{export.name}" {resolved_skill_package}/SKILL.md {resolved_skill_package}/{each references[] path}` in the parent context. The name MUST appear at least once somewhere in that file set. Greping SKILL.md alone would false-HALT a split-body skill whose sampled export is documented only in a `references/*.md` file (a legitimate placement per §1 step 2 and the split-body note below).
4. If a sampled name returns zero matches across SKILL.md **and** all listed reference files, HALT "coverage-check: subagent inventory failed ground-truth spot-check — `{name}` claimed as export but absent from SKILL.md and the listed reference files".

These checks catch two hallucination classes: schema-shape drift (subagent paraphrased or dropped the contract) and fabricated exports (subagent invented names not in the document). Both are disqualifying for a grader skill — do not downgrade to a warning.

**Split-body traversal** is handled inside the subagent: if `references/` exists and `## Full` headings are absent or stubs in SKILL.md, the subagent extends its scan to all `references/*.md` files and includes them in the `exports` array. After split-body, Tier 2 content (Full API Reference, Full Type Definitions) lives in reference files — the inventory must reflect the full skill content regardless of where it resides.

### 1b. Cross-Check Split-Body Consistency

**Only execute if the subagent's `references` array is non-empty** (detected during split-body traversal in Section 1). Skip silently otherwise.

The subagent has already read both SKILL.md body and `references/*.md` files. For each function, class, type, or interface that appears in BOTH the SKILL.md body AND any `references/*.md` file, instruct the subagent (or perform in the same subagent call from Section 1) to compare the documented signatures and include mismatches in its JSON output as a `cross_check_mismatches` array:

- **Parameters:** name, type, order, optionality
- **Return types:** exact type match
- **Description:** no contradictions (brief vs detailed is acceptable; conflicting semantics is not)

**SKILL.md body is authoritative.** When a mismatch is found, the reference file is the one that needs updating.

Parent reads `cross_check_mismatches` from the subagent JSON summary. Build the split-body consistency findings list:

```json
{
  "cross_check_mismatches": [
    {
      "export": "formatDate",
      "skill_md_line": 42,
      "reference_file": "references/api-reference.md",
      "reference_line": 18,
      "issue": "SKILL.md shows (date: Date) => string, reference shows (date: Date, format?: string) => string"
    }
  ],
  "exports_cross_checked": 12,
  "mismatches_found": 1
}
```

Flag each mismatch as **High severity** — signature inconsistency between SKILL.md body and reference files undermines agent trust. These findings feed into the gap report (step 6).

### 2. Analyze Source Code (Tier-Dependent)

Start from the package entry point (see 0b) and identify the public API surface. Then analyze those exports at the appropriate tier depth.

**Quick Tier (no tools):**
- Read the entry point file(s) directly
- Identify public exports by scanning for `export` keywords, `module.exports`, `__init__.py` imports, or language-specific export patterns
- Compare against documented inventory by name matching
- Cannot verify signatures — note as "unverified" in report

**Forge Tier (ast-grep available):**

**Before delegating, the parent builds a `documented_signatures` map** from the §1 inventory: `{ "{name}": {"params": "...", "return_type": "..."} }` for every documented export that carries a signature. Pass this map as a structured input alongside the per-file ast-grep instructions. Without it the subagent has only the bare source — it cannot diff against the documented signatures, so `signature_mismatches[]` collapses to empty and Signature Accuracy defaults to 100% on a name-only pass (a silent false positive). The subagent must populate `documented_sig` from this map, not invent it.

For EACH source file that defines public API exports, delegate to a subagent that:
1. Uses ast-grep to extract all exported symbols with their full signatures (the `source_sig`)
2. Matches each export against the `documented_signatures` map supplied by the parent, comparing params (name, type, order, optionality) and return type
3. Returns ONLY the JSON object below — no prose, no commentary, no markdown fences:

```json
{
  "file": "src/utils.ts",
  "exports_found": ["formatDate", "parseConfig", "ConfigType"],
  "exports_documented": ["formatDate", "parseConfig"],
  "missing_docs": ["ConfigType"],
  "signature_mismatches": [
    {
      "name": "formatDate",
      "source_sig": "(date: Date, format?: string) => string",
      "documented_sig": "(date: Date) => string",
      "issue": "missing optional parameter 'format'"
    }
  ]
}
```

Parent strips wrapping markdown fences (if present) before parsing, same as §1a. If subagent unavailable, perform ast-grep analysis in main thread per file.

**Deep Tier (ast-grep + gh + QMD):**
- All Forge tier checks, plus:
- Use gh CLI to verify source repository matches documented version
- Cross-check type definitions against their source declarations
- Verify re-exported symbols trace to their original source

### 2b. Zero-Exports Guard

After the source-code analysis (§2) completes, compute `total_exports` — the count of exports discovered in the source / provenance-map / metadata.json, per the stratified-scope and State 2 rules resolved in §4.

**Stack-skill branch (`metadata.json.skill_type == "stack"`):** A stack skill's own barrel is empty by design — it composes constituent skills rather than exporting a proprietary surface — so `total_exports` derived from its own barrel is `0` for a *correctly* built stack, and its `[from skill: …]` citations never trip §0's `[EXT:…]`-only docs-only trigger. The zero-exports HALT below targets individual source-based skills and must NOT fire for stacks. Derive the stack's coverage denominator (`stack_denominator`) from its composition surface, in priority order, and use it as `total_exports` for the rest of coverage scoring:

1. Provenance-map cited-contract count — when `{forge_data_folder}/{skill_name}/provenance-map.json` exists **and its `entries[]` is non-empty**: count the named cited contracts, **excluding entries whose `export_name` contains `::`** (impl-block methods roll up under an already-counted type). Use the same exclusion as §4b's named-export rule so the §2b and §4b stack denominators agree.
2. Otherwise the composition surface from `metadata.json`: `len(libraries) + len(integration_pairs)`.

**If `stack_denominator == 0`** (no provenance-map or empty `entries[]`, AND `libraries` and `integration_pairs` are both empty): HALT with `Error: stack composition surface empty — {skill_name} cites no contracts, libraries, or integration pairs, so Export Coverage is undefined. Verify the stack was compiled from at least one constituent skill.` Do not write the Coverage Analysis section; this is an indeterminate state, not a FAIL.

Otherwise carry `stack_denominator` forward as `total_exports`, skip the HALT below, and continue — §2c and §4b consume this same denominator via their own stack-skill branches. (Stacks route to contextual mode per `detect-mode.md` and have a dedicated section in `scoring-rules.md`, so they are first-class — the indeterminate-surface HALT is an individual-skill guard only.)

**If `total_exports == 0` AND `docs_only_mode == false` AND `metadata.json.skill_type != "stack"`:** HALT with:

```
Error: indeterminate API surface — 0 exports discovered in source for {skill_name}.

A source-based skill with zero exports cannot be meaningfully tested:
Export Coverage is undefined (division by zero) and downstream scoring
would yield a vacuous PASS.

Fix one of:
  - Set `scope.include` in the brief to point at the package's entry point(s)
  - Add `[EXT:]` citations if this is actually a docs-only skill
  - Verify the skill's source_path / source_ref resolve to the intended tree
```

Do not write the Coverage Analysis section. Do not proceed to scoring. This is a true indeterminate state, not a FAIL — no score should be attached.

**If `docs_only_mode == true` and the documented inventory is empty:** HALT with the analogous docs-only message ("docs-only skill declares zero items — no API surface to test").

### 2c. Reconcile Documented vs Source Surface (Deterministic Intersection)

On a split-body skill the §1 inventory (documented surface) and the §2 AST output (source barrel) are two independent lists, so the `Documented` count must be their **intersection**, not a parent estimate. Compute three sets deterministically so the Export Coverage numerator is reproducible across runs and reviewers:

**Stack-skill branch (`metadata.json.skill_type == "stack"`):** A stack's source barrel is empty by design, so `barrel_set` is `{}` and the `|documented_set ∩ barrel_set|` / `|barrel_set|` formulas in steps 3–4 would divide by zero. Do NOT use the source barrel for a stack. Instead use the §2b `stack_denominator` as the denominator and compute the numerator by full-grep verification (same mechanism as the scalar-denominator branch below): enumerate the stack's composition-surface names — the provenance-map cited-contract names (`::`-excluded) when the map exists and is non-empty, else the `libraries` and `integration_pairs` names — and for each, grep across `SKILL.md ∪ references/*.md`; `Documented` := the count that appear at least once. Set `Missing` := `stack_denominator − Documented` and omit `Stale` (no source barrel to enumerate against). Carry these into §3/§4 with `Export Coverage = Documented / stack_denominator * 100`, and skip steps 1–4 below.

1. **`documented_set`** := the de-duplicated set of `name` from the §1 inventory `exports[]`, excluding `kind: "method"` (methods are members of an already-counted class/type, not top-level barrel exports).
2. **`barrel_set`** := the union of `exports_found[]` across every §2 per-file result (the actual source public surface). When a stratified-scope or State-2 denominator applies (see §4) **and it resolves to an enumerated name set** — the priority-2/3 re-derivation from `scope.tier_a_include` / `scope.include` globs — `barrel_set` is that resolved denominator's name set instead of the raw union.

   **Scalar-denominator branch (§4 priority 1):** when the resolved denominator is the scalar `metadata.json.stats.effective_denominator` (a count with **no enumerated name set**), there is no `barrel_set` to intersect against — the `documented_set ∩ barrel_set` formula in step 3 does not apply. Instead compute the numerator by full-grep verification: for each name in `documented_set`, grep it across `SKILL.md ∪ references/*.md`; `Documented` := the count of `documented_set` names that appear at least once. Use `effective_denominator` directly as the denominator, set `Missing` := `effective_denominator − Documented`, and omit `Stale` (not enumerable without a barrel name set). If §4b's numerator-ground-truth arm fires (it triggers only when `exports_documented == effective_denominator`), its verified count is authoritative and **overrides** this numerator — do not apply both.
3. Compute (**enumerated path only** — skip when the scalar-denominator branch above applies):
   - `Documented` := `|documented_set ∩ barrel_set|`
   - `Missing` := `barrel_set − documented_set` (in source, not documented)
   - `Stale` := `documented_set − barrel_set` (documented, not in source)
4. Carry the resulting counts into §3's table and §4's Export Coverage: `Export Coverage = |Documented| / |barrel_set| * 100` (enumerated path) or `Documented / effective_denominator * 100` (scalar-denominator branch). Record the counts in the Coverage Analysis section so the numerator is auditable.

This removes the parent-side guess that otherwise swings the documented count between runs (e.g., "85 from the AST agent" vs "~120 from a hand intersection") and can cross the PASS threshold on split-body skills.

### 3. Build Coverage Results

Aggregate findings across all source files:

**Per-export status table:**

| Export | Type | Documented | Signature Match | File:Line | Status |
|--------|------|-----------|-----------------|-----------|--------|
| {name} | function/class/type | yes/no | yes/no/unverified | src/file.ts:42 | PASS/FAIL/WARN |

**Summary counts** (from the §2c reconciliation — not re-estimated here):
- Total exports in source: `|barrel_set|`
- Documented in SKILL.md: `Documented` (`|documented_set ∩ barrel_set|`)
- Missing documentation: `|Missing|`
- Signature mismatches: {N}
- Undocumented in SKILL.md but not in source (stale docs): `|Stale|`

### 4. Load Scoring Rules

Load `{scoringRulesFile}` to determine category scores:

- **Export Coverage:** (documented / total_exports) * 100
- **Signature Accuracy:** (matching_signatures / total_documented) * 100 (Forge/Deep only, "N/A" for Quick)
- **Type Coverage:** (documented_types / total_types) * 100 (Forge/Deep only, "N/A" for Quick)

**Stratified-scope denominator (monorepo curated subsets):** Before computing Export Coverage, check whether the Source Access Protocol's stratified-scope clause applies to this skill (see `{sourceAccessProtocol}` §Source API Surface Definition — "Stratified-scope monorepo packages"). When it applies:

1. **Prefer `metadata.json.stats.effective_denominator`** when present. Use it directly as `total_exports` — but apply the **denominator deflation guard** from `{sourceAccessProtocol}` stratified-scope resolution step 1: when source is readable, re-derive the source barrel and, if it exceeds `effective_denominator` by >25% with no `scope.tier_a_include`, treat the stored value as deflated, use the re-derived count, and emit the `denominator deflation` gap.
2. **Otherwise re-derive at test time** from the brief's scope globs per the protocol. When the brief supplies `scope.tier_a_include`, re-derive from that narrower list (excluding umbrella barrel files per the protocol's umbrella-barrel note); otherwise re-derive from `scope.include`. Use the resulting union count as `total_exports`.
3. **Run the denominator inflation check** defined in `{sourceAccessProtocol}` stratified-scope resolution step 3 whenever re-derivation fell back to `scope.include`. If the `scope.include` union exceeds the provenance-map entry count by more than 25%, emit the Medium-severity `denominator inflation — coarse scope.include union exceeds authored surface` gap and append it to the Coverage Analysis gap list.
4. **Apply provenance-map canonicalization** before intersecting documented exports against the raw provenance-map entry list — see `{sourceAccessProtocol}` §Source API Surface Definition → "Provenance-map canonicalization" for the folding rules (`_def`/`_exact` suffix, `a11y_` prefix, renderer-prefix disambiguation). Skip folding when `metadata.json.stats.effective_denominator` is present and already equals the raw provenance-map entry count. Record the fold summary in the Coverage Analysis section so it's auditable.

Record the denominator source in the Coverage Analysis section as `Denominator: stratified ({effective_denominator | tier_a_include union | scope.include union}, {N} files matched)`. When stratified scope does not apply, use the standard barrel-based denominator and omit the stratified annotation.

**Record the two non-chosen candidate values alongside the chosen one.**
Stratified-scope resolution picks ONE of three denominator candidates
(`stats.effective_denominator`, `tier_a_include` union, `scope.include` union)
per the priority above. To make the choice auditable, append a
`Denominator Candidates` block immediately after the `Denominator:` line listing
all three values — the chosen one explicitly marked and the other two recorded
as-observed (or `absent` when the candidate was not present for this skill):

```markdown
**Denominator Candidates** (stratified-scope audit trail):
- `stats.effective_denominator`: {N | absent}  {← chosen if priority (1) applied}
- `scope.tier_a_include` union: {N | absent}    {← chosen if priority (2) applied}
- `scope.include` union: {N | absent}           {← chosen if priority (3) applied}
```

Readers can then spot-check whether the chosen denominator is reasonable
against the other two without re-running the extraction. A future reviewer who
suspects denominator gaming has the evidence inline.

**State 2 denominator validation:** When using provenance-map as the baseline (State 2), cross-reference the provenance-map entry count against `metadata.json`'s `exports[]` array before computing Export Coverage. If they diverge, use the union as the denominator per the source-access-protocol rules. Log the gap size if any. The stratified-scope rule above takes precedence when both conditions apply — compute the stratified denominator first, then validate the provenance-map entry count against it.

### 4b. Metadata Export-Count Coherence Cross-Check

After the denominator has been resolved (standard, stratified, or State 2), cross-check export counts *within each semantic cluster* to detect extraction drift without false-positiving on intentional multi-denominator reporting. Picking the denominator silently when sources disagree is a known friction — the tester cannot tell whether to trust the pick, ignore the drift, or report it. Make it explicit, but only for counts that are authored to measure the *same* surface.

**Stack-skill branch (`metadata.json.skill_type == "stack"`):** Skip the intra-cluster and cross-cluster count comparisons, the `confidence_distribution` sum check, AND the numerator ground-truth check below — none apply to a stack. For a stack the three counts measure intentionally *different* surfaces, so comparing them yields only false drift: `exports_documented` / `exports[]` measure the stack's own barrel (empty by design → `0`), the provenance-map enumerates the cited *constituent* contracts, and `confidence_distribution` bins those constituents — so for a stack treat `confidence_distribution` as a per-constituent count (it sums to the constituent count, not to `exports_documented`) and do not assert it against `exports_documented`. The numerator-inflation arm below targets an *individual* skill whose `exports_documented` was padded to equal `effective_denominator`; a stack's numerator is instead computed by full-grep in §2c's stack-skill branch and stack `metadata.json.stats` carries no `effective_denominator`, so the arm is not run. Record the denominator using the §2b source — `Denominator: stack composition ({N} cited contracts)` when the provenance-map supplied it, or `Denominator: stack composition ({N} libraries + integration pairs)` when the composition surface did — then proceed.

**Collect available counts (skip any that are absent) and bin them into two clusters:**

**Cluster A — public-barrel surface** (what `__init__.py` / `index.ts` / `lib.rs` re-exports):

1. `metadata.json.stats.exports_public_api` — the declared public API count
2. `metadata.json.exports[]` array length — the enumerated public export list

**Cluster B — documented surface** (what was extracted and documented, including methods and submodule members):

3. `metadata.json.stats.exports_documented` — the declared documented count
4. Provenance-map **named-export count** (if `{forge_data_folder}/{skill_name}/provenance-map.json` exists) — count only top-level named exports: **exclude entries whose `export_name` contains `::`** (impl-block methods like `Type::method`, which roll up under an already-counted type and are not separate barrel exports). Comparing the raw entry count instead false-positives on any method-enumerating provenance map (common for Rust/TS type-heavy skills): e.g. a map with 88 named exports + 48 `Type::method` entries reports 136 against `exports_documented` ≈ 92 → a spurious ~32% Cluster-B drift, while the comparable named-export count (88) agrees within ~4%.
5. `confidence_distribution` sum (`t1 + t1_low + t2 + t3`, when present in `metadata.json.stats`) — every extracted/documented export is binned into exactly one confidence tier, so the distribution must sum to the documented-surface total; a divergence (e.g., distribution sums to 91 while `exports_documented` is 85) is an internal-consistency defect even when the two clusters look fine

Cluster assignment is canonical: `skf-create-skill` step 5 derives `exports_public_api` from entry-point validation and writes the `exports[]` array from the same barrel surface (see `skf-create-skill/references/compile.md:105`), while `exports_documented` tracks the broader documented surface that the provenance-map also enumerates.

**Intra-cluster divergence (Medium):** For each cluster, if two or more counts are present and the largest and smallest disagree by more than 10% of the larger, emit a **Medium**-severity gap titled `metadata drift — {cluster} export counts diverge` (substitute `barrel` for Cluster A, `documented-surface` for Cluster B). Enumerate the offending counts in the gap body (e.g., `stats.exports_public_api=55, exports[].length=48` → 13% drift). This is the real drift signal — the two sources should mirror the same surface and they don't, so upstream extraction or compilation produced inconsistent output that a re-compile should reconcile. Classify under structural/metadata coherence regardless of naive/contextual mode.

**Cross-cluster divergence (Info):** After intra-cluster checks, if both clusters resolved to a representative count (pick the higher of each cluster's available counts) and the two cluster values differ by more than 10%, append a single **Info**-severity note titled `multi-denominator reporting — barrel vs documented surface` with both values (e.g., `barrel=55, documented=114`). This is expected for skills whose documented surface intentionally exceeds the barrel (methods, submodule members, re-exported classes) — it is not drift. The note exists so the test report makes the dual-denominator design visible and auditable without demanding action.

**When a cluster has only one count available:** Skip that cluster's intra-cluster check silently — there is nothing to cross-check within it.

**When both clusters agree within 10% of each other:** Skip the cross-cluster note silently — no multi-denominator reporting is in play.

**When only one count is available across both clusters:** Skip silently — there is nothing to cross-check.

**Numerator ground-truth — force a full grep on the inflation signature:** The intra/cross-cluster checks above only compare *counts*; they cannot tell whether the declared documented exports actually appear in the skill. When `metadata.json.stats.exports_documented == effective_denominator` exactly (the numerator equals the denominator — the signature of a numerator inflated to match the full surface), do **not** trust the documented count. Grep every declared export name (the full `metadata.exports[]` / provenance-map declared set — not the §1a 3-sample) against `SKILL.md ∪ references/*.md`. The count of declared names that actually appear is the **verified numerator**:

- If verified == declared, the skill is genuinely fully documented — no finding; coverage stands.
- If verified < declared, emit a **High**-severity gap `numerator inflation — {declared − verified} of {declared} declared exports absent from SKILL.md/references` listing the absent names, and use the verified count as the Export Coverage numerator (overriding `exports_documented`). A numerator padded to equal the denominator otherwise produces a tautological 100% that passes the gate.

The full grep runs only on the exact equality signature, so it adds no cost to the common case where the numerator is already below the denominator. Unlike the count-coherence findings above, this arm is authoritative — it changes the numerator used for scoring.

Append any findings (Medium gaps, the Info note, and/or the High numerator-inflation gap) to the Coverage Analysis section's gap list (built in section 5) so they surface in the final test report alongside coverage and signature findings. The count-coherence findings are informational about data quality and do not change the denominator chosen above; the numerator ground-truth arm is the one exception that overrides the numerator.

### 5. Append Coverage Analysis to Output

Append the **Coverage Analysis** section to `{outputFile}`:

```markdown
## Coverage Analysis

**Tier:** {forge_tier}
**Source Access:** {analysis_confidence} (full | provenance-map | metadata-only | remote-only | docs-only)
**Source Path:** {source_path}
**Files Analyzed:** {count}
**Denominator:** {barrel | stratified ({effective_denominator | scope.include union}, {N} files matched)}

### Export Coverage

| Export | Type | Documented | Signature | Source Location | Status |
|--------|------|-----------|-----------|-----------------|--------|
| ... per-export rows ... |

### Coverage Summary

- **Exports Found:** {N}
- **Documented:** {N} ({percentage}%)
- **Missing Documentation:** {N}
- **Signature Mismatches:** {N}
- **Stale Documentation:** {N}

### Category Scores

| Category | Score |
|----------|-------|
| Export Coverage | {N}% |
| Signature Accuracy | {N}% or N/A |
| Type Coverage | {N}% or N/A |

Note: Weight application is deferred to step 5 where all category weights are calculated after external validation availability is known.
```

### 6. Report Coverage Results

"**Coverage check complete.**

**{skill_name}** — {forge_tier} tier analysis of {file_count} source files:

- Exports: {documented}/{total} documented ({percentage}%)
- Signatures: {matching}/{total} accurate ({percentage}% or N/A for Quick)
- Types: {documented_types}/{total_types} covered ({percentage}% or N/A for Quick)

**{N} issues found** — details in Coverage Analysis section.

**Proceeding to coherence check...**"

Update stepsCompleted, then load and execute {nextStepFile}.

