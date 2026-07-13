---
nextStepFile: 'coherence-check.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
scoringRulesFile: '{scoringRulesPath}'
sourceAccessProtocol: 'references/source-access-protocol.md'
reconcileScript: 'scripts/reconcile-coverage.py'
coherenceScript: 'scripts/check-metadata-coherence.py'
numeratorVerifyScript: 'scripts/verify-declared-numerator.py'
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

Delegate reading of the skill under test to a subagent. The subagent receives the path to SKILL.md (and the `references/` directory path if it exists) and must:
1. Read SKILL.md
2. If a `references/` directory exists alongside SKILL.md and SKILL.md's `## Full` headings are absent or stubs, also read all `references/*.md` files
3. only return this compact JSON inventory — no prose, no extra commentary:

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

**If subagent delegation is unavailable:** the parent performs the read itself in the main thread — read SKILL.md (and, per step 2 above, all `references/*.md` when a `references/` directory exists and SKILL.md's `## Full` headings are absent or stubs) and assemble the same compact JSON inventory. The §1a schema validation and ground-truth spot-check still run on the parent-built inventory — a quality gate does not skip its own hallucination guards just because the extraction ran in-thread. This mirrors the §2 fallback ("perform ast-grep analysis in main thread") so §1 degrades gracefully instead of stalling.

#### 1a. Parent-Side Schema Validation + Spot-Check

test-skill is a quality gate — it must not trust subagent output blindly. Before any downstream step consumes the inventory, the parent runs a schema validator and a grep spot-check, and HALTs on any failure.

**Schema validation (required keys + types) — delegated to `scripts/validate-inventory.py`.** Fence-stripping, JSON parsing, and the required-keys / per-entry-type / `kind`-enum / mismatch-field contract are structural validation with one correct verdict per input, so they run in the script, not in-prompt. Pipe the subagent's **raw** response (fence and all) to it exactly as §2c pipes the reconcile input:

```bash
echo '<subagent raw response>' | uv run scripts/validate-inventory.py --stdin
```

The script strips a wrapping markdown fence (a leading line of three backticks with an optional language tag like `json`, and a trailing line of three backticks — subagents frequently return fenced JSON despite instructions), parses the inner content, and enforces exactly this contract, returning a `violations[]` entry for each breach:

- Parses as JSON after fence stripping (parse failure → `not valid JSON`).
- Required keys present with correct types: `exports` (list), `cross_check_mismatches` (list — may be empty). Note: the parent already knows the skill name from workflow context (`{resolved_skill_package}` from step 1) — the subagent is not required to echo it back, and doing so introduces a contract-drift surface without improving verification.
- Each `exports[]` entry is a dict with at minimum `name` (non-empty string) and `kind` (one of `function|class|type|constant|hook|interface|method|struct|enum|trait|macro|adapter`). The enum spans the constructs SKF actually documents across languages and skill types: JS/TS (`function`/`class`/`type`/`constant`/`hook`/`interface`/`method`), Rust public-API items (`struct`/`enum`/`trait`/`macro` — alongside the shared `type`/`constant`/`function`), and stack-composition scaffolds (`adapter`). Malformed entries are counted in `rejectedCount`.
- Each non-empty `cross_check_mismatches[]` entry carries `export`, `skill_md_line`, `reference_file`, `reference_line`, `issue`.

The script returns `{"valid": bool, "violations": [...], "rejectedCount": N, "exportsCount": N, "inventory": {...}|null}`. **If `valid` is false → HALT** `coverage-check: subagent inventory failed schema validation — {violations joined}` (do not downgrade to a warning; a grader must not trust malformed subagent output). When `valid` is true, consume the script's returned `inventory` object as the documented inventory for the spot-check and all downstream steps — do **not** re-parse the raw response by hand.

**Spot-check (ground-truth verification, zero-hallucination guard):** operate on the validated `inventory` from the script.

1. If `inventory.exports` is empty (`exportsCount == 0`): skip the spot-check (no names to verify). Zero-exports policy is handled in the §2b zero-exports guard.
2. Otherwise, sample `min(3, exportsCount)` exports deterministically — by default take indices `[0, len//2, len-1]` (first, middle, last) from `inventory.exports` after a stable sort by `name`.
3. For each sampled export, grep for the name across SKILL.md **and every reference file the subagent listed in `inventory.references`** (the documented surface of a split-body skill spans both): `grep -n "{export.name}" {resolved_skill_package}/SKILL.md {resolved_skill_package}/{each references[] path}` in the parent context. The name must appear at least once somewhere in that file set. Greping SKILL.md alone would false-HALT a split-body skill whose sampled export is documented only in a `references/*.md` file (a legitimate placement per §1 step 2 and the split-body note below).
4. If a sampled name returns zero matches across SKILL.md **and** all listed reference files, HALT "coverage-check: subagent inventory failed ground-truth spot-check — `{name}` claimed as export but absent from SKILL.md and the listed reference files".

These checks catch two hallucination classes: schema-shape drift (subagent paraphrased or dropped the contract) and fabricated exports (subagent invented names not in the document). Both are disqualifying for a grader skill — do not downgrade to a warning.

**Split-body traversal** is handled inside the subagent: if `references/` exists and `## Full` headings are absent or stubs in SKILL.md, the subagent extends its scan to all `references/*.md` files and includes them in the `exports` array. After split-body, Tier 2 content (Full API Reference, Full Type Definitions) lives in reference files — the inventory must reflect the full skill content regardless of where it resides.

### 1b. Cross-Check Split-Body Consistency

**Only execute if the subagent's `references` array is non-empty** (detected during split-body traversal in Section 1). Skip silently otherwise.

The subagent has already read both SKILL.md body and `references/*.md` files. For each function, class, type, or interface that appears in both the SKILL.md body AND any `references/*.md` file, instruct the subagent (or perform in the same subagent call from Section 1) to compare the documented signatures and include mismatches in its JSON output as a `cross_check_mismatches` array:

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
3. Returns only the JSON object below — no prose, no commentary, no markdown fences:

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

**Stack-skill branch (`metadata.json.skill_type == "stack"`):** A stack skill's own barrel is empty by design — it composes constituent skills rather than exporting a proprietary surface — so `total_exports` derived from its own barrel is `0` for a *correctly* built stack, and its `[from skill: …]` citations never trip §0's `[EXT:…]`-only docs-only trigger. The zero-exports HALT below targets individual source-based skills and must not fire for stacks. Derive the stack's coverage denominator (`stack_denominator`) from its composition surface, in priority order, and use it as `total_exports` for the rest of coverage scoring:

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

On a split-body skill the §1 inventory (documented surface) and the §2 AST output (source barrel) are two independent lists, so the `Documented` count must be their **intersection**, not a parent estimate. That reconciliation — set intersection/difference/cardinality plus the grep-verified numerator of the scalar/stack branches — is deterministic arithmetic with one correct answer per input, so it is performed by `uv run {reconcileScript}`, not by hand.

**Which branch applies — and therefore which `denominatorSource` the script runs — is the policy decision made here.** The denominator itself is resolved by §4/§4b; the script consumes the *already-resolved* denominator and does only the counting (`documented_set` is derived inside the script from the §1 `exports[]`, de-duplicated and with `kind: "method"` excluded — methods are members of an already-counted class/type, not top-level barrel exports). Pick exactly one branch:

1. **Enumerated path (`denominatorSource: "barrel"`)** — the common split-body case. `barrel_set` is the union of `exports_found[]` across every §2 per-file result. **When a stratified-scope or State-2 denominator applies (see §4) and it resolves to an enumerated name set** — the priority-2/3 re-derivation from `scope.tier_a_include` / `scope.include` globs — pass that resolved name set as `barrelSet` so the script intersects against it instead of the raw per-file union. The script computes `Documented := |documented_set ∩ barrel_set|`, `Missing := barrel_set − documented_set` (in source, not documented), `Stale := documented_set − barrel_set` (documented, not in source), and `Export Coverage = |Documented| / |barrel_set| * 100`.

2. **Scalar-denominator branch (`denominatorSource: "scalar"`)** — §4 priority 1, when the resolved denominator is the scalar `metadata.json.stats.effective_denominator` (a count with **no enumerated name set**). There is no `barrel_set` to intersect, so the script instead greps each `documented_set` name across `SKILL.md ∪ references/*.md` and counts appearances. Pass `denominatorValue: effective_denominator` and `skillPackagePath: {resolved_skill_package}`; the script sets `Missing := effective_denominator − Documented` and returns an empty `Stale` (not enumerable without a barrel name set). If §4b's numerator-ground-truth arm fires (it triggers only when `exports_documented == effective_denominator`), its verified count is authoritative and **overrides** this numerator — do not apply both.

3. **Stack-skill branch (`denominatorSource: "stack"`, `metadata.json.skill_type == "stack"`)** — a stack's source barrel is empty by design, so intersecting against it would divide by zero. Pass `denominatorValue: stack_denominator` (the §2b composition-surface denominator) and `compositionNames`: the provenance-map cited-contract names (`::`-excluded) when the map exists and is non-empty, else the `libraries` and `integration_pairs` names. The script greps each composition name across `SKILL.md ∪ references/*.md` for the numerator, sets `Missing := stack_denominator − Documented`, and omits `Stale` (no source barrel to enumerate against).

**Build the reconciliation input and run the script:**

```bash
echo '<JSON>' | uv run {reconcileScript} --stdin
```

Input JSON (one object — supply only the fields the chosen branch needs; `{reconcileScript}` is resolved relative to the skill root):

```json
{
  "denominatorSource": "barrel | scalar | stack",
  "exports": [ /* §1 inventory exports[] — used for barrel + scalar; kind:"method" entries are excluded automatically */ ],
  "barrelSet": [ /* barrel: resolved enumerated name set, when §4 supplies one */ ],
  "perFileResults": [ /* barrel: the §2 per-file results, unioned into barrel_set when no barrelSet */ ],
  "denominatorValue": 0,
  "compositionNames": [ /* stack: composition-surface names to grep */ ],
  "skillPackagePath": "{resolved_skill_package}"
}
```

The script returns (read these — **do not re-derive them by hand**):

- `documented` — the numerator (`|documented_set ∩ barrel_set|` for barrel; grep-verified count for scalar/stack)
- `missing` / `missingCount` — source names not documented (barrel enumerates the names; scalar/stack give only the residual count)
- `stale` / `staleCount` — documented names not in source (barrel only; empty with `staleApplicable: false` for scalar/stack)
- `denominator` — `|barrel_set|` (barrel) or the resolved scalar/stack denominator
- `exportCoverage` — `documented / denominator * 100`, already rounded

Carry these into §3's table/summary and §4's Export Coverage, and record the counts in the Coverage Analysis section (§5) so the numerator is auditable. The `exportCoverage` recorded here is the value step 5 feeds to `compute-score.py` — it is the script's value, not a parent estimate.

### 3. Build Coverage Results

Aggregate findings across all source files:

**Per-export status table:**

| Export | Type | Documented | Signature Match | File:Line | Status |
|--------|------|-----------|-----------------|-----------|--------|
| {name} | function/class/type | yes/no | yes/no/unverified | src/file.ts:42 | PASS/FAIL/WARN |

**Summary counts** (read from the §2c reconciliation script's JSON — not re-estimated here):
- Total exports in source: `denominator`
- Documented in SKILL.md: `documented`
- Missing documentation: `missingCount`
- Signature mismatches: {N}
- Undocumented in SKILL.md but not in source (stale docs): `staleCount`

### 4. Load Scoring Rules

Load `{scoringRulesFile}` to determine category scores:

- **Export Coverage:** the `exportCoverage` value returned by the §2c reconciliation script (`documented / denominator * 100`) — read it from the script's JSON, do not re-compute it here
- **Signature Accuracy:** (matching_signatures / total_documented) * 100 (Forge/Deep only, "N/A" for Quick)
- **Type Coverage:** (documented_types / total_types) * 100 (Forge/Deep only, "N/A" for Quick)

**Resolve the coverage denominator per `{sourceAccessProtocol}` (already loaded in §0b) — do not re-derive its ladders here.** Determine which §Source API Surface Definition clause matches this skill and apply that clause exactly as written: **stratified-scope** (monorepo curated subset), **multi-entry (exports-map)**, **specific-modules**, **pattern-reference**, or the **State 2** provenance-vs-metadata cross-reference (union on divergence). Each clause fixes its own resolution priority (prefer `metadata.json.stats.effective_denominator` → `scope.tier_a_include` → `scope.include` / subpath union), its deflation and inflation guards, the umbrella-barrel exclusion, and provenance-map canonicalization (including the fold summary the canonicalization records). Use the clause's resolved value as `total_exports`; when no clause matches, use the standard barrel-based denominator. Record the denominator source in the Coverage Analysis section using the exact `Denominator: {barrel | stratified (…) | multi-entry (…) | specific-modules (…) | pattern-reference (…)}` annotation string the matching clause specifies.

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
- exports-map subpath union: {N | absent}        {← chosen if the multi-entry clause applied}
- root barrel: {N}                               {secondary candidate — root-barrel-vs-subpath-union audit}
```

Readers can then spot-check whether the chosen denominator is reasonable
against the other two without re-running the extraction. A future reviewer who
suspects denominator gaming has the evidence inline. The `multi-entry` clause
requires the root-barrel named-export count in the `root barrel` row so the
root-barrel-vs-subpath-union choice is auditable.

### 4b. Metadata Export-Count Coherence Cross-Check

After the denominator has been resolved (standard, stratified, or State 2), cross-check export counts *within each semantic cluster* to detect extraction drift without false-positiving on intentional multi-denominator reporting. Picking the denominator silently when sources disagree is a known friction — the tester cannot tell whether to trust the pick, ignore the drift, or report it. Make it explicit, but only for counts that are authored to measure the *same* surface.

**Stack-skill branch (`metadata.json.skill_type == "stack"`):** Skip the intra-cluster and cross-cluster count comparisons, the `confidence_distribution` sum check, AND the numerator ground-truth check below — none apply to a stack. For a stack the three counts measure intentionally *different* surfaces, so comparing them yields only false drift: `exports_documented` / `exports[]` measure the stack's own barrel (empty by design → `0`), the provenance-map enumerates the cited *constituent* contracts, and `confidence_distribution` bins those constituents — so for a stack treat `confidence_distribution` as a per-constituent count (it sums to the constituent count, not to `exports_documented`) and do not assert it against `exports_documented`. The numerator-inflation arm below targets an *individual* skill whose `exports_documented` was padded to equal `effective_denominator`; a stack's numerator is instead computed by full-grep in §2c's stack-skill branch and stack `metadata.json.stats` carries no `effective_denominator`, so the arm is not run. Record the denominator using the §2b source — `Denominator: stack composition ({N} cited contracts)` when the provenance-map supplied it, or `Denominator: stack composition ({N} libraries + integration pairs)` when the composition surface did — then proceed.

**Reference-app branch (`metadata.json.scope_type == "reference-app"`):** Skip the intra-cluster and cross-cluster count comparisons, the `confidence_distribution` sum check, AND the numerator ground-truth check below — none apply to a reference app, whose counts measure intentionally *different* surfaces. A reference app documents wiring/construct **pattern surfaces**, not a library export barrel, so `metadata.json.exports[]` is empty by design (`0`), `stats.exports_public_api` / `stats.pattern_surfaces_documented` count the documented pattern surfaces, and `confidence_distribution` bins the per-citation provenance entries (it sums to the citation count, not to `pattern_surfaces_documented`). Comparing these yields only false drift: a spurious Cluster-A "barrel drift" (`exports_public_api` vs `exports[].length == 0`) and a Cluster-B "documented-surface drift" (`pattern_surfaces_documented` vs the larger `confidence_distribution` sum). The numerator-inflation arm also does not apply — a reference app carries no `effective_denominator` (see the `skf-create-skill` reference-app carve-out), so the `exports_documented == effective_denominator` signature never fires. Record the denominator as `Denominator: pattern-surface ({pattern_surfaces_documented})` and proceed. (`referenceApp` and a stack skill are distinct signals — a skill is one or the other, never both, so only one of these two branches applies.)

**Collect available counts (skip any that are absent) and bin them into two clusters:**

**Cluster A — public-barrel surface** (what `__init__.py` / `index.ts` / `lib.rs` re-exports):

1. `metadata.json.stats.exports_public_api` — the declared public API count
2. `metadata.json.exports[]` array length — the enumerated public export list

**Cluster B — documented surface** (what was extracted and documented, including methods and submodule members):

3. `metadata.json.stats.exports_documented` — the declared documented count
4. Provenance-map **named-export count** (if `{forge_data_folder}/{skill_name}/provenance-map.json` exists) — pass the raw `export_name` values as `provenanceExportNames`; the script counts top-level named exports, **excluding entries whose `export_name` contains `::`** (impl-block methods like `Type::method`, which roll up under an already-counted type and are not separate barrel exports). Comparing the raw entry count instead false-positives on any method-enumerating provenance map (common for Rust/TS type-heavy skills): e.g. a map with 88 named exports + 48 `Type::method` entries reports 136 against `exports_documented` ≈ 92 → a spurious ~32% Cluster-B drift, while the comparable named-export count (88) agrees within ~4%.
5. `confidence_distribution` (`t1`, `t1_low`, `t2`, `t3`, when present in `metadata.json.stats`) — pass the tiers as `confidenceDistribution`; the script sums them. Every extracted/documented export is binned into exactly one confidence tier, so the distribution must sum to the documented-surface total; a divergence (e.g., distribution sums to 91 while `exports_documented` is 85) is an internal-consistency defect even when the two clusters look fine

Cluster assignment is canonical: `skf-create-skill` step 5 derives `exports_public_api` from entry-point validation and writes the `exports[]` array from the same barrel surface (see `skf-create-skill/references/compile.md:105`), while `exports_documented` tracks the broader documented surface that the provenance-map also enumerates.

**Delegate the drift arithmetic to `uv run {coherenceScript}`.** The intra-cluster / cross-cluster `>10%` comparisons are deterministic count arithmetic with one correct answer per input, so the script — not the prompt — owns the binning, the divergence percentages, and every skip condition (a cluster with fewer than two present counts, and clusters that agree within the threshold, are skipped inside the script). Build the input from the counts collected above and run it (`{coherenceScript}` resolves relative to the skill root):

```bash
echo '<JSON>' | uv run {coherenceScript} --stdin
```

Input JSON (omit any count that is absent; `driftThresholdPct` defaults to `10`):

```json
{
  "skillType": "{metadata.json.skill_type or null}",
  "scopeType": "{metadata.json.scope_type or null}",
  "clusterA": {"exports_public_api": 0, "exports_length": 0},
  "clusterB": {"exports_documented": 0},
  "provenanceExportNames": [ /* raw provenance-map export_name values — the script excludes `::` impl-block methods and counts the rest */ ],
  "confidenceDistribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0}
}
```

The script returns `{"skipped": bool, "clusterACounts": {...}, "clusterBCounts": {...}, "findings": [...]}`. Read `findings[]` and append each entry directly — **do not re-derive the percentages by hand.** Each entry carries `severity`, `title`, `detail` (the enumerated counts + drift %), and `category: structural/metadata coherence`:

- A **Medium** `metadata drift — {barrel|documented-surface} export counts diverge` is the real drift signal — the two sources should mirror the same surface and they don't, so upstream extraction or compilation produced inconsistent output that a re-compile should reconcile. It is classified under structural/metadata coherence regardless of naive/contextual mode.
- An **Info** `multi-denominator reporting — barrel vs documented surface` is expected for skills whose documented surface intentionally exceeds the barrel (methods, submodule members, re-exported classes) — it is not drift. The note exists so the test report makes the dual-denominator design visible and auditable without demanding action.

(The stack and reference-app branches above already skip this delegation; the script also returns `skipped: true` when passed their `skillType` / `scopeType`, so an unconditional call stays safe.)

**Numerator ground-truth — force a full grep on the inflation signature.** The intra/cross-cluster checks above only compare *counts*; they cannot tell whether the declared exports actually appear in the skill. When `metadata.json.stats.exports_documented == effective_denominator` exactly (numerator equals denominator — the signature of a numerator padded to match the full surface), do not trust the documented count: grep the full declared set (the `metadata.exports[]` / provenance-map names, not the §1a 3-sample) against `SKILL.md ∪ references/*.md`. That grep + present/absent set-diff + count has one correct answer per input, so it runs in `uv run {numeratorVerifyScript}`, not in-prompt (`{numeratorVerifyScript}` resolves relative to the skill root):

```bash
echo '{"declaredNames": [ /* full declared set */ ], "skillPackagePath": "{resolved_skill_package}"}' | uv run {numeratorVerifyScript} --stdin
```

Read the script's output — do not re-derive it by hand:

- `inflated: false` (`verified == declared`) → the skill is genuinely fully documented; no finding, coverage stands.
- `inflated: true` (`verified < declared`) → emit a **High**-severity gap `numerator inflation — {declared − verified} of {declared} declared exports absent from SKILL.md/references` listing the script's `absent[]` names, and use `verified` as the Export Coverage numerator (overriding `exports_documented`). A numerator padded to equal the denominator otherwise produces a tautological 100% that passes the gate.

The grep runs only on the exact-equality signature, so it adds no cost to the common case where the numerator is already below the denominator. Unlike the count-coherence findings above, this arm is authoritative — it changes the numerator used for scoring.

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

Report the coverage result to the user: the {forge_tier}-tier analysis of {file_count} source files, the documented ratios for exports / signatures / types (signatures and types are N/A for Quick tier), and the issue count — full details are in the Coverage Analysis section. Then proceed to the coherence check.

Update stepsCompleted, then load and execute {nextStepFile}.

