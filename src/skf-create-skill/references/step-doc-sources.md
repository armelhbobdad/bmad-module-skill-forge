---
nextStepFile: 'step-auto-shard.md'
detectDocsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
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
- A HARD HALT, once step 3 §2a has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound: it stages `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "summary": {"halt_reason": "<halt_reason>", "evidence_report": null}}`, plus `"path"` when the HALT names a file or folder, as `{run_dir}/halt.json`, runs `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, displays the line it prints (the halt message alone when no path resolves) and stops with the HALT's exit code. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### 1. Check for Upstream Doc Detection Results

**Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins: §2, §2a and §3 run it. If no candidate exists, **HARD HALT** (exit code 3, `helper-missing`, phase `doc-sources`): "Cannot record the doc sources: skf-detect-docs.py is missing. Re-install SKF, then re-run create-skill."

Check if `doc_detection_results` is already populated in the workflow context (set by BS auto-brief in the forge-auto pipeline).

- **If upstream results exist:** write them, as the JSON array they are, to `{run_dir}/doc-detection.json` and skip to step 3.
- **If no upstream results:** continue to step 2.

### 2. Run Doc Detection (if needed)

**If `source_type` is `"docs-only"`:** skip detection: `source_repo` is the documentation site, not a GitHub repository, so `{detectDocsHelper} --repo-url` would exit 2 with `INVALID_URL` and leave `doc_sources[]` empty. The brief's `doc_urls` are the doc sources; continue to §2a.

Otherwise check that `{source_repo}` is available from the skill brief.

**If `{source_repo}` is not available:**
- Add evidence note: `"Doc sources: detection skipped, no source_repo in brief"`
- Skip to step 3, with no detected entries.

**If `{source_repo}` is available:**

Invoke the detect-docs script, saving what it prints:

```bash
uv run {detectDocsHelper} \
  --repo-url {source_repo} \
  [--skip-pages-api] > "{run_dir}/doc-detection.json"
```

Pass no `--local-path`: step 3 read a remote source from a private tree that step 7 removes, and a `file://` URL into it could never be fetched again at audit time. Without it the helper lists the `docs/` folder through the GitHub API, whose raw file URLs `skf-audit-skill` can fetch again.

**Handle exit codes:**
- **Exit 0** (found ≥1 doc) or **Exit 1** (none found): `{run_dir}/doc-detection.json` holds the detected entries for §3.
- **Exit 2** (error): §3 gets no detected entries; add evidence note: `"Doc sources: detection partial, skf-detect-docs.py error (exit 2)"`

### 2a. Docs-Only: Hash the Brief's Documentation URLs

Runs only when `source_type` is `"docs-only"` (§2 routed here). Build the URL list: every `doc_urls[].url` from the brief, in brief order, followed by every subpage URL that step 3c (fetch-docs) actually fetched through subpage discovery, the `[EXT:{url}]` provenance set of the doc-fetch inventory. Include a brief URL even if step 3c could not fetch it; the helper fetches independently of the agent's web tools.

Pipe the list to the `hash-urls` subcommand, saving what it prints. It fetches each URL and hashes the raw response bytes with the same primitive `skf-audit-skill` step 5a (`compare-hashes`) uses, so a hash recorded here compares byte-for-byte at audit time. Do not hash the markdown a web-fetch tool rendered in step 3c: the audit re-fetches raw bytes, and a rendered-markdown hash would report every page as drifted.

```bash
printf '%s' '["{url-1}", "{url-2}", "..."]' | uv run {detectDocsHelper} hash-urls - > "{run_dir}/doc-detection.json"
```

The input may also be the brief's `doc_urls` block verbatim: an array of `{url, label}` objects, or an object with a `doc_urls` array.

**Handle exit codes:**
- **Exit 0:** `{run_dir}/doc-detection.json` holds the entries for §3 (`detected_via: "brief_doc_urls"`, `content_hash` null for a URL that could not be fetched) and the `stats` its evidence note reads.
- **Exit 2** (malformed input, unreadable file): §3 gets no detected entries; add evidence note: `"Doc sources: detection partial, skf-detect-docs.py hash-urls error (exit 2)"`

A docs-only brief has no repository README to track. Continue at §3.

### 3. Record the Doc Sources

One `record-sources` call writes `doc_sources` into the staging `_bmad-output/.skf-stage/{skill-name}/metadata.json` that compile (step 5) wrote, replacing what an earlier compile left there. It keeps each detected entry's `url`, `detected_via` and `content_hash`, stamps its `recorded_at`, and leaves every other field of the file as it was. From `{project-root}`, run:

```bash
uv run {detectDocsHelper} record-sources "_bmad-output/.skf-stage/{skill-name}/metadata.json" [--detected "{run_dir}/doc-detection.json"] [--source-repo "{source_repo}" --ref "{source_ref}" [--local-root "{source_root}"]]
```

Pass `--detected` when §1 wrote `{run_dir}/doc-detection.json`, §2's call exited 0 or 1, or §2a's exited 0. Pass `--source-repo` and `--ref` only for a source brief with a `{source_repo}` (never docs-only, whose `source_repo` is the documentation site): the helper then keeps a detected README, or adds the README entry `readme-entry` builds, the raw GitHub file at the ref step 3 resolved (a `file://` URL for a local source), hashed as `skf-audit-skill`'s `compare-hashes` hashes it again. Add `--local-root` when `{source_root}` is a local folder: the local source, or the private tree step 3 read a remote source into. Without it the helper lists the top of a GitHub repository through the GitHub API.

- **Exit 0:** add the evidence note its JSON gives:
  - Source brief: `"Doc sources: {count} recorded, README tracked"` when `readme_tracked` is true, else `"Doc sources: {count} recorded, README not tracked"`, ending `", {source_repo} is not a GitHub repository"` when `skip_reason` is `not-github`.
  - Docs-only, when §2a's call exited 0: `"Doc sources: {stats.hashed}/{stats.total} brief doc URL(s) hashed, {stats.fetch_failed} fetch failed"`, from the `stats` in `{run_dir}/doc-detection.json`.
- **Exit 2 with `code` `METADATA_UNREADABLE`:** **HARD HALT** (exit code 4, `staging-unreadable`, phase `doc-sources`), with `"path"` the staged `metadata.json`: "Cannot read the staged metadata.json that compile wrote. Re-run create-skill." It means compile failed, which no doc detection caused.
- **Any other exit 2:** add evidence note `"Doc sources: not recorded, skf-detect-docs.py record-sources error: {message}"`, with `{message}` its stderr JSON's `error`, and go on.

### 4. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
