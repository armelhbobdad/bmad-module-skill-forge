---
nextStepFile: 'merge-write.md'
# Resolve `{hashContentHelper}` to the first existing path; HALT if neither
# exists: §4 amends the [MANUAL] inventory with the user's decisions, which
# merge-write.md §6b verifies the merged SKILL.md against.
hashContentProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
# SKILL.md binds `{emitEnvelopeHelper}` and `{runStateHelper}` for every
# stage; resolve them again when a binding was lost: first existing path wins.
# §4's gate decisions and warnings go to the run log through the first, and
# the halt procedure runs the second.
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
runStateProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-update-run-state.py'
  - '{project-root}/src/shared/scripts/skf-update-run-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Merge

## STEP GOAL:

Merge freshly extracted export data into the existing SKILL.md and its references/*.md while preserving all [MANUAL] sections. Detect and resolve conflicts where regenerated content overlaps developer-authored content; merge-write.md then writes the merge to disk.

## Rules

- Focus only on merging extractions into existing skill content
- Never delete or modify [MANUAL] section content without the user's section 4 [R]/[E] decision
- Write nothing outside `{run_dir}`: merge-write.md writes the merge to disk
- If [MANUAL] conflicts detected: halt and present to user (headless: HALT, nothing written, on any ORPHAN or STALE_REFERENCE conflict; otherwise keep each POSITION block). A clean or resolved merge goes on to write
- When a helper is not bound, it resolves to the first existing path in its probe order: `{emitEnvelopeHelper}` in `{emitEnvelopeProbeOrder}` and `{runStateHelper}` in `{runStateProbeOrder}`.

## Steps

**Halt procedure.** Every HALT in this step names its payload (`status`, `phase`, `path` when it has one, and `reason`), displays its message, and then runs, from `{project-root}`, the `{runStateHelper}` `halt` call below.

```bash
uv run {runStateHelper} halt --run-dir "{run_dir}" \
    [--tree "{source_tree}"] \
    [--lock "{forge_data_folder}/{skill_name}/.skf-update.lock" --owner "{lock_owner}"] \
    [--emit] <<'SKF_JSON'
{"status": "<status>", "phase": "<phase>", "path": "<path; leave the key out when the halt names none>", "reason": "<reason>", "skill_name": "{skill_name}", "version": "<the metadata.json version>", "previous_version": "<the same>", "update_mode": "<normal, gap-driven or degraded>"}
SKF_JSON
```

Pass `--tree` when load-baseline.md §6b bound `{source_tree}`, always `--lock` and `--owner`, and `--emit` in `{headless_mode}`. It removes the private source tree, releases the run lock and, with `--emit`, prints the halt's `SKF_UPDATE_RESULT_JSON:` line, with a warning (`source-tree-not-removed`, `run-lock-not-released`) for each step it could not finish: do none of it yourself. Write each payload value as a JSON string: escape `"` and `\`, and write every path with `/`. Display the line it prints verbatim. When it exits 1 and its message names the payload, fix the payload once and run it again, which redoes nothing already done; when it still fails or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing. A HALT that names no payload (a helper the frontmatter says to HALT without, resolving to no path) takes `status: "blocked"`, `phase: "merge:<the helper's file name>"` and `reason: "<the helper's file name> is missing; re-install SKF"`.

The halt leaves `{run_dir}` in place.

**Warnings go to the run log.** Record each warning this step adds to `warnings[]` the moment it is raised: write its text to `{run_dir}/warning.txt` with a file write (a warning can hold quotes, `$` or backticks), then, from `{project-root}`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`. The halt line and the result line read warnings only from `{run_dir}/warnings.jsonl`.

### 2. Extract [MANUAL] Blocks

From the [MANUAL] inventory captured in step 1:
- Extract every `<!-- [MANUAL:section-name] -->` ... `<!-- [/MANUAL:section-name] -->` block
- Map each block to its parent section heading: when the generated content around a block moves, the block moves with that section
- Store blocks in a preservation map keyed by section-name
- A block nested inside another is an ERROR: flag it, since blocks never nest

### 3. Apply Merge by Priority Order

Read this step's inputs from disk, never from memory: the change manifest from `{run_dir}/change-manifest.json` (step 2, or gap-driven.md §1 in gap-driven mode), and the extraction or verification records from `{run_dir}/reextract-records.json` (step 3, or gap-spot-check.md §4). A compacted context still merges what those steps found. A gap-driven record in `files` that carries a `local` name was matched by its public name (a renamed re-export): document it under that public name, its `name`, saying it re-exports the declared `local` name.

Apply merge in the following priority order.

**A split-body skill** (one whose `references/*.md` files document exports, the `## Full` sections a body split moved among them): Priorities 1 to 5 apply their change to every file that documents the export, SKILL.md and each `references/*.md` alike. Priority 1 removes the export's content from each file, and deletes a reference file it leaves documenting nothing and holding no `[MANUAL]` block, with SKILL.md's `> See` pointer to that file; merge-write.md §6b moves its citations (`[AST:]` and `[SRC:]` alike) in each by script (Priority 2), never by hand, Priority 3 renames it in each, Priority 4 replaces its content in each, and Priority 5 adds a new export where the skill documents that kind of export (a `references/*.md` file when the skill keeps that kind there) and corrects any statement, in SKILL.md or a `references/*.md` file, that calls the new export not covered. [MANUAL] blocks are inventoried and verified in SKILL.md only: nothing re-checks one in a `references/*.md` file yet, so the merge leaves such a block untouched, as it never edits inside one in SKILL.md without the user's §4 decision. merge-write.md §6b writes each `references/*.md` file this changes or adds, and deletes each one it removes.

**Priority 1 — Process DELETED exports:**
- Remove generated content for deleted exports
- Check if deleted export has attached [MANUAL] blocks
- If [MANUAL] attached: flag as ORPHAN conflict (do not remove)
- If no [MANUAL]: remove generated content cleanly
- **Gap-driven rescopes** (`DELETED_EXPORT` from gap-driven.md §1 rule R1, verification `rescoped`) are processed here with the same removal. merge-write.md §6b writes the entry's `rescope` (its `scope.amendments[]` entry, `action: "excluded"`, and its `scope.exclude` path) to the skill brief before SKILL.md, and step 5 removes the provenance `entries[]` row and recomputes `stats` from the amended `brief.scope` (write.md §3/§3b). gap-spot-check.md §4 HALTs on a rescope that carries no `rescope`, so no unscoped removal reaches here.

**Priority 2 — Process MOVED exports:**
- merge-write.md §6b moves each `MOVED_EXPORT`'s citations (in gap-driven mode, each record marked `moved`) by script: never move a citation by hand. The script moves each `[AST:]` or `[SRC:]` citation of the export's old line to its `new_line`, and, when the change manifest gives it an `old_file` (a move across files), to the file its `per_file` item names, keeping its prefix; a citation another export also claims, or one inside a [MANUAL] block, stays where it is with a `provenance:` warning. A `MODIFIED_EXPORT` with an `old_file` (it also changed) is rewritten whole by Priority 4.
- **Gap-driven:** move citations only for an export whose gap-spot-check.md §4 spot-check recorded `moved`. A `MOVED_EXPORT` that recorded `unknown` (the drift override among the causes), `verified` or `missing` moves none: write.md §3 leaves its line as it is.
- Update provenance map file references
- [MANUAL] blocks unaffected (content unchanged)

**Priority 3 — Process RENAMED exports:**
- Replace old identifier with new identifier in generated content
- Check if [MANUAL] blocks reference old identifier name
- If referenced: flag as STALE_REFERENCE conflict

**Priority 4 — Process MODIFIED exports:**
- Replace generated content for the export with fresh extraction
- **Gap-driven `MODIFIED_EXPORT`:** its fresh extraction is its record in `files` of `{run_dir}/reextract-records.json`, which gap-spot-check.md §4 copied from §4a's extraction at the line its spot-check located (`verified` or `moved`): document it from that record, as a `re-extracted` one is, taking its signature, parameters and return type from the record, never from the old content or the gap's text, so SKILL.md names the signature step 5's `apply` writes to the provenance map. The record holds no docstring (§4 asks none for it), so keep the export's description. With no record there (its verification record's `extraction_method` is null), repair it from the source line its spot-check read.
- **Gap-driven `MODIFIED_EXPORT` recorded `unknown` or `missing`** (gap-spot-check.md §4 located no line for it, and step 5's `apply` warns with the cause, `cited-elsewhere` or `outside-scope` among them): keep its documented content as it stands. Never rewrite it from the gap's text (its title, issue or remediation), which may describe another file's declaration.
- Preserve [MANUAL] blocks adjacent to the export
- Check for position conflicts (new content shifts [MANUAL] block)
- If position conflict: flag as POSITION conflict

**Priority 5 — Process NEW exports:**
- Append new export content to appropriate section
- Place before any [MANUAL] blocks at section boundary
- No conflicts expected (new content, no existing [MANUAL])
- **A `public-api` skill's public surface (normal mode only):** document no new export, and no export of an ADDED or MOVED file, whose record in `{run_dir}/reextract-records.json` is marked `public: false`, unless the provenance map holds the export (by name at its `old_path` for a MOVED file) or the old name it renames, or this update removes an entry of its name (a `DELETED_EXPORT`, a DELETED file's entry): `records` (re-extract.md §4) found it off the public surface, and step 5's `apply` adds no entry for it, so SKILL.md, the provenance map and metadata.json's `exports[]` name the same exports. A record with no `public` mark is documented as before, and an export the map already holds keeps its content (Priority 4) whatever its mark. In gap-driven and degraded mode document every record whatever its mark: `apply` maps them all.
- **Gap-driven cited `NEW_EXPORT` whose spot-check pinned a line** (gap-spot-check.md §4 recorded `verified` or `moved` for an export the provenance map does not hold): cite it as `[SRC:{source_file}:L{line}]`, where `{line}` is the citation's line for `verified` and the `new_location` line for `moved`: the line write.md §3 records in its new `source-read` entry. The spot-check found that line by the verifier's text rules, not by an ast-grep recipe, so the prefix is `SRC`, never `AST`. Document it from its record in `files` of `{run_dir}/reextract-records.json`, as a `re-extracted` one is, when §4 copied one there from §4a's extraction at that line (its verification record's `extraction_method` is set): its signature, parameters and return type come from that record, never from the gap's text, and the record holds no docstring (§4 asks none for it). It keeps its `[SRC:]` citation and its T1-low label whatever its record's tool.
- **Gap-driven `NEW_EXPORT` recorded `unknown` with `cited-elsewhere` or `outside-scope`** (gap-spot-check.md §4: the provenance map already holds its name at another file than the gap cites, or the skill brief's scope leaves out the file the gap names): add nothing for it, and never document it from the gap's text (its title, issue or remediation), which may describe another file's declaration.

**Priority 6: Process script, asset and document changes (Category D of the change manifest):** step 5's `apply` writes every `file_entries[]` row, and write.md §3 copies or removes each script and asset file the change manifest's `category_d` lists, never a document. Merge updates SKILL.md's Section 7b manifest table for those `scripts_*` and `assets_*` paths, and never modifies a file in `scripts/[MANUAL]/` or `assets/[MANUAL]/` (user-authored). Changed documents are already recorded for the reports: report.md lists each `docs_modified` and `docs_deleted` path of `category_d`, and the evidence report names each document reconcile-scope.md §1b promoted, through its `authoritative_files_mirror` record.

**Priority 8: Process STRUCTURAL_FIX entries (gap-driven, from gap-driven.md §1 rule R2):**

For each `STRUCTURAL_FIX` entry gap-spot-check.md §4 forwarded:

- Apply the surgical edit described in the entry's `remediation` text to the **generated output file only** (e.g., escape an unescaped `|` inside a code span, balance a fence, repair a broken intra-skill anchor in SKILL.md or a `references/*.md`).
- **A split-body consistency finding** (rule R2: two files of the skill, the SKILL.md body or a `references/*.md` file, document one export differently): edit the file the entry's `package_citation` names, the side the pinned source contradicts (test-skill coverage-check §5b), so it documents the export as the other file does: of two `references/*.md` files no source settled, that is the one whose path sorts last, matched to the other. Without a `package_citation`, edit the file the remediation names to change; when neither names one, edit the `references/*.md` file to match the SKILL.md body, or of two `references/*.md` files the one whose path sorts last to match the other. Several split-body entries that cite one file and line are one edit of it. Change only what the remediation names as contradicting (a parameter, a type, the return type), taking it from the other file, and nothing more when it says both forms agree with the source. A remediation that asks for citations instead (each form documents a different declaration of the name) names no form to take: add each citation it names at the line it names, in either file, with the module or owner it names, and change no form. Keep each file's level of detail: the body keeps its brief form, and a `|` the change puts inside a table cell is escaped (`\|`). Read no source. When the manifest also holds a `MODIFIED_EXPORT` for the same export, Priority 4's rewrite settles the body: skip this edit of SKILL.md for that export.
- Do **not** add, modify, or remove any provenance `entries[]` row — STRUCTURAL_FIX never touches the provenance map.
- Preserve any [MANUAL] blocks; if the fix location overlaps a [MANUAL] block, flag as a POSITION conflict instead of editing.
- For each entry it edits, append the record `structural_fix: {gap_id, summary, file, line}` (`summary` its remediation in one line, `file` and `line` where the edit landed) to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `structural_fix`. An edit this priority skips for Priority 4's rewrite, or flags as a POSITION conflict, adds none.

**If no STRUCTURAL_FIX entries:** skip Priority 8 silently.

**Priority 8b: Process metadata-update entries (gap-driven, from gap-driven.md §1 rule R4):**

For each `metadata update` entry gap-spot-check.md §4 forwarded:

- Stage the surgical metadata patch the entry's `remediation` describes as one item of `metadata_patches[]`, for write.md §2 to apply **before** write.md §3b's automatic stat recount: its `gap_id`, a one-line `summary` of its remediation, and in `set` each metadata.json field it sets (`a.b` for a nested one) with its value.
- Touch no provenance `entries[]` row and no generated markdown — this priority only stages the patch; write.md §2 applies it.
- Append the record `metadata_patch: {gap_id, summary, set}` of each item to `{run_dir}/evidence-records.jsonl` as one JSON line keyed `metadata_patch`.

Once every entry is staged, write the items to `{run_dir}/metadata-patches.json` in one file write, each value as JSON (a string with `"` and `\` escaped), from `{project-root}`:

```bash
cat > "{run_dir}/metadata-patches.json" <<'SKF_JSON'
{"metadata_patches": [{"gap_id": "<the entry's gap_id>", "summary": "<its remediation in one line>", "set": {"<metadata.json field, a.b for a nested one>": <its value as JSON>}}]}
SKF_JSON
```

**If no metadata-update entries:** skip Priority 8b silently, and write no `metadata-patches.json`.

### 4. Check for Conflicts

Scan all merge operations for flagged conflicts.

**If ZERO conflicts:** report a clean merge.

**GATE [default: K for POSITION, HALT otherwise]**: **if conflicts are detected, headless (`{headless_mode}` true):** the conflicts' types decide what the run does:

- **Any ORPHAN or STALE_REFERENCE conflict:** it requires human judgment, and nothing is written yet. HALT with status `halted-for-manual-mismatch` (halt procedure: `phase: "merge:conflict-resolution"`, `reason: "{N} [MANUAL] conflict(s) need a person: {each conflict_type and section}"`), where `{N}` and the list count the ORPHAN and STALE_REFERENCE conflicts alone. No `headless_decisions[]` entry is added.
- **Otherwise** (every conflict is POSITION): keep each block as [K]eep below does, recording `{"name": "<block>", "action": "keep"}` in `{run_dir}/manual-plan.json` once per block name `{manual_inventory}` holds, and none for a block in a `references/*.md` file, which the inventory does not hold and the merge leaves untouched: `manual-inventory-amend` refuses a name the inventory lacks or one the plan decides twice. The block moves with its section, which merge-write.md §6b's `manual-verify` reports in `moved` without failing. For a POSITION conflict Priority 8 flagged, make no edit and add `structural-fix-skipped: {gap_id}: the edit at {file}:{line} overlaps the [MANUAL] block {block}, kept as it is` to `warnings[]`. Record one decision per block, from `{project-root}`:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-update-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
  {"gate": "merge.manual-conflict", "default_action": "K", "taken_action": "K", "reason": "headless: a POSITION conflict keeps the [MANUAL] block, which moves with its section", "evidence": {"block": "<block>", "section": "<its parent section heading before the merge>"}}
  SKF_JSON
  ```

**If conflicts detected, interactive:** present each conflict to user:

"**[MANUAL] Conflict Resolution Required:**

**Conflict {N} of {total}:** {conflict_type}

{Detailed description of the conflict with before/after context}

**Options:**
- **[K]eep** — Preserve [MANUAL] content as-is, adjust generated content around it
- **[R]emove** — Remove the [MANUAL] block (content will be lost)
- **[E]dit** — Show me both versions, I'll provide the resolution

Select: [K] Keep / [R] Remove / [E] Edit"

Process each conflict with user's decision, and record each one as it is made in the run's plan, `{run_dir}/manual-plan.json` (`{"decisions": [...]}`), one decision per [MANUAL] block by its name:

- **[K]eep:** `{"name": "<block>", "action": "keep"}`.
- **[R]emove**, and an ORPHAN the user removes: `{"name": "<block>", "action": "remove"}`.
- **[E]dit:** write the interior the user approved to `{run_dir}/manual-edit-<block>.md`, byte for byte as it goes between the block's markers, its leading and trailing newlines included, and record `{"name": "<block>", "action": "edit", "content_file": "manual-edit-<block>.md"}`. merge-write.md §6b writes that same file's bytes between the markers. Never type a hash: the helper below hashes the file.

**Amend the [MANUAL] inventory** (every mode, a clean merge included: then the plan holds no decision). Write `{run_dir}/manual-plan.json` (`{"decisions": []}` when there was no conflict), then, from `{project-root}`, resolve `{hashContentHelper}` ← first existing path in `{hashContentProbeOrder}` and run:

```bash
uv run {hashContentHelper} manual-inventory-amend \
    --inventory "{manual_inventory}" \
    --plan "{run_dir}/manual-plan.json" \
    --output "{run_dir}/manual-inventory.json"
```

It writes the step 1 inventory without the blocks the user removed and with each edited block hashed from its approved interior. Rebind `{manual_inventory}` ← `{run_dir}/manual-inventory.json`: merge-write.md §6b's staged check, write.md §1, verify-publish.md §6's `fix` and verify-publish.md §7's re-check verify against it, so they check what the user approved and nothing else. On exit 1 or no JSON (a plan that names a block the inventory does not hold, or an edit with no interior), or no candidate resolves: HALT with status `blocked` (halt procedure: `phase: "merge:manual-plan"`, `path: "{run_dir}/manual-plan.json"`, its stderr as `reason`).

### 6. Compile Merge Results

Build merge result summary:

```
Merge Results:
  exports_updated: [count]
  exports_added: [count]
  exports_removed: [count]
  exports_moved: [count]
  exports_renamed: [count]

  manual_sections_preserved: [count]
  manual_conflicts_resolved: [count]
  manual_orphans_kept: [count]
  manual_orphans_removed: [count]
```

In gap-driven mode, write what step 5's `apply` reads from merge to `{run_dir}/merge-records.json`: for each `NEW_EXPORT` or `MODIFIED_EXPORT` the provenance map does not hold and no `re-extracted` record covers (a cited export whose spot-check pinned a line, and a `Medium`, `Low` or `Info` one recorded `unknown`, but not one whose `unknown_reason` is `outside-scope`, for which `apply` adds no entry), the `export_type`, `params` and `return_type` its merged documentation gives, leaving out each one it does not. Leave out each part a record gives, and leave out an export whose record gives all three: when §4a found an export's record (its verification record in `{run_dir}/reextract-records.json` has an `extraction_method`), `apply` takes its whole signature from that record, a part the record gives as null included, and reads merge's only for an export with no record:

```bash
cat > "{run_dir}/merge-records.json" <<'SKF_JSON'
{"exports": [{"export_name": "<name>", "export_type": "<kind>", "params": ["<name: type>"], "return_type": "<type>"}]}
SKF_JSON
```

This step auto-proceeds: once §6 is done, load, read the full file, then execute `{nextStepFile}`, which writes the merge.
