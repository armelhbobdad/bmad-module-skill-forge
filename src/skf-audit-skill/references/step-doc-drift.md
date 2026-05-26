---
nextStepFile: 'report.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5a: Documentation Drift

## STEP GOAL:

Compare documentation content hashes stored at compile time (in `doc_sources` within metadata.json) against the current upstream state. Produce a drift section that reports which tracked docs have changed, which are unreachable, and which were never hashed. This step is informational — doc drift does not affect the source code drift score.

## Rules

- Auto-proceed step — no user interaction
- Graceful failure — if doc fetching fails for any URL, mark as `fetch_failed`, do not block the audit
- Do not classify severity — doc drift is informational alongside source drift
- If no `doc_sources` in metadata, skip with notice and auto-proceed
- Never abort the audit pipeline on any failure in this step

## MANDATORY SEQUENCE

### 1. Check for doc_sources

Check the skill metadata loaded at init (step 1 §3 — Load Skill Artifacts) for a `doc_sources` array.

**If `doc_sources` is absent or metadata lacks the field:**

Append to {outputFile}:

```markdown
## Documentation Drift

No doc_sources recorded — skip doc drift check. This skill was compiled before doc tracking was available. Recompile with the current CS pipeline to enable doc drift detection.
```

Set `doc_drift_summary = { skipped_entirely: true }` in workflow context. Update {outputFile} frontmatter: append `'doc-drift'` to `stepsCompleted`. Auto-proceed to {nextStepFile}.

**If `doc_sources` is present but an empty array:**

Append to {outputFile}:

```markdown
## Documentation Drift

No documentation sources tracked. The `doc_sources` array is empty — no drift check to perform.
```

Set `doc_drift_summary = { total_tracked: 0, skipped_entirely: false }` in workflow context. Update {outputFile} frontmatter: append `'doc-drift'` to `stepsCompleted`. Auto-proceed to {nextStepFile}.

**If `doc_sources` is present and non-empty:** Continue to §2.

### 2. Fetch and Hash Each Tracked Doc

For each entry in `doc_sources`:

1. Read `url` and `content_hash` from the entry
2. **If `content_hash` is `null`:** Skip this entry — there is no baseline to compare against. Record it for the report as a null-hash entry. Do not attempt to fetch the URL.
3. **If `content_hash` is non-null:** Attempt HTTP GET of the URL with a reasonable timeout (10s)
   - **On success:** Compute `sha256:{hexdigest}` of the response body bytes (UTF-8 encoding). Compare against the stored `content_hash`. If they differ, record as drifted. If they match, record as unchanged.
   - **On failure (network error, timeout, non-200 status):** Record the entry as `status: "fetch_failed"` with the failure reason. Do not report as drift.

If URL fetching is unavailable in the current environment, skip doc drift check entirely with:

```markdown
## Documentation Drift

Doc drift check skipped — URL fetching unavailable in current environment.
```

Set `doc_drift_summary = { skipped_entirely: true }` and auto-proceed.

### 3. Build Drift Findings

Categorize results:
- **changed:** entries where `content_hash` differs from newly computed hash
- **unchanged:** entries where hashes match
- **fetch_failed:** entries where the URL could not be reached
- **skipped_null_hash:** entries where `content_hash` was `null`

Compute totals:
- `total_tracked` = length of `doc_sources`
- `changed` = count of drifted entries
- `unchanged` = count of matching entries
- `fetch_failed` = count of fetch failures
- `skipped_null_hash` = count of null-hash entries

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

Include rows for ALL entries, in order:
- Drifted entries: show old and new hash
- Unchanged entries: omit from table (only drifted entries appear)
- Fetch-failed entries: `| {url} | \`{old_hash}\` | _(fetch failed: {reason})_ | {timestamp} |`
- Null-hash entries: `| {url} | _(not recorded)_ | — | — |`

Fetch-failed entries are clearly marked and excluded from the drift count.

**When no drift detected:**

```markdown
## Documentation Drift

No documentation drift detected. All {total_tracked} tracked documentation source(s) match their compile-time hashes.
```

If some entries were fetch_failed or skipped_null_hash, append a note after the main message listing those entries.

### 5. Store Context and Auto-Proceed

Store `doc_drift_summary` in workflow context for report.md to reference:

```
doc_drift_summary = {
  total_tracked: N,
  changed: N,
  unchanged: N,
  fetch_failed: N,
  skipped_null_hash: N,
  skipped_entirely: false
}
```

Update {outputFile} frontmatter:
- Append `'doc-drift'` to `stepsCompleted`

Display: "**Documentation drift check complete. {changed} of {total_tracked} source(s) drifted. Proceeding to report generation...**"

Load, read the full file, then execute {nextStepFile}.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ## Documentation Drift section has been appended to {outputFile} and workflow context updated will you then load and read fully `{nextStepFile}` to begin final report generation.
