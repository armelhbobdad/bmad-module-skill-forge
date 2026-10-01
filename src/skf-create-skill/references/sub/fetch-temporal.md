---
nextStepFile: 'fetch-docs.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
# Resolve `{forgeTierRwHelper}` by probing `{forgeTierRwProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. §2 reads the registry through it and §4 changes the registry only
# through it. If neither resolves, §2 finds no cached entry and §4 skips the
# registry change with a warning: temporal enrichment never halts the workflow.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# If neither path exists, §1 skips the step: temporal enrichment never
# halts the workflow.
fetchTemporalProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-fetch-temporal.py'
  - '{project-root}/src/shared/scripts/skf-fetch-temporal.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3b: Fetch Temporal Context

## STEP GOAL:

To fetch temporal context (issues, PRs, changelogs, release notes) from the source repository, keep the fetched files as the skill's temporal feeder, and index them into a QMD collection for Deep tier enrichment. This ensures step 4 has historical data to search when annotating extracted functions with T2 provenance, and that step 5c's doc-rot scan can read the same files.

## Rules

- Deep tier only — Quick, Forge, and Forge+ tiers skip this step entirely and silently
- GitHub repositories only — other source types degrade gracefully
- Do not halt the workflow if fetching or indexing fails
- Do not modify extraction data from step 3: this step only writes the temporal feeder folder, the fetch folder that replaces it, and the QMD collection indexed from it

## MANDATORY SEQUENCE

### 1. Check Eligibility

Set `{temporal_feeder}` to null first, so that in a `--batch` run one brief's feeder never carries into the next. Then evaluate the following conditions sequentially. **If ANY condition fails, leave `{temporal_feeder}` null and skip silently to section 5 (auto-proceed) with no output:**

1. **Tier is Deep:** If tier is Quick, Forge, or Forge+, skip silently.
2. **The source is a GitHub repository `gh` can read:** resolve `{fetchTemporalHelper}` from `{fetchTemporalProbeOrder}` and, from `{project-root}`, run:

   ```bash
   uv run {fetchTemporalHelper} repo --source-repo "{source_repo}"
   ```

   Skip silently when the command exits non-zero, when its `skip_reason` is not null, and when no candidate resolves. Otherwise bind `{temporal_repo}` ← its `repo`, and when its `via` is `origin`, log: "**Local source with GitHub remote detected:** {temporal_repo}. Fetching temporal context."

Both conditions must pass to proceed to section 2. Then bind `{temporal_feeder}` ← `{forge_data_folder}/{skill-name}/.skf-temporal`: the folder where this step keeps what it fetched (sections 3 and 4). Step 5c's doc-rot scan reads the files in it, and a null `{temporal_feeder}` tells step 5c that no temporal feeder was expected.

### 2. Check Cache (Skip If Fresh)

Resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}` and read the registry as JSON, from `{project-root}`:

```bash
uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"
```

Bind `{registry_collections}` ← its `data.qmd_collections`: an empty list when `exists` is false, the list is missing, the command fails or no candidate resolves. Section 4 reads it again for its embed check.

- Look for a `{registry_collections}` entry where `skill_name` matches the current brief AND `type` is `"temporal"`.
- If `{temporal_feeder}` holds no `.md` file, continue to section 3 even when that entry is fresh: a cache hit must leave step 5c files to read, and an earlier SKF release deleted the folder once it was indexed.
- If found AND `created_at` is within the last **7 days** (rationale: temporal context — issues, PRs, changelogs — rarely changes meaningfully on shorter horizons; a 7-day window balances freshness against re-fetch cost and GitHub rate limits): the temporal collection is fresh. Display:

"**Temporal context: cached.** Collection `{skill-name}-temporal` is fresh ({days} days old). Skipping re-fetch."

Skip to section 5 (auto-proceed).

- If not found OR `created_at` is older than 7 days: continue to section 3.

### 3. Fetch Temporal Context

Fetch through the helper, from `{project-root}`. Pass the extraction inventory's `top_exports[]` as a JSON list for the targeted issue searches; when it is empty or missing (docs-only mode, or a source extraction with no public exports), leave out `--exports -` and the heredoc:

```bash
uv run {fetchTemporalHelper} fetch --repo "{temporal_repo}" --feeder "{temporal_feeder}" --exports - <<'SKF_TOP_EXPORTS'
{top_exports as a JSON list}
SKF_TOP_EXPORTS
```

It fetches into a fresh folder beside `{temporal_feeder}` and replaces the feeder with it only when the fetch returned something (`uv run {fetchTemporalHelper} --help` describes the files it writes and the swap).

Show each of its `warnings`. Then:

- **Exit 0** (`status: "replaced"`): `{temporal_feeder}` now holds this fetch, and `files` lists it. Continue to section 4.
- **Exit 3** (`status: "kept"`: no fetch returned anything): log a warning and skip to section 5. `{temporal_feeder}` stays bound and keeps what the last good fetch left in it: step 5c scans those files, or reports the missing feeder in the evidence report when there are none.
- **Exit 1 or 2:** as for exit 3, with the helper's error (its stderr) in the warning.

### 4. Index Into QMD & Register

**Index `{temporal_feeder}`:**

If a `{skill-name}-temporal` collection already exists, remove and recreate for atomic replace. **Wrap the remove + add pair with rollback on `add` failure:** a `remove` that succeeds followed by an `add` that fails must not leave the registry claiming a collection that no longer exists in QMD. The registry changes below go through `{forgeTierRwHelper}` (resolved in section 2), which holds `{sidecar_path}/forge-tier.yaml.lock` for its one read-modify-write, so no step takes a lock of its own:

```bash
qmd collection remove {skill-name}-temporal
if ! qmd collection add "{temporal_feeder}" --name {skill-name}-temporal --mask "*.md"; then
  # add failed after remove succeeded: the collection is gone from QMD, so its registry entry goes too.
  uv run {forgeTierRwHelper} remove-qmd-collection --target "{forgeTierConfig}" --name {skill-name}-temporal
  echo "WARN: qmd add failed after remove; registry entry for {skill-name}-temporal removed to keep forge-tier.yaml consistent with QMD state."
else
  qmd embed --collection {skill-name}-temporal
fi
```

**Rollback rule:** if the `qmd collection add` step fails (non-zero exit, network error, parse error) after the prior `remove` succeeded, the `remove-qmd-collection` call above removes the registry entry, to match QMD's actual state. A dangling registry entry that points at a non-existent QMD collection poisons subsequent cache-hit checks in §2. Emit a warning in evidence-report and skip the embed and the registration below: enrichment degrades to no-QMD for this run.

**Scope the embed:** Always pass `--collection {skill-name}-temporal` to `qmd embed`. An unscoped `qmd embed` re-embeds every collection in the QMD store, which can take minutes per run in batch mode and generates wasteful GPU/API cost. If the installed `qmd` CLI does not accept `--collection` (older upstream versions), gate the embed behind a per-skill check: if the `{skill-name}-temporal` entry section 2 found in `{registry_collections}` has a `created_at` within 24 hours, skip the embed entirely and warn "qmd embed skipped: upstream qmd lacks --collection scope; re-embedding all collections would be wasteful in batch mode". Log the skip in the evidence report.

**Note:** `qmd embed` generates vector embeddings required for semantic (`type:'vec'`) and HyDE (`type:'hyde'`) sub-queries inside the QMD `query` tool. Without embeddings, only BM25 (`type:'lex'`) keyword search works. Run `qmd embed` after every `qmd collection add`.

**Register the collection** only when `qmd collection add` succeeded. The helper replaces the entry with `name: "{skill-name}-temporal"` or appends it, and its lock keeps concurrent batch runs from losing each other's entries:

```bash
uv run {forgeTierRwHelper} register-qmd-collection --target "{forgeTierConfig}" <<'SKF_REGISTRY_ENTRY'
{"name": "{skill-name}-temporal", "type": "temporal", "source_workflow": "create-skill", "skill_name": "{skill-name}", "created_at": "{current ISO date}"}
SKF_REGISTRY_ENTRY
```

**Keep `{temporal_feeder}`.** It is the source path of the `{skill-name}-temporal` collection and the temporal feeder step 5c's doc-rot scan reads, on this run and on every cache hit until a later fetch replaces it (section 3), so this step never deletes it. Its `.skf-` name, like the fetch folder's, marks it as SKF output to SKF's ownership checks, so it stays with the skill's forge folder: a purge of the whole skill deletes it and a rename moves it.

**Error handling:**

- If QMD indexing fails: log the error, note that temporal enrichment will be unavailable. Do not fail the workflow. The files stay in `{temporal_feeder}` for step 5c.
- If a registry command fails, or `{forgeTierRwHelper}` does not resolve: log the error, continue. The collection may exist in QMD even if the registry entry failed.

Display brief confirmation:

"**Temporal context indexed.** Collection `{skill-name}-temporal` created ({file_count} files: {list files}). Proceeding to enrichment..."

### 5. Auto-Proceed

No user interaction. After temporal context is fetched and indexed (or skipped for any reason — non-Deep tier, non-GitHub source, cache hit, or any failure), load `{nextStepFile}`, read it fully, then execute it.

