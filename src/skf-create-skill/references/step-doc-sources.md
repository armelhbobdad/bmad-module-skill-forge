---
nextStepFile: 'step-auto-shard.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5a: Doc Sources

## STEP GOAL:

Record detected documentation pages and README with content hashes in metadata.json so that downstream audit (analyze-skill) can detect when upstream docs have changed since the skill was compiled.

## Rules

- Auto-proceed step — no user interaction required
- Graceful failure — if doc detection fails, skip with a warning and proceed to validate
- Do not modify any compiled artifact other than `metadata.json`
- Do not block the pipeline on any doc detection error

## MANDATORY SEQUENCE

### 1. Check for Upstream Doc Detection Results

Check if `doc_detection_results` is already populated in the workflow context (set by BS auto-brief in the forge-auto pipeline).

- **If upstream results exist:** use them directly, skip to step 3.
- **If no upstream results:** continue to step 2.

### 2. Run Doc Detection (if needed)

Check that `{source_repo}` is available from the skill brief.

**If `{source_repo}` is not available:**
- Set `doc_detection_results` to an empty array `[]`
- Add evidence note: `"Doc sources: detection skipped — no source_repo in brief"`
- Skip to step 3.

**If `{source_repo}` is available:**

Invoke the detect-docs script:

```bash
uv run src/shared/scripts/skf-detect-docs.py \
  --repo-url {source_repo} \
  [--local-path {source_path}] \
  [--skip-pages-api]
```

Pass `--local-path {source_path}` when a local clone exists from the extraction step to avoid redundant cloning for `docs/` folder detection.

**Handle exit codes:**
- **Exit 0** (found ≥1 doc): parse JSON stdout as `doc_detection_results`
- **Exit 1** (none found): set `doc_detection_results` to empty array `[]`
- **Exit 2** (error): set `doc_detection_results` to empty array `[]`, add evidence note: `"Doc sources: detection partial — skf-detect-docs.py error (exit 2)"`

### 3. Ensure README Entry

After obtaining detection results, check if any entry has a URL matching `*/README.md` or `*/readme.md`.

**If a README entry already exists** from detection (e.g., `detected_via: "docs_folder"` found a README): keep it as-is.

**If no README entry exists,** add one:

- `url`: Construct from `{source_repo}/blob/main/README.md`
- `detected_via`: `"readme_always"`
- `content_hash`: Hash the README content using `sha256:{hexdigest}` convention:
  - If `{source_path}` is available: read `{source_path}/README.md` locally with `encoding="utf-8"`, compute `sha256:{hexdigest}`
  - Else: fetch via `gh api repos/{owner}/{repo}/readme --jq '.content'`, base64-decode, hash
  - If README cannot be found or fetched: set `content_hash` to `null`
- `recorded_at`: current ISO-8601 timestamp with timezone

### 4. Build doc_sources Array

Map each detection result to the `doc_sources` schema:

```json
{
  "url": "{url from detection result}",
  "detected_via": "{detected_via from detection result}",
  "content_hash": "{content_hash from detection result — sha256:{hexdigest} or null}",
  "recorded_at": "{current ISO-8601 timestamp with timezone}"
}
```

Field mapping from `skf-detect-docs.py` output:
- `url` ← `url` (direct copy)
- `detected_via` ← `detected_via` (direct copy; or `"readme_always"` for the mandatory README entry)
- `content_hash` ← `content_hash` (direct copy, already in `sha256:{hexdigest}` format from story 1.2)
- `recorded_at` ← generated at step execution time (ISO-8601 with timezone)

Note: `content_type` from detect-docs output is NOT carried into `doc_sources`.

### 5. Update metadata.json

Read the staging `_bmad-output/{skill-name}/metadata.json` that compile (step 5) wrote.

**If the staging metadata.json is unreadable:** HALT — this indicates compile failed (critical, not doc-detection-related).

**Replace** the `doc_sources` field entirely (do not merge or append to stale data from prior compiles):

```python
metadata["doc_sources"] = new_doc_sources  # full replacement
```

Write the updated metadata.json back to the staging directory.

Add evidence note summarizing the result:
- Success: `"Doc sources: {N} detected, README tracked"`
- Skip: `"Doc sources: detection skipped — {reason}"`
- Partial: `"Doc sources: detection partial — {N} found, {errors}"`

### 6. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
