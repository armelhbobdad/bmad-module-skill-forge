---
nextStepFile: 'report.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# Resolve `{compareDocHashesHelper}` by probing `{compareDocHashesProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. When neither resolves (uv/python absent), §2 falls back to
# skipping the doc-drift check with a notice — see the graceful-failure rule.
compareDocHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
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

Fetching each URL, hashing the response bytes, comparing against the stored `content_hash`, and categorizing the outcome is deterministic work — and the model cannot compute a `sha256:{hexdigest}` of fetched bytes natively (it must shell out). Delegate the whole fetch/hash/compare pass to the shared script, which hashes byte-symmetrically with how `doc_sources` hashes were written at compile time and fetches independently of whether a WebFetch tool is wired.

**Resolve `{compareDocHashesHelper}`** from `{compareDocHashesProbeOrder}`; first existing path wins.

Run one deterministic comparison subprocess over the skill's `doc_sources`. The script reads the `doc_sources` array straight out of the skill's `metadata.json` (or accepts a bare `doc_sources` array, or `-` for stdin):

```bash
uv run {compareDocHashesHelper} compare-hashes {skill_path}/metadata.json
```

For each entry, the script:
- **`content_hash` is `null`** → records it under `skipped_null_hash` and does **not** fetch the URL (there is no baseline to compare against).
- **`content_hash` is non-null** → HTTP GETs the URL (15s timeout, same User-Agent as the compile side), computes `sha256:{hexdigest}` of the response body bytes, and compares against the stored `content_hash` (prefix-normalized so a bare-hex writer form still matches).
  - Hashes match → `unchanged`.
  - Hashes differ → `changed`, carrying `old_hash` and `new_hash`.
  - Network error, timeout, or non-200 status → `fetch_failed`, carrying the failure `reason`. Not reported as drift.

Parse the emitted JSON:

```json
{
  "changed":           [{"url": "...", "old_hash": "sha256:...", "new_hash": "sha256:..."}],
  "unchanged":         [{"url": "..."}],
  "fetch_failed":      [{"url": "...", "old_hash": "sha256:...", "reason": "..."}],
  "skipped_null_hash": [{"url": "..."}],
  "stats": {"total_tracked": N, "changed": N, "unchanged": N, "fetch_failed": N, "skipped_null_hash": N}
}
```

The script exits 0 on any well-formed input (even when everything drifted) and exits 2 only on malformed args/JSON — it never blocks this informational audit.

If `uv`/`python` is unavailable or the script cannot be resolved — i.e. URL fetching is unavailable in the current environment — skip the doc drift check entirely with:

```markdown
## Documentation Drift

Doc drift check skipped — URL fetching unavailable in current environment.
```

Set `doc_drift_summary = { skipped_entirely: true }` and auto-proceed.

### 3. Build Drift Findings

Read the categories and totals directly from the script's JSON — no manual counting. The four buckets are already computed:
- **changed:** entries where the stored `content_hash` differs from the newly computed hash (`changed[]`)
- **unchanged:** entries where the hashes match (`unchanged[]`)
- **fetch_failed:** entries where the URL could not be reached (`fetch_failed[]`)
- **skipped_null_hash:** entries where `content_hash` was `null` (`skipped_null_hash[]`)

Take the totals straight from `stats` (do not recount):
- `total_tracked` = `stats.total_tracked`
- `changed` = `stats.changed`
- `unchanged` = `stats.unchanged`
- `fetch_failed` = `stats.fetch_failed`
- `skipped_null_hash` = `stats.skipped_null_hash`

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

Only when the ## Documentation Drift section has been appended to {outputFile} and workflow context updated do you then load and read fully `{nextStepFile}` to begin final report generation.
