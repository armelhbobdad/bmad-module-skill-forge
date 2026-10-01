---
nextStepFile: 'step-auto-validate.md'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
mergeDocUrlsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-merge-doc-urls.py'
  - '{project-root}/src/shared/scripts/skf-merge-doc-urls.py'
detectDocsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1a: Auto-Brief Generation

## STEP GOAL:

To enrich an upstream skill brief (produced by AN auto-scope) with documentation URLs discovered via `skf-detect-docs.py`, validate the enriched brief, and write it through the canonical writer. Envelope emission is deferred to step-auto-validate.md, which presents the brief for user approval before continuing. This step replaces the interactive gather-intent → analyze-target → scope-definition → confirm-brief → write-brief chain when `[auto]` mode is active.

## Rules

- Auto-proceed step — no user interaction required
- This step is conditional — only loaded when `[auto]` flag is present in the pipeline context
- Must produce the same output artifact as the interactive chain: a validated `skill-brief.yaml`
- Doc detection is best-effort — failures do not halt the pipeline
- Do NOT re-derive scope fields from the upstream brief — AN already set them correctly
- Do NOT render YAML or JSON envelopes in the LLM — delegate to deterministic scripts

## MANDATORY SEQUENCE

### 1. Load Upstream Brief

Read the upstream brief path from `{brief_path}` (passed by the forger from AN's `SKF_ANALYZE_RESULT_JSON` `brief_paths[]`).

**IF `{brief_path}` is not set or the file does not exist:** emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-missing"` (SKILL.md Halt Contract), then HARD HALT (exit code 2): "**Auto-brief requires an upstream brief: `brief_path` is missing or the file does not exist at `{brief_path}`.**"

**Resolve `{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins. HALT if no candidate exists.

Validate the upstream brief against the schema:

```bash
uv run {validateBriefSchemaHelper} {brief_path}
```

The script returns JSON `{valid, errors[], warnings[], halt_reason, brief}`.

- **`valid: false`**: the upstream brief is malformed. Emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-invalid"` (SKILL.md Halt Contract), then HARD HALT (exit code 2): "**Upstream brief at `{brief_path}` is invalid: {first error message}.**"
- **`valid: true`**: proceed with the parsed `brief` payload. Log any non-empty `warnings[]` and add each to `workflow_warnings[]` as `<field>: <message>`.

Nothing the upstream brief carries is rebuilt or dropped: §4's writer starts from the upstream brief file itself. That covers the top-level fields (`name`, `version`, `source_type`, `source_repo`, `language`, `description`, `forge_tier`, `created`, `created_by`, `source_authority`, `doc_urls`, `target_version`, `target_ref`, `source_ref`, `scripts_intent`, `assets_intent`) and all scope fields: `scope.type`, `scope.include`, `scope.exclude`, `scope.notes`, `scope.rationale`, `scope.amendments`, `scope.tier_a_include`, `scope.registry_path`, `scope.ui_variants`, `scope.demo_patterns`. The sections below read `skill_name` ← `brief.name`, `source_repo` ← `brief.source_repo`, `scope_type` ← `brief.scope.type` and `source_type` ← `brief.source_type`.

**Docs-only check:** If `source_type` is `docs-only` in the parsed brief, skip §2 (Run Doc Detection) and §3 (Enrich Brief with Detected Docs): the doc URL is already in the brief's `doc_urls`. Log: "Docs-only brief: skipping repo-based doc detection. Doc URLs provided by upstream." Proceed directly to §4 (Write Enriched Brief). All brief fields (`source_type`, `source_authority`, `doc_urls`, `scope_type`) must pass through unmodified.

### 2. Run Doc Detection

**Resolve `{detectDocsHelper}`** from `{detectDocsProbeOrder}`; first existing path wins. HALT if no candidate exists.

Invoke doc detection to discover documentation URLs for the source repo:

```bash
uv run {detectDocsHelper} --repo-url {source_repo}
```

`--repo-url` is always required (the script uses it for GitHub API calls). If a local clone is also available at `{local_clone_path}`, add `--local-path {local_clone_path}` to enable docs-folder scanning in addition to API-based detection.

**Handle exit codes:**

- **Exit 0 (found docs):** Parse the JSON output array. Each entry has `{url, detected_via, content_hash, content_type}`. Proceed to §3 with the detected docs.
- **Exit 1 (none found):** Log: "No external documentation found — brief generated from source analysis only." Proceed to §4 with no doc enrichment.
- **Exit 2 (error):** Log the warning "Doc detection failed: proceeding without doc enrichment." and add it to `workflow_warnings[]`. Do NOT halt: doc enrichment is best-effort. Proceed to §4 with no doc enrichment.

### 3. Enrich Brief with Detected Docs

For each detected doc entry, create a brief `doc_urls` entry:

- `url` ← `url` (direct copy)
- `label` ← derive from `content_type` if available:
  - `"api-docs"` → `"API Documentation"`
  - `"guide"` → `"Guide"`
  - `"reference"` → `"Reference"`
  - Otherwise derive from `detected_via`:
    - `"homepageUrl"` → `"Homepage"`
    - `"readme_link"` → `"README Link"`
    - `"pages_api"` → `"GitHub Pages"`
    - `"docs_folder"` → `"Docs Folder"`
- `source` ← coarse provenance derived from `detected_via` (per the `skill-brief.v1.json` `doc_urls[].source` enum): `homepageUrl` → `homepage`, `readme_link` → `readme-detection`, `pages_api` → `pages-api`, `docs_folder` → `docs-folder`. This marks the entry as opportunistically detected, distinct from a registry-guaranteed corpus.

**Merge via the canonical helper.** Resolve `{mergeDocUrlsHelper}` from `{mergeDocUrlsProbeOrder}` (first existing path wins; HALT if neither exists). Stage its input in the run folder, the upstream brief's `doc_urls` as `existing` and the entries just mapped above as `detected`, then run it on the file:

```bash
cat > "{run_dir}/doc-urls.json" <<'SKF_JSON'
{"scope_type": "<scope_type>", "existing": <the upstream brief's doc_urls, [] if none>, "detected": <the mapped detected entries>}
SKF_JSON
uv run {mergeDocUrlsHelper} < "{run_dir}/doc-urls.json" > "{run_dir}/doc-urls-merged.json"
```

The redirect keeps the helper's output in `{run_dir}/doc-urls-merged.json`: §4 hands the writer that file, and the suppressed entries below are read from it.

The helper returns `{"doc_urls": [...], "suppressed": [...]}`. It deduplicates by **normalized** URL (lowercase host, strip a trailing `/index.html` and any trailing `/`), so a seeded `…/book/` and a README's `…/book/index.html` collapse to one entry; existing/corpora-seeded entries always win and keep their `source: language-registry`, so the registry-vs-detected distinction survives the merge. For a **whole-language reference** (`scope_type == "full-library"` AND ≥1 `existing` entry has `source: language-registry`) it additionally suppresses README noise on a corpus host: non-corpus path segments (`/whatsnew/`, `/contribute`, `/wiki/`) and non-primary-locale duplicates of a kept page (`/ja/master/` when `/en/master/` is kept). Ordinary skills (any other `scope_type`, or no registry corpora) pass through with dedup only — no suppression. Use the returned `doc_urls` as the brief's merged list.

**Log suppressed entries.** When `suppressed` is non-empty, log one line per entry — `"info: suppressed {url} ({reason})"` — so the operator can see what the whole-language noise filter dropped (never drop silently). The N==0 DEGRADED case (a whole-language repo whose registry returned no corpora) carries no `language-registry` entry, so suppression stays inactive and its README docs are kept — this is intentional (there is no canonical corpus host to filter against).

### 4. Write Enriched Brief

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`; first existing path wins. HALT if no candidate exists.

Write the enriched brief through the canonical writer. It starts from the upstream brief file (`--base-brief`), keeps every field and the version it holds, replaces `doc_urls` with the merged list (`--doc-urls-file`), validates the result and writes it atomically:

```bash
uv run {writeSkillBriefHelper} write --target {forge_data_folder}/{skill_name}/skill-brief.yaml --base-brief "{brief_path}" --doc-urls-file "{run_dir}/doc-urls-merged.json"
```

Leave `--doc-urls-file` out when §2 and §3 were skipped or found nothing.

**On script failure (non-zero exit):**
- Exit 1 (validation/invariant): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "input-invalid"` (SKILL.md Halt Contract), then HARD HALT (exit code 2).
- Exit 2 (I/O failure): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "write-failed"` (SKILL.md Halt Contract), then HARD HALT (exit code 4).

**On success:** Capture `brief_path` and `version` from the response envelope for step-auto-validate's envelope emission, and add each entry of its `warnings[]` to `workflow_warnings[]`.

### 5. Chain to Auto-Validate

Load, read fully, then execute {nextStepFile} to present the auto-brief validation gate, where the user can approve, edit, or reject the brief before the pipeline continues. Do this only after the enriched brief has been written and validated.
