---
nextStepFile: 'step-auto-shard.md'
# Resolve `{detectDocsHelper}` by probing `{detectDocsProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT (exit code 3, helper-missing) if neither resolves: §2
# has no prose fallback for doc-source detection (Pages-API walk, docs/
# folder scan, content hashing), §2a none for URL hashing and §3 none for
# the README entry.
detectDocsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
# HARD HALT helpers (Rules).
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
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
- A HARD HALT, once step 3 §2b has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

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

**Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins. If no candidate exists, **HARD HALT** (exit code 3, `helper-missing`, phase `doc-sources`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot record the doc sources: skf-detect-docs.py is missing. Re-install SKF, then re-run create-skill."

Invoke the detect-docs script:

```bash
uv run {detectDocsHelper} \
  --repo-url {source_repo} \
  [--skip-pages-api]
```

Pass no `--local-path`: step 3 read a remote source from a private tree that step 7 removes, and a `file://` URL into it could never be fetched again at audit time. Without it the helper lists the `docs/` folder through the GitHub API, whose raw file URLs `skf-audit-skill` can fetch again.

**Handle exit codes:**
- **Exit 0** (found ≥1 doc): parse JSON stdout as `doc_detection_results`
- **Exit 1** (none found): set `doc_detection_results` to empty array `[]`
- **Exit 2** (error): set `doc_detection_results` to empty array `[]`, add evidence note: `"Doc sources: detection partial — skf-detect-docs.py error (exit 2)"`

### 2a. Docs-Only: Hash the Brief's Documentation URLs

Runs only when `source_type` is `"docs-only"` (§2 routed here). Build the URL list: every `doc_urls[].url` from the brief, in brief order, followed by every subpage URL that step 3c (fetch-docs) actually fetched through subpage discovery — the `[EXT:{url}]` provenance set of the doc-fetch inventory. Include a brief URL even if step 3c could not fetch it; the helper fetches independently of the agent's web tools.

**Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins. If no candidate exists, **HARD HALT** (exit code 3, `helper-missing`, phase `doc-sources`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot record the doc sources: skf-detect-docs.py is missing. Re-install SKF, then re-run create-skill."

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

**If `source_type` is `"docs-only"`:** skip this section: `source_repo` is the documentation site, not a repository, so there is no README to track, and any README URL built from it would be fabricated. Continue at §4.

After obtaining detection results, check if any entry has a URL matching `*/README.md` or `*/readme.md`.

**If a README entry already exists** from detection (e.g., `detected_via: "docs_folder"` found a README): keep it as-is.

**If no README entry exists,** add the one the `readme-entry` subcommand builds. It picks the README at the top of the source (`README.md` before a translation such as `README-ja.md`), records the raw GitHub file at the ref step 3 resolved (a `file://` URL for a local source), and hashes it with the fetch `skf-audit-skill`'s `compare-hashes` runs again, so an unchanged README reads as unchanged at audit time. **Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins. If no candidate exists, **HARD HALT** (exit code 3, `helper-missing`, phase `doc-sources`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot record the doc sources: skf-detect-docs.py is missing. Re-install SKF, then re-run create-skill." From `{project-root}`, run:

```bash
uv run {detectDocsHelper} readme-entry --source-repo "{source_repo}" --ref "{source_ref}" [--local-root "{source_root}"]
```

Pass `--local-root` when `{source_root}` is a local folder: the local source, or the private tree step 3 read a remote source into. Without it the helper lists the top of a GitHub repository through the GitHub API.

- **Exit 0:** add each entry of its `doc_sources`, at most one, as the helper wrote it (`url`, `detected_via: "readme_always"`, `content_hash`, `recorded_at`). `content_hash` is `null` when the README could not be fetched, and the audit then skips the entry instead of reporting drift. When `skip_reason` is `not-github`, `doc_sources` is empty: add evidence note `"Doc sources: README not tracked, {source_repo} is not a GitHub repository"`.
- **Exit 2:** add no README entry, and add evidence note `"Doc sources: README not tracked, skf-detect-docs.py readme-entry error (exit 2)"`.

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
- `detected_via` ← `detected_via` (direct copy; `"readme_always"` for the README entry §3 adds)
- `content_hash` ← `content_hash` (direct copy, already in `sha256:{hexdigest}` format)
- `recorded_at` ← generated at step execution time (ISO-8601 with timezone)

Note: `content_type` from detect-docs output is not carried into `doc_sources`.

For a docs-only skill the `hash-urls` output from §2a is already in this shape (`detected_via: "brief_doc_urls"`, `recorded_at` stamped by the helper) — copy its `doc_sources` entries verbatim.

### 5. Update metadata.json

Read the staging `_bmad-output/.skf-stage/{skill-name}/metadata.json` that compile (step 5) wrote.

**If the staging metadata.json is unreadable:** **HARD HALT** (exit code 4, `staging-unreadable`, phase `doc-sources`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with `"path"` the staged `metadata.json`: "Cannot read the staged metadata.json that compile wrote. Re-run create-skill." It means compile failed, which no doc detection caused.

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
