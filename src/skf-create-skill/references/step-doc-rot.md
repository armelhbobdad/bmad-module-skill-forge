---
nextStepFile: 'validate.md'
scanDocRotHelper: 'scripts/scan-doc-rot.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5c: Doc-Rot

## STEP GOAL:

Scan feeder artifacts for doc-rot correction indicators and annotate the compiled SKILL.md with `## CORRECTION` blocks. Matching is a deterministic substring grep performed by `{scanDocRotHelper}` (`scripts/scan-doc-rot.py`) — no AI judgment is used for detection. The prompt keeps only the genuine judgment the script cannot make: enriching each match's `affected` symbol (§2) and choosing where each `## CORRECTION` block goes (§3).

## Rules

- Auto-proceed step — no user interaction required
- Graceful skip — if no corrections are found in any feeder artifact, proceed without modification
- Only modify the compiled SKILL.md (correction block insertion) and references (if corrections target referenced content)
- Do not modify feeder artifacts (evidence-report.md, provenance-map.json, metadata.json) — this step READS them only
- Do not modify frontmatter — correction blocks are body content only
- Matching is case-insensitive substring grep — no semantic or AI-based assessment

## MANDATORY SEQUENCE

### §1. Locate Feeder Artifacts

Identify the feeder artifacts in the **staging directory** for the current skill. This step (5c) runs **before** step 7 promotes the staging tree to `{forge_data_folder}/{skill-name}/{version}/`, so the feeder artifacts only exist under the staging path compile (step 5 §1a) wrote — reading the not-yet-promoted `{forge_data_folder}` path would make every match a no-op:

1. **Evidence report:** `_bmad-output/{skill-name}/evidence-report.md`
2. **Provenance map:** `_bmad-output/{skill-name}/provenance-map.json` — focus on T2/T3 entries with temporal annotations
3. **Temporal context:** changelogs, migration guides, and issue/PR data fetched by step 3b and enriched by step 4 (available in workflow context)
4. **Compiled SKILL.md:** the staged `_bmad-output/{skill-name}/SKILL.md` itself — check for `[QMD:...]` or `[DOC:...]` annotations referencing corrections. **Do not treat its own `## Migration & Deprecation Warnings` section (§4b) as a correction source:** compile (step 5 §4b) already authored that section from the same T2-future annotations, so its bullets are already-surfaced corrections — §2 discards matches that land inside it.

For each artifact, attempt to load its content. If an artifact does not exist or is empty, skip it — this is not an error.

Store: `feeder_artifacts_scanned: [{list of artifacts that were loaded}]`

### §2. Grep for Correction Indicators

The scan is deterministic plumbing — a fixed-table substring grep with one correct answer per input — so it runs in `{scanDocRotHelper}`, **not** in-prompt. Do not hand-grep the feeder artifacts: identical feeders must yield identical `correction_matches`, and only the script guarantees that across multi-KB inputs. Pass the `## Migration & Deprecation Warnings`-bearing compiled SKILL.md (feeder #4) as `--skill-md` and every other loaded feeder as a positional argument:

```bash
uv run {scanDocRotHelper} \
  --skill-md _bmad-output/{skill-name}/SKILL.md \
  _bmad-output/{skill-name}/evidence-report.md \
  _bmad-output/{skill-name}/provenance-map.json \
  _bmad-output/{skill-name}-temporal/*.md
```

(Pass whichever of the §1 feeder paths actually exist — the script skips any that are missing or empty, and reports the loaded set in `scanned`.)

The script emits `{scanned: [...], matches: [...], match_count, excluded_count}` on stdout. Each entry in `matches` is a match record with the deterministic fields the script owns:

- `source`: the feeder artifact path where the match was found
- `pattern`: the specific pattern string that matched
- `category`: the category label
- `context_line`: the line containing the match
- `line_number`: the 1-indexed line the match sits on

Read `matches` into `correction_matches: [{match records}]`. Then add the one judgment field the script cannot infer:

- `affected`: the function name, API, or section the correction relates to — enrich each record from surrounding context (use the `[QMD:...]`/`[DOC:...]` annotations and nearby symbols); if not identifiable, set to `"unknown"`.

**What the script does (the contract it implements — keep this table and the script's `PATTERN_TABLE` in lockstep):** it matches every feeder line against the following correction patterns. All matches are **case-insensitive substring matches** — no regex interpretation, no semantic analysis.

| Pattern | Category |
|---------|----------|
| `deprecated` | Deprecation |
| `@deprecated` | Deprecation |
| `breaking change` | Breaking change |
| `BREAKING` | Breaking change |
| `removed in` | Removal |
| `was removed` | Removal |
| `renamed to` | Rename |
| `renamed from` | Rename |
| `superseded by` | Supersession |
| `replaced by` | Supersession |
| `no longer supported` | End of life |
| `migration required` | Migration |
| `signature changed` | Signature change |

**Exclusion — drop already-surfaced §4b corrections (deterministic, no AI judgment, applied inside the script before it emits):** the script discards any match whose `source` is the compiled SKILL.md (feeder #4) **and** whose `context_line` sits inside that file's own `## Migration & Deprecation Warnings` section — i.e. on a line at or after the `## Migration & Deprecation Warnings` heading and before the next `##` heading (`excluded_count` reports how many it dropped). Compile (step 5 §4b) authored that section from the same T2-future annotations, so re-emitting its bullets as `## CORRECTION` blocks in §3 would duplicate already-surfaced content verbatim. This is a positional heading-boundary check on text already loaded, not a semantic assessment. Set `feeder_artifacts_scanned` from the script's `scanned` list.

**IF `correction_matches` is empty** (the script returned `match_count: 0`, or the run had no feeder files to pass)**:**
- Log: `"doc-rot: skipped (no correction indicators found in feeder artifacts)"`
- Set context: `doc_rot_triggered: false`, `corrections_added: 0`
- Skip to §5 (Auto-Proceed)

**ELSE:** Proceed to §3.

### §3. Annotate SKILL.md with Correction Blocks

For each entry in `correction_matches`, insert a `## CORRECTION` block into the compiled SKILL.md.

**Block format:**

```markdown
## CORRECTION

**Source:** {source}
**Pattern:** {pattern}
**Affected:** {affected}
**Detail:** {context_line}
```

**Insertion rules:**
- **After the relevant API section** in SKILL.md if the `affected` function or section can be identified and located in the document
- **At the end of SKILL.md body** (before any trailing sections like `## Manual Sections`) if the affected section cannot be determined
- **Never inside frontmatter** — body content only
- Each correction block is self-contained with its own source citation
- Multiple corrections produce multiple `## CORRECTION` blocks

Store: `corrections_added: {count of blocks inserted}`

### §4. Log Results

Log: `"doc-rot: {corrections_added} correction blocks added from {feeder_artifacts_scanned_count} feeder artifacts"`

Set context:
- `doc_rot_triggered: true`
- `corrections_added: {count}`
- `feeder_artifacts_scanned: [{list}]`
- `correction_matches: [{match records}]`

### §5. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
