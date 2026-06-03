---
nextStepFile: 'validate.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5c: Doc-Rot

## STEP GOAL:

Scan feeder artifacts for doc-rot correction indicators and annotate the compiled SKILL.md with `## CORRECTION` blocks. Matching is grep-based and deterministic — no AI judgment is used for detection.

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
4. **Compiled SKILL.md:** the staged `_bmad-output/{skill-name}/SKILL.md` itself — check for `[QMD:...]` or `[DOC:...]` annotations referencing corrections

For each artifact, attempt to load its content. If an artifact does not exist or is empty, skip it — this is not an error.

Store: `feeder_artifacts_scanned: [{list of artifacts that were loaded}]`

### §2. Grep for Correction Indicators

Scan each loaded feeder artifact for the following correction patterns. All matches are **case-insensitive substring matches** — no regex interpretation, no semantic analysis.

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

For each match, record:
- `source`: the feeder artifact path or citation where the match was found
- `pattern`: the specific pattern string that matched
- `category`: the category from the table above
- `context_line`: the line or excerpt containing the match
- `affected`: the function name, API, or section the correction relates to (extract from surrounding context if identifiable; otherwise set to `"unknown"`)

Store all matches as `correction_matches: [{match records}]`

**IF `correction_matches` is empty:**
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
