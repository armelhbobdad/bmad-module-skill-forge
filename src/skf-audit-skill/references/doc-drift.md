---
nextStepFile: 'report.md'
# A docs-only skill (step 1 §3) goes on to step 5 instead, which grades each
# changed document: this comparison is the only drift such a skill has.
classifyStepFile: 'severity-classify.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder: §2 saves the comparison here.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
# §2's comparison helper: the installed SKF module path first, then the src/
# dev-checkout path.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5a: Documentation Drift

## STEP GOAL:

Compare the content hash each tracked document had at compile time (`doc_sources` in metadata.json) with its current upstream state, and report which documents changed, which could not be reached and which were never hashed. For a skill built from source this is informational: doc drift does not move the drift score. A docs-only skill has no other drift, so for it step 5 grades each changed document.

## Rules

- Auto-proceed, no user interaction, and do not classify severity here. Graceful failure: a URL that cannot be fetched is `fetch_failed`, never a halt by itself (a docs-only skill halts only when it could compare no document at all, §2). For a skill built from source, never abort the audit on a failure here: skip the check with a note
- `{docs_only_skill}` is the `docs_only_skill` value step 1 §6 wrote into {outputFile}'s frontmatter: read it there, not from memory, so a compacted session still takes the docs-only route

## MANDATORY SEQUENCE

**Halt envelope.** Only a docs-only skill halts here (§2), and step 1 read no private source tree for it. In headless mode, stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{outputFile}"}`, adding `"path"` when the halt names one, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-audit-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Check for doc_sources

Check the skill metadata loaded at init (step 1 §3, Load Skill Artifacts) for a `doc_sources` array. A docs-only skill always has one with a recorded `content_hash`: step 1 §3 stops a docs-only skill without it.

**If `doc_sources` is absent:** append the section below to {outputFile}, set `doc_drift_summary = { skipped_entirely: true }`, append `'doc-drift'` to `stepsCompleted` in its frontmatter and auto-proceed to {nextStepFile}:

```markdown
## Documentation Drift

No doc_sources recorded: skip doc drift check. This skill was compiled before doc tracking was available. Recompile with the current CS pipeline to enable doc drift detection.
```

**If `doc_sources` is an empty array:** do the same with `doc_drift_summary = { total_tracked: 0, skipped_entirely: false }` and this section:

```markdown
## Documentation Drift

No documentation sources tracked. The `doc_sources` array is empty: no drift check to perform.
```

**Otherwise** continue to §2.

### 2. Fetch and Hash Each Tracked Doc

Run the script rather than fetching yourself: the stored hashes are `sha256:{hexdigest}` of each document's raw response bytes, which the model cannot compute. Resolve `{compareDocHashesHelper}` ← first existing path in `{compareDocHashesProbeOrder}` (SKILL.md On Activation checked that one exists) and, from `{project-root}`, save the comparison in the stage data folder:

```bash
mkdir -p "{auditDataFolder}"
uv run {compareDocHashesHelper} compare-hashes "{resolved_skill_package}/metadata.json" > "{auditDataFolder}/doc-drift.json"
```

It fetches each URL whose `content_hash` is set and compares the hashes. A `null` `content_hash` is not fetched (`skipped_null_hash`: there is no baseline), and a network error, a timeout or a non-200 status is `fetch_failed`, which is not drift. The saved JSON:

```json
{
  "changed":           [{"url": "...", "old_hash": "sha256:...", "new_hash": "sha256:..."}],
  "unchanged":         [{"url": "..."}],
  "fetch_failed":      [{"url": "...", "old_hash": "sha256:...", "reason": "..."}],
  "skipped_null_hash": [{"url": "..."}],
  "stats": {"total_tracked": N, "changed": N, "unchanged": N, "fetch_failed": N, "skipped_null_hash": N}
}
```

**If the command exits non-zero** (exit 2 is a `doc_sources` it cannot read) or saves no JSON:

- **A skill built from source:** delete the file, append the section below to {outputFile}, set `doc_drift_summary = { skipped_entirely: true }`, append `'doc-drift'` to `stepsCompleted` and auto-proceed to {nextStepFile}:

  ```markdown
  ## Documentation Drift

  Doc drift check skipped: the comparison failed ({the first stderr line}).
  ```

- **A docs-only skill** (`{docs_only_skill}`): this comparison is its whole audit, so HALT with **exit 3**, phase `doc-drift:compare`, showing the first stderr line: on exit 2, `halt_reason: "provenance-invalid"` with `"path": "{resolved_skill_package}/metadata.json"` (its `doc_sources` is the record the audit compares against); otherwise `halt_reason: "helper-missing"`.

**Once the comparison is saved, a docs-only skill** (`{docs_only_skill}`) is graded only on the documents it compared:

- **`stats.changed` + `stats.unchanged` is 0:** no document was compared (each one failed to fetch or has no recorded hash), and a CLEAN score would vouch for documents nobody read. HALT with **exit 3**, `halt_reason: "source-unreadable"`, phase `doc-drift:compare`, `"path": "{resolved_skill_package}/metadata.json"`: "**No documentation source of `{skill_name}` could be compared.** {each `fetch_failed` URL with its `reason`, then each `skipped_null_hash` URL with `no hash recorded`}. Re-run once the documents can be reached, or re-create the skill with `[CS] Create Skill` to record their hashes."
- **Otherwise,** record each of `stats.fetch_failed` and `stats.skipped_null_hash` that is not 0 as a warning, so the envelope shows the score leaves those documents out: `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "doc_fetch_failed: {fetch_failed}"` and `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "doc_not_hashed: {skipped_null_hash}"`.

### 3. Build Drift Findings

Take the four buckets (`changed[]`, `unchanged[]`, `fetch_failed[]`, `skipped_null_hash[]`) and every count from the saved JSON's `stats`: never recount.

### 4. Append to Drift Report

Append the `## Documentation Drift` section to {outputFile}.

**When drift detected:**

```markdown
## Documentation Drift

| URL | Old Hash | New Hash | Detected At |
|-----|----------|----------|-------------|
| {url} | `{old_hash}` | `{new_hash}` | {ISO-8601 timestamp} |

**{changed} of {total_tracked} tracked documentation source(s) have changed since compile.**
```

Rows, in this order: each `changed` entry with its old and new hash; each `fetch_failed` entry, with `_(fetch failed: {reason})_` as its New Hash; each `skipped_null_hash` entry, with `_(not recorded)_` as its Old Hash and `n/a` in the last two columns. An unchanged entry gets no row, and only the `changed` rows count as drift.

**When no drift detected:**

```markdown
## Documentation Drift

No documentation drift detected. All {total_tracked} tracked documentation source(s) match their compile-time hashes.
```

If some entries were `fetch_failed` or `skipped_null_hash`, append a note after the main message listing those entries.

### 5. Store Context and Auto-Proceed

Set `doc_drift_summary` to the saved JSON's `stats` (`total_tracked`, `changed`, `unchanged`, `fetch_failed`, `skipped_null_hash`) plus `skipped_entirely: false`: report.md reads it. Append `'doc-drift'` to `stepsCompleted` in {outputFile}'s frontmatter.

Display: "**Documentation drift check complete. {changed} of {total_tracked} source(s) drifted.**"

Load, read the full file, then execute {nextStepFile}, or `{classifyStepFile}` for a docs-only skill (`{docs_only_skill}`), whose changed documents step 5 grades.

## CRITICAL STEP COMPLETION NOTE

Only after the `## Documentation Drift` section is appended and `doc_drift_summary` is set, load and read fully the next step file.
