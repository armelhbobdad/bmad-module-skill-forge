---
nextStepFile: 'step-auto-validate.md'
validateBriefSchemaProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-schema.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-schema.py'
writeSkillBriefProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-write-skill-brief.py'
  - '{project-root}/src/shared/scripts/skf-write-skill-brief.py'
emitBriefEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-brief-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-brief-result-envelope.py'
detectDocsScript: 'src/shared/scripts/skf-detect-docs.py'
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

**IF `{brief_path}` is not set or the file does not exist:**
- HARD HALT with exit code 2 (`input-missing`): "**Auto-brief requires an upstream brief — `brief_path` is missing or the file does not exist at `{brief_path}`.**"
- Emit error envelope per §6 with `halt_reason: "input-missing"`.

**Resolve `{validateBriefSchemaHelper}`** from `{validateBriefSchemaProbeOrder}`; first existing path wins. HALT if no candidate exists.

Validate the upstream brief against the schema:

```bash
uv run {validateBriefSchemaHelper} {brief_path}
```

The script returns JSON `{valid, errors[], warnings[], halt_reason, brief}`.

- **`valid: false`** — the upstream brief is malformed. HARD HALT with exit code 2 (`input-invalid`): "**Upstream brief at `{brief_path}` is invalid: {first error message}.**" Emit error envelope per §6 with `halt_reason: "input-invalid"`.
- **`valid: true`** — proceed with the parsed `brief` payload. Surface any non-empty `warnings[]` to the log.

Extract from the parsed brief:
- `skill_name` ← `brief.name`
- `version` ← `brief.version`
- `source_repo` ← `brief.source_repo`
- `language` ← `brief.language`
- `scope_type` ← `brief.scope.type`
- `forge_tier` ← `brief.forge_tier`
- `description` ← `brief.description`
- `created` ← `brief.created`
- `created_by` ← `brief.created_by`
- All scope fields: `scope.include`, `scope.exclude`, `scope.notes`, `scope.rationale`, `scope.amendments`, `scope.tier_a_include`
- Optional fields: `source_type`, `source_authority`, `doc_urls`, `target_version`, `target_ref`, `source_ref`, `scripts_intent`, `assets_intent`

**Docs-only check:** If `source_type` is `docs-only` in the parsed brief, skip §2 (Run Doc Detection) and §3 (Enrich Brief with Detected Docs) — the doc URL is already in the brief's `doc_urls`. Log: "Docs-only brief — skipping repo-based doc detection. Doc URLs provided by upstream." Proceed directly to §4 (Validate Enriched Brief). All brief fields (`source_type`, `source_authority`, `doc_urls`, `scope_type`) must pass through unmodified.

### 2. Run Doc Detection

Invoke doc detection to discover documentation URLs for the source repo:

```bash
uv run {project-root}/{detectDocsScript} --repo-url {source_repo}
```

`--repo-url` is always required (the script uses it for GitHub API calls). If a local clone is also available at `{local_clone_path}`, add `--local-path {local_clone_path}` to enable docs-folder scanning in addition to API-based detection.

**Handle exit codes:**

- **Exit 0 (found docs):** Parse the JSON output array. Each entry has `{url, detected_via, content_hash, content_type}`. Proceed to §3 with the detected docs.
- **Exit 1 (none found):** Log: "No external documentation found — brief generated from source analysis only." Proceed to §4 with no doc enrichment.
- **Exit 2 (error):** Log warning: "Doc detection failed — proceeding without doc enrichment." Do NOT halt — doc enrichment is best-effort. Proceed to §4 with no doc enrichment.

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

If the upstream brief already has `doc_urls`, merge the detected docs with the existing entries. Deduplicate by **normalized** URL — lowercase the host and strip a trailing `/index.html` and any trailing `/` before comparing — so a seeded `…/book/` and a README's `…/book/index.html` collapse to one entry rather than being fetched twice. Existing (upstream / corpora-seeded) entries take precedence — and an upstream corpus entry **retains its `source: language-registry`** on a collision, so the registry-vs-detected distinction survives the merge.

### 4. Validate Enriched Brief

Assemble the enriched brief context as a flat JSON object following the write-brief §3 contract:

```json
{
  "name":             "{skill_name}",
  "target_version":   "{target_version or null}",
  "detected_version": null,
  "source_type":      "{source_type or 'source'}",
  "source_repo":      "{source_repo}",
  "language":         "{language}",
  "description":      "{description}",
  "forge_tier":       "{forge_tier}",
  "created":          "{created}",
  "created_by":       "{created_by}",
  "scope_type":       "{scope_type}",
  "scope_include":    ["{scope.include patterns}"],
  "scope_exclude":    ["{scope.exclude patterns}"],
  "scope_notes":      "{scope.notes or ''}",
  "scope_rationale":  null,
  "scope_tier_a_include": null,
  "scope_amendments":     null,
  "doc_urls":         [{"url": "...", "label": "...", "source": "..."}],
  "scripts_intent":   "{scripts_intent or null}",
  "assets_intent":    "{assets_intent or null}",
  "source_authority": "{source_authority or null}",
  "target_ref":       "{target_ref or null}",
  "source_ref":       "{source_ref or null}",
  "version_resolved": "{version}"
}
```

The `version_resolved` key pins the output to the upstream brief's version — without it, the writer's precedence logic falls through to `1.0.0` since `target_version` and `detected_version` are both null on the auto path.

### 5. Write Enriched Brief

**Resolve `{writeSkillBriefHelper}`** from `{writeSkillBriefProbeOrder}`; first existing path wins. HALT if no candidate exists.

Write the enriched brief through the canonical writer:

```bash
echo '<context-json>' | uv run {writeSkillBriefHelper} write --target {forge_data_folder}/{skill_name}/skill-brief.yaml --from-flat
```

**On script failure (non-zero exit):**
- Exit 1 (validation/invariant): Emit error envelope per §6 with `halt_reason: "input-invalid"`, then HARD HALT.
- Exit 2 (I/O failure): Emit error envelope per §6 with `halt_reason: "write-failed"`, then HARD HALT.

**On success:** Capture `brief_path` and `version` from the response envelope for step-auto-validate's envelope emission.

### 6. Error Envelope (Canonical)

Every HARD HALT in this step emits the error envelope on stderr:

**Resolve `{emitBriefEnvelopeHelper}`** from `{emitBriefEnvelopeProbeOrder}`; first existing path wins. HALT if no candidate exists.

```bash
echo '{"status":"error","skill_name":"{skill_name or unknown}","halt_reason":"{reason}","mode":"auto"}' | \
  uv run {emitBriefEnvelopeHelper} emit --target stderr
```

### 7. Chain to Auto-Validate

Load, read fully, then execute {nextStepFile} to present the auto-brief validation gate, where the user can approve, edit, or reject the brief before the pipeline continues.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the enriched brief has been written and validated will you load and read fully {nextStepFile} to begin the auto-brief validation gate.
