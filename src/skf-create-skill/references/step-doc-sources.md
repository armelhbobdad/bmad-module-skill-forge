---
nextStepFile: 'step-auto-shard.md'
# Resolve `{detectDocsHelper}` by probing `{detectDocsProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — §2 has no prose fallback for doc-source
# detection (Pages-API walk, docs/ folder scan, content hashing), and §2a none
# for docs-only URL hashing.
detectDocsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5a: Doc Sources

## STEP GOAL:

Record detected documentation pages and README — or, for a docs-only skill, the brief's documentation URLs — with content hashes in metadata.json so that downstream audit (analyze-skill) can detect when upstream docs have changed since the skill was compiled.

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

**If `source_type` is `"docs-only"`:** skip detection — `source_repo` is the documentation site, not a GitHub repository, so `{detectDocsHelper} --repo-url` would exit 2 with `INVALID_URL` and leave `doc_sources[]` empty. The brief's `doc_urls` are the doc sources; continue to §2a.

Otherwise check that `{source_repo}` is available from the skill brief.

**If `{source_repo}` is not available:**
- Set `doc_detection_results` to an empty array `[]`
- Add evidence note: `"Doc sources: detection skipped — no source_repo in brief"`
- Skip to step 3.

**If `{source_repo}` is available:**

**Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins. HALT if no candidate exists.

Invoke the detect-docs script:

```bash
uv run {detectDocsHelper} \
  --repo-url {source_repo} \
  [--local-path {source_path}] \
  [--skip-pages-api]
```

Pass `--local-path {source_path}` when a local clone exists from the extraction step to avoid redundant cloning for `docs/` folder detection.

**Handle exit codes:**
- **Exit 0** (found ≥1 doc): parse JSON stdout as `doc_detection_results`
- **Exit 1** (none found): set `doc_detection_results` to empty array `[]`
- **Exit 2** (error): set `doc_detection_results` to empty array `[]`, add evidence note: `"Doc sources: detection partial — skf-detect-docs.py error (exit 2)"`

### 2a. Docs-Only: Hash the Brief's Documentation URLs

Runs only when `source_type` is `"docs-only"` (§2 routed here). Build the URL list: every `doc_urls[].url` from the brief, in brief order, followed by every subpage URL that step 3c (fetch-docs) actually fetched through subpage discovery — the `[EXT:{url}]` provenance set of the doc-fetch inventory. Include a brief URL even if step 3c could not fetch it; the helper fetches independently of the agent's web tools.

**Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins. HALT if no candidate exists.

Pipe the list to the `hash-urls` subcommand. It fetches each URL and hashes the raw response bytes with the same primitive `skf-audit-skill` step 5a (`compare-hashes`) uses, so a hash recorded here compares byte-for-byte at audit time. Do not hash the markdown a web-fetch tool rendered in step 3c — the audit re-fetches raw bytes, and a rendered-markdown hash would report every page as drifted.

```bash
printf '%s' '["{url-1}", "{url-2}", "..."]' | uv run {detectDocsHelper} hash-urls -
```

The input may also be the brief's `doc_urls` block verbatim — an array of `{url, label}` objects, or an object with a `doc_urls` array.

**Handle exit codes:**
- **Exit 0:** parse the JSON object. Set `doc_detection_results` ← its `doc_sources` array — entries are already in the §4 schema (`url`, `detected_via: "brief_doc_urls"`, `content_hash` — `null` for a URL that could not be fetched — and `recorded_at`). Keep `fetch_failed[]` and `stats` for the §5 evidence note.
- **Exit 2** (malformed input, unreadable file): set `doc_detection_results` to empty array `[]`, add evidence note: `"Doc sources: detection partial — skf-detect-docs.py hash-urls error (exit 2)"`

Skip §3 — a docs-only brief has no repository README to track. Continue at §4.

### 3. Ensure README Entry

**If `source_type` is `"docs-only"`:** skip this section — `source_repo` is the documentation site, not a repository, so there is no README to track and `{source_repo}/blob/main/README.md` would be a fabricated URL. Continue at §4.

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
- `content_hash` ← `content_hash` (direct copy, already in `sha256:{hexdigest}` format)
- `recorded_at` ← generated at step execution time (ISO-8601 with timezone)

Note: `content_type` from detect-docs output is not carried into `doc_sources`.

For a docs-only skill the `hash-urls` output from §2a is already in this shape (`detected_via: "brief_doc_urls"`, `recorded_at` stamped by the helper) — copy its `doc_sources` entries verbatim.

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
- Docs-only: `"Doc sources: {stats.hashed}/{stats.total} brief doc URL(s) hashed, {stats.fetch_failed} fetch failed"`

### 6. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
