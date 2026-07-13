---
nextStepFile: 'report.md'
descriptionGuardProtocol: '{project-root}/src/shared/references/description-guard-protocol.md'
# Resolve `{descriptionGuardHelper}` by probing `{descriptionGuardProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback);
# first existing path wins. HALT if neither resolves — letting an external
# tool's rewrite of the merged description field stand would silently
# regress discovery quality and re-introduce angle-bracket tokens.
descriptionGuardProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-description-guard.py'
  - '{project-root}/src/shared/scripts/skf-description-guard.py'
# Resolve `{updateActiveSymlinkHelper}` to the first existing path; HALT if
# neither candidate exists. §5b uses it to atomically flip the active
# symlink; §6 uses it (verify mode) to confirm the post-state. Without
# the helper, §5b's "rm and recreate" pattern leaves a brief window where
# concurrent readers see a missing symlink.
updateActiveSymlinkProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-active-symlink.py'
  - '{project-root}/src/shared/scripts/skf-update-active-symlink.py'
# Resolve `{verifyProvenanceCompletenessHelper}` to the first existing path.
# §6a runs Check D (Provenance Completeness), deferred from step 5 because it
# needs both metadata.json + provenance-map.json on disk: the export/provenance
# set-diff (missing + orphaned entries) and file:line citation resolution.
# Advisory — do not HALT if neither path resolves; fall back to the in-prose
# set comparison §6a documents (graceful degradation).
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# candidate exists. §1 uses its `manual-verify` subcommand to verify the
# post-merge file against the byte-exact [MANUAL] inventory captured in step 1
# §5; a marker-count comparison would pass a block whose interior was truncated
# without changing the marker count.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# Resolve `{renderMetadataStatsHelper}` by probing `{renderMetadataStatsProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT if neither resolves — §2's `stats` block and
# `confidence_distribution` are computed values that must not be hand-binned,
# and this is the same helper sibling create-skill compiles them with.
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 6: Write Updated Files

## STEP GOAL:

Verify the merged SKILL.md that step 4 section 6b wrote to disk, then write the derived artifacts (metadata.json, provenance-map.json, evidence-report.md, context-snippet.md, and the active symlink).

## Rules

- Focus only on verifying merged files and writing derived artifacts — merge content was already written in step 4
- Do not modify merged SKILL.md content — any mismatch detected during verification triggers HALT, not repair
- Do not skip provenance map update — critical for future audits
- HALT immediately on verification failure before writing any derived artifact — a partial-write skill package is worse than an unchanged one

## Steps

### 0. Description Guard Protocol

**Used by:** §7 (`skill-check check --fix` and `skill-check split-body --write`), and any future tool invocation that may modify SKILL.md's frontmatter on disk.

Load `{descriptionGuardProtocol}` for the full prose explanation of the four-phase guard (why it exists, what counts as divergence, why token-stream comparison is the right shape). The deterministic phases are executed via `{descriptionGuardHelper}` — §7 invokes the helper at the capture and verify-restore points around every `skill-check` call.

Update-skill does not run the optional post-restore frontmatter re-validation today — the post-write checks in §1 catch downstream issues, and a `restored: true` outcome is already surfaced through the evidence report (§4).

### 1. Verify SKILL.md Write

SKILL.md was written in step 4 section 6b. Verify the write landed intact before proceeding to any derived-artifact writes.

- Verify the resolved `{skill_package}` path matches the version directory step 4 wrote to (if the version changed, step 4 updated `{skill_package}` in context to point at the new path)
- Run the deterministic [MANUAL]-integrity verifier against the byte-exact inventory captured in step 1 §5:

  ```bash
  uv run {hashContentHelper} manual-verify {skill_package}/SKILL.md \
      --inventory {manual_inventory}
  ```

  The verdict JSON is `{"preserved":[...], "modified":[...], "missing":[...], "moved":[...], "ok":bool}`. A `modified` block is one whose byte-exact interior changed (an interior truncation); a `missing` block lost its markers entirely; a `moved` block is byte-identical but relocated with its logical parent section (clean — does not fail the gate). `ok == (modified empty AND missing empty)`.
- If `ok == true` and the path resolves: proceed to section 2
- **If `ok == false`: HALT immediately** with status `halted-for-manual-mismatch`. Do not write `metadata.json`, `provenance-map.json`, or any other artifact — further writes would compound the inconsistency. In `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "write:verify-manual-integrity", path: "{skill_package}/SKILL.md", reason: "..."}`). Alert the user:

  "**[MANUAL] section integrity failure after write.** Blocks modified (interior changed): {modified}. Blocks missing (markers lost): {missing}. Relocated-but-intact (advisory only): {moved}. Verified against the step-1 inventory `{manual_inventory}`, on disk at `{skill_package}/SKILL.md`. The skill package is in an inconsistent state. Manual recovery required — restore the previous version from `{skill_group}/{previous_version}/` or fix the file in place, then re-run update-skill."

### 2. Write Updated metadata.json

Update `{skill_package}/metadata.json`:
- **First, apply any queued `metadata_patches[]`** (staged by merge Priority 8b from gap-driven `metadata update` entries): apply each surgical patch described in the gap's remediation (reconcile a divergent count, add an explanatory stat, etc.) *before* the automatic recount below, so the recount overrides only the fields it owns and the patch survives for any field it does not. If a patch and the recount disagree on a field the recount owns (e.g., `exports_documented`), the recount wins — log the divergence so a still-stale stat surfaces in the report rather than being silently overwritten.
- **For gap-driven rescopes** (`DELETED_EXPORT` / verification `rescoped`): the removed exports are already dropped from the `exports` array below, and `stats` recompute from that reduced surface — never set a `stats` count by hand to match the documented total. The reduction is justified by the `brief.scope.exclude` + `scope.amendments[]` (`action: "excluded"`) written in step 2; the recount simply reflects the smaller surface.
- Update `version`: **if `update_mode == "gap-driven"`, do not bump — the skill is being repaired against the same source commit, so leave `version` unchanged and update only `generation_date` / `last_update` below.** This keeps metadata `version` consistent with the on-disk `{skill_package}` path, which step 4 §6b also leaves unchanged in gap-driven mode (see step 4 §6b's "If the source version detected during step 3 differs..." carve-out — in gap-driven mode no source version is detected, so step 4 writes into the existing version directory). Otherwise, if a source version was detected during re-extraction and differs from the current metadata version, use the source version; otherwise increment patch version
- Update `generation_date` timestamp to current ISO-8601 date
- Update `exports` array to reflect current export list
- **Compute the `stats` block and `confidence_distribution` deterministically** with `{renderMetadataStatsHelper}` (resolve from `{renderMetadataStatsProbeOrder}`; first existing path wins) — the same helper sibling create-skill compiles them with, so create and update emit byte-identical stats for identical inputs. The helper owns all the arithmetic: it bins each provenance `entries[]` row once by its `signature_source` tier into `confidence_distribution.{t1,t1_low,t2,t3}`, sets `exports_documented` = the entry count, and derives `exports_total` = `exports_public_api` + `exports_internal`, `public_api_coverage` = documented / public_api (`null` if public_api is 0), `total_coverage` = documented / total (`null` if total is 0), plus `scripts_count` / `assets_count` from the inventory arrays. Run `uv run {renderMetadataStatsHelper} --help` for the full contract. Do not hand-bin the distribution — binning T2 annotations + T3 doc items on top of the per-export tiers double-counts, which per-entry binning by `signature_source` makes structurally impossible. You supply only the judgment payload:

  **Judgment payload (what you decide — passed as JSON on stdin):**
  - `exports_public_api`: count of exports from public entry points (`__init__.py`, `index.ts`, `lib.rs`, or equivalent)
  - `exports_internal`: count of all other non-underscore-prefixed exports
  - `scripts` / `assets`: the scripts / assets inventory arrays (or `[]` when empty) — the helper sets `scripts_count` / `assets_count` from their lengths

  **Invoke** — since the helper reads `entries[]`, stage §3's `provenance-map.json` write first (§3 does not depend on these stats):

  ```bash
  echo '{"exports_public_api": {N}, "exports_internal": {M}, "scripts": {scripts-inventory-or-[]}, "assets": {assets-inventory-or-[]}}' \
    | uv run {renderMetadataStatsHelper} {forge_version}/provenance-map.json
  ```

  Write the returned `stats` and `confidence_distribution` objects into `metadata.json` **verbatim**. If the helper reports `coherence.ok: false`, some provenance entries carry a missing/unrecognized `signature_source` (§3 must write it on every entry) — fix the provenance map, do not hand-edit the stats.

### 3. Write Updated provenance-map.json

Write to `{forge_version}/provenance-map.json`:

**Every entry this step writes or rewrites carries a `signature_source` (`T1` / `T1-low` / `T2` / `T3`)** — the tier that contributed the structural signature, matching create-skill's entry contract. §2's stats helper bins each entry on this field, so a missing value trips its `coherence.ok: false` check. Preserve it byte-identical on untouched entries; set it from the contributing extraction tier on every re-extracted or new entry.

**If `no_reextraction == true` (gap-driven mode from step 3 section 0):**
Dispatch per-entry on the verification outcome recorded by step 3 — gap-driven runs produce a mix of `verified`, `moved`, `re-extracted`, and `unknown` outcomes, and each requires a different provenance-map write strategy:

- **`verified` exports**: no fresh extraction data exists — do NOT overwrite `confidence`, `extraction_method`, `ast_node_type`, `params[]`, `return_type`, `source_file`, or `source_line`. The provenance entry stays byte-identical.
- **`moved` exports**: update `source_line` (and `source_file` if different) to the new location recorded by the spot-check. Do not touch other fields.
- **`re-extracted` exports** (resolved via step 3 §0a's Targeted Re-Extraction Branch from `remediation_paths[]`): write a full entry — `source_file`, `source_line`, `confidence`, `extraction_method`, `ast_node_type`, `params[]`, `return_type` — from §0a's fresh AST extraction record. This is the only gap-driven outcome that produces normal-mode-quality provenance; do NOT fall through to the byte-identical preservation above.
- **`unknown` exports** (not in provenance map; no `source_citation`; `severity` is `Medium`, `Low`, or `Info`, OR `remediation_paths[]` was empty and §0a did not halt): add new entries with fields populated from step 4 merge output. `source_file`/`source_line` may be `null` here — leave these fields unset rather than writing stale values. **This path is only acceptable for `severity` in `Medium`, `Low`, or `Info`.** A Critical/High `unknown` reaching this branch indicates step 3 §0a was skipped or bypassed and is a workflow bug — step 3 §0a should have halted with status `halted-for-remediation-path` before step 6 ran. If you encounter one, halt with a pointer to §0a rather than writing null citations for a blocking gap.
- **`rescoped` exports** (`DELETED_EXPORT`, removed from the public surface per detect-changes §0 rule R1): remove the entry from the provenance map — identical to the normal-mode "For deleted exports" path below. The reduction's audit trail is the `brief.scope.exclude` + `scope.amendments[]` (`action: "excluded"`) entry written in step 2; do not record the removal by editing `stats` directly — §2 recomputes `stats` from the reduced `exports` array.
- Skip the "For each export in the updated skill" bullets below — they apply only to normal re-extraction mode.

**For each export in the updated skill (normal mode only):**
- Update `export_name` if renamed
- Update `params[]` array if parameters changed (add, remove, or modify individual entries)
- Update `return_type` if changed
- Update `source_file` if moved
- Update `source_line` from fresh extraction
- Update `confidence` from extraction results
- Update `extraction_method` and `ast_node_type` if re-extracted with different tools

**For deleted exports:**
- Remove entry from provenance map

**For new exports:**
- Add new entry with full structured fields: `export_name`, `export_type`, `params[]`, `return_type`, `source_file`, `source_line`, `confidence`, `extraction_method`, `ast_node_type`

**For script/asset file changes (if `file_entries` exists):**
- MODIFIED_FILE: copy updated file to `scripts/` or `assets/`, update `content_hash` in `file_entries`
- DELETED_FILE: remove file from `scripts/` or `assets/`, remove entry from `file_entries`
- NEW_FILE: copy file to `scripts/` or `assets/`, add entry to `file_entries` with `file_name`, `file_type`, `source_file`, `confidence: "T1-low"`, `extraction_method: "file-copy"`, `content_hash`

**Add update operation metadata:**
```json
{
  "last_update": "{current_date}",
  "update_type": "{incremental if normal mode | full if degraded_mode}",
  "files_changed": {count},
  "exports_affected": {count},
  "confidence_tier": "{tier}",
  "manual_sections_preserved": {count}
}
```

`manual_sections_preserved` = `len(preserved) + len(moved)` from the §1 `manual-verify` verdict (blocks that survived byte-identical, whether in place or relocated). Do not re-count markers by hand — the §1 verdict is the deterministic source.

### 4. Write Updated evidence-report.md

Append update operation section to `{forge_version}/evidence-report.md` (create the file with a standard header if it does not yet exist):

```markdown
## Update Operation — {current_date}

**Trigger:** {manual / audit-skill chain}
**Forge Tier:** {tier}
**Mode:** {normal / degraded}

### Changes Detected
- Files modified: {count}
- Files added: {count}
- Files deleted: {count}
- Exports affected: {total}

### Merge Results
- Exports updated: {count}
- Exports added: {count}
- Exports removed: {count}
- [MANUAL] sections preserved: {count}
- Conflicts resolved: {count}

### Validation Summary
- Spec compliance: {PASS/WARN/FAIL}
- [MANUAL] integrity: {PASS/WARN/FAIL}
- Confidence tiers: {PASS/WARN/FAIL}
- Provenance: {PASS/WARN/FAIL}

### Description Guard
- Restored: {true/false}
- Triggering tool: {tool_name or —}
- Original description preserved: {true/false}
- Notes: {one-sentence detail or —}

### Context Snippet
- Regenerated: {true/false}
- Triggers fired: {list or —}
- Notes: {one-sentence detail or —}
```

**Description Guard population** (used by §7 Post-Write Validation when the §0 protocol fires): fill all four fields from context when `description_guard_restored == true` (triggering tool, whether restore succeeded, what changed). When `Restored: false`, the other three fields are `—` — this is the clean-run expected state. Same field semantics and populator logic as create-skill step 6 §8.

**Context Snippet population** (used by §5 after the staleness check runs): §4 writes the sub-block with placeholders; §5 updates the on-disk evidence report in place after deciding whether to regenerate. Set `Regenerated: true` and populate `Triggers fired` with any combination of `headline-exports`, `version`, `gotchas` when at least one trigger fired. Set `Regenerated: false` and `Triggers fired: —` when none fired (the gap-driven / internals-only outcome). Always fill `Notes` with a one-sentence reason (e.g., `"Gap-driven repair — no snippet surface changed"`, `"Version bumped 0.1.0 → 0.2.0; headline exports re-ranked"`).

### 5. Regenerate context-snippet.md

**Regenerate `context-snippet.md` if stale:**

`context-snippet.md` is a `{skill_package}` deliverable that goes stale whenever **headline exports**, **version**, or **gotchas** change in this run. Regenerate it only when at least one of these triggers fired; otherwise skip — a skip is the correct outcome for gap-driven repairs and other runs that touch internals below the snippet's surface, where regenerating would produce byte-identical content.

**Staleness triggers:**

- **Headline exports changed** — the top-K exports surfaced in the snippet differ from the prior snippet (a `NEW_EXPORT` was promoted into a headline slot, or a `MODIFIED_EXPORT` changed the signature/shape of a surfaced export).
- **Version changed** — §2 bumped `version` (normal mode with detected source drift; never fires in gap-driven mode per §2's carve-out).
- **Gotchas changed** — new gotchas surfaced from this run's evidence that were not in the prior snippet, or a prior gotcha was invalidated and removed.

**Record the decision on the on-disk evidence report:** open `{forge_version}/evidence-report.md` (written by §4 with placeholder values in the `### Context Snippet` sub-block) and update that sub-block under the Update Operation section just written. Set `Regenerated: true|false`, fill `Triggers fired:` with the list of triggers that fired (or `—` when none), and write a one-sentence `Notes:` entry. See §4's "Context Snippet population" note for field semantics.

**If no trigger fired:** skip regeneration — do not touch `context-snippet.md` on disk. The snippet remains valid against the prior run's surface. Continue to §5b.

**If at least one trigger fired:** regenerate the snippet using the format from `skf-create-skill/assets/skill-sections.md` (pipe-delimited indexed format).

Use the **flat draft form** for the `root:` path in the draft snippet: `root: skills/{skill-name}/`. The per-IDE skill root (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/` — see `skf-export-skill/assets/managed-section-format.md`) is applied later by `export-skill` step 3 when the skill is exported. Do not choose an IDE-specific prefix in update-skill — that is an export-time decision that depends on config.yaml.

Pull values for the regenerated snippet from the updated metadata.json (version, top exports), the merged SKILL.md (section anchors, inline summaries), and the evidence report (new gotchas). If gotchas cannot be derived from the updated evidence but the prior snippet has a `|gotchas:` line, carry forward the prior line with the `[CARRIED]` marker — see `skf-export-skill/references/generate-snippet.md` for the carry-forward protocol (one-cycle limit).

Write the regenerated snippet to `{skill_package}/context-snippet.md`, preserving file permissions.

### 5b. Update Active Symlink

Flip `{skill_group}/active` to point at the current `{version}` via the helper. The call is **always** run — atomic, idempotent, and verified in one shot. The helper's no-op path handles the "version did not change" case (gap-driven mode, or no source drift) without writing to disk:

```bash
uv run {updateActiveSymlinkHelper} update \
    --skill-group {skill_group} \
    --version {version}
```

The helper emits a result envelope with `status` ∈ `{ok, flipped, mismatch, missing-target}` and a pre-formatted `log_message`. Log the message to the evidence report.

**Dispatch on `status`:**

- **`ok`** (exit 0): symlink already points at `{version}` — no disk write. Continue to §6.
- **`flipped`** (exit 0): symlink was atomically updated (temp-and-replace). Continue to §6.
- **`missing-target`** (exit 2): `{skill_group}/{version}/` directory does not exist on disk. HALT — display `halt_message` verbatim. This indicates §4 §6b did not write the version directory before §5b ran (a workflow bug, not a user error).
- **`mismatch`** (exit 2): re-read after flip showed the symlink still points elsewhere. HALT — display `halt_message`. Should be impossible because the helper uses `os.replace` (atomic rename); a mismatch here indicates filesystem-level interference (concurrent writer, broken FUSE mount).

Both exit-2 halts carry status `halted-for-write-failure`; in `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "write:active-symlink", reason: "..."}`).

### 6. Verify Derived Artifact Writes

SKILL.md was verified in section 1 (written by step 4 section 6b). This section verifies the artifacts this step wrote: `metadata.json`, `provenance-map.json`, `evidence-report.md`, `context-snippet.md`, and the `active` symlink from §5b.

For each derived artifact:
- Read back the file
- Confirm content matches expected output
- Report verification status

**Active symlink verification:** run `{updateActiveSymlinkHelper} verify --skill-group {skill_group} --version {version}` — read-only check that the symlink resolves to the version just written to `metadata.json` in §2. This closes the §5b gap where a silent skip would otherwise leave the manifest and symlink divergent — the symlink is the fallback resolver for consumers that don't read the manifest (see `knowledge/version-paths.md` §Reading Workflows step 5), so a `mismatch` must fail the step, not warn. Applies in every mode — gap-driven runs do not bump `version`, but the symlink must still point to the current `version`, otherwise a prior partial run left it pointing elsewhere.

"**Write Verification:**

| File | Status |
|------|--------|
| SKILL.md | {VERIFIED in section 1} |
| metadata.json | {VERIFIED/FAILED} |
| provenance-map.json | {VERIFIED/FAILED} |
| evidence-report.md | {VERIFIED/FAILED} |
| context-snippet.md | {VERIFIED/FAILED} |
| {skill_group}/active symlink | {VERIFIED/FAILED} (readlink → {resolved_version}, expected {version}) |

**On symlink `mismatch` (helper exit 2):** HALT with status `halted-for-write-failure`. Do not proceed to §7 post-write validation or §8 menu. Display the helper's `halt_message` verbatim — it already includes the diverged target, the expected version, and the recovery command; in `{headless_mode}`, emit the halt envelope per SKILL.md §Headless (`error: {phase: "write:verify-active-symlink", reason: "..."}`). This matches the severity of the other four artifact checks — silent divergence here mis-routes any downstream consumer that uses the symlink fallback.

**All files written and verified.**"

### 6a. Provenance Completeness (Check D — Deferred from Step 05)

`validate.md` Check D (Provenance Completeness) is a deterministic set-diff plus citation resolution, and it needs both `metadata.json` (written in §2) and `provenance-map.json` (written in §3) on disk — neither exists at validate time, so the check is deferred here. Run it against the just-written artifacts via `{verifyProvenanceCompletenessHelper}`:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {skill_package}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {source_root}
```

The helper reads its `--source-root` (falling back to the provenance map's own `source_root` field when the flag is omitted); pass the resolved `{source_root}` so citation resolution runs against the same tree re-extraction read. **Read the emitted JSON — do NOT recompute the set operations by eye; an LLM set-diff can silently pass a dropped or orphaned entry:**

- `missing[]` — documented exports (metadata `exports[]`) with no provenance entry: a coverage gap.
- `orphaned[]` — provenance `entries[].export_name` whose export was removed but the entry remains.
- `stale[]` — entries whose `source_file:source_line` no longer resolves; each carries a `reason` of `file-missing`, `line-out-of-bounds`, or `line-invalid`. Internal names are canonicalized through `reexport_map` before the diff, so a barrel-renamed export does not read as missing or orphaned.
- `summary.stale_check` — `"checked"` when citations were resolved against the source tree, or `"skipped-no-source-root"` when no source root resolved on disk (the completeness + orphan diffs still ran; `stale` is empty by construction, not clean-by-verification).

Map `status` to the `Provenance:` line of the §4 evidence report's Validation Summary: `PASS` when `status == "pass"`, `WARN` when `status == "findings"` (this is the persistent record — step 5 §5's table was rendered before the provenance map existed, so it necessarily showed this row as deferred). Provenance findings are **advisory** — they do not block the update. Surface each `missing` / `orphaned` / `stale` entry in the evidence report's Validation Summary so the user can decide, and note when `stale_check` was `skipped-no-source-root`.

**Graceful degradation:** if neither probe path resolves (no `uv` / script available), fall back to the manual set comparison the script encapsulates — enumerate metadata `exports[]` and provenance `entries[].export_name` (canonicalizing internal names through `reexport_map`), diff the two sets for missing/orphaned entries, and spot-check that each `source_file:source_line` still points at a real line in the source tree. Prefer the script — it does this deterministically.

### 7. Run Post-Write Validation (Deferred from Step 05)

External tool checks deferred from step 5 now run against the written files.

**Description Guard Protocol:** every invocation below that may modify SKILL.md (`skill-check check --fix` and any `split-body` write) must run inside the four-phase guard defined in §0. Invoke `{descriptionGuardHelper}` at the capture and verify-restore points around each call:

```bash
# Phase 1 — capture before any frontmatter-touching tool call
uv run {descriptionGuardHelper} capture {skill_package}/SKILL.md
# stash returned `description` as `guarded_description`

# Phase 2 — run the tool (skill-check --fix, split-body --write, etc.)

# Phases 3+4 — verify and restore after the tool call
uv run {descriptionGuardHelper} verify-restore {skill_package}/SKILL.md \
    --captured-description "{guarded_description}"
```

Do not rely on per-call ad-hoc preservation logic — use the helper.

**If skill-check available:**

- Run: `npx skill-check check {skill_package} --fix --format json --no-security-scan` **inside the §0 guard**.
- **Context sync after --fix:** If `fixed[]` is non-empty (i.e., `--fix` modified files on disk), re-read the modified SKILL.md to update the in-context copy. This prevents silent divergence between the in-context SKILL.md and the on-disk version that report will reference. The §0 guard has already restored `description` if divergent; the re-read picks up any other fix-corrected content.
- If `body.max_lines` reported, prefer selective split — extract only the largest Tier 2 section(s) to `references/`, keeping Tier 1 inline (inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval). **If falling back to `npx skill-check split-body {skill_package} --write`, run it inside the §0 guard** — split-body can also touch frontmatter. Verify anchors resolve after split.
- Run: `npx skill-check diff` if original version was preserved.
- Run: `npx skill-check check {skill_package} --format json` for security scan. (Read-only; guard not required.)

Record findings in the evidence report (section 4), including any `description_guard_restored` events recorded by the §0 protocol. These are advisory — do not block on warnings.

**If skill-check unavailable:** Skip with note — structural checks from step 5 are sufficient.

### 8. Route to Next Step

This step auto-proceeds — no user choices. Once all files have been written and verified and post-write validation is complete, display "**Proceeding to report...**", then load, fully read, and execute `{nextStepFile}` to display the change report.

