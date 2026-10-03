---
nextStepFile: '../enrich.md'
forgeTierConfig: '{sidecar_path}/forge-tier.yaml'
# Resolve `{forgeTierRwHelper}` by probing `{forgeTierRwProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. §5b changes the registry only through it. If neither resolves,
# §5b skips the registry change with a warning: a docs fetch never halts the
# workflow.
forgeTierRwProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-forge-tier-rw.py'
  - '{project-root}/src/shared/scripts/skf-forge-tier-rw.py'
# Resolve `{deriveAssemblyShapeHelper}` the same way — used in §1 to decide
# whether this is a whole-language reference (registry-corpora prose retained
# as a Language Guide) or a standard skill (unchanged behaviour).
deriveAssemblyShapeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-derive-assembly-shape.py'
  - '{project-root}/src/shared/scripts/skf-derive-assembly-shape.py'
# If neither path exists, §3 looks for no subpages.
detectDocsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
# §5 merges the T3 items into the extraction inventory and counts it through
# it; step 3 §5 already halted when neither path exists.
extractionInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py'
  - '{project-root}/src/shared/scripts/skf-extraction-inventory.py'
# §4a writes the Language Guide's index beside the inventory through it; if
# neither path exists, step 5 has no guide and says so.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# HARD HALT helpers (Rules).
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3c: Fetch Remote Documentation

## STEP GOAL:

Fetch remote documentation from brief-specified URLs using whatever web fetching capability is available in the agent's environment, extract API information, and add T3-confidence content to the extraction inventory. Tool-agnostic — the agent uses Firecrawl, WebFetch, web-reader, curl, or any available web tool.

## Rules

- No tier gate — runs at any tier when `doc_urls` are present in the brief
- Tool-agnostic — use whatever web fetching capability is available
- Do not halt the workflow if web fetching is unavailable or fails, with one exception: a `docs-only` brief left with nothing to compile halts at §5's zero-content check, before anything is staged. The user may still stop the run at §5's zero-export gate ([R])
- Do not override existing T1, T1-low, or T2 extraction data with T3 content
- Never delete the staging directory of a `docs-only` skill, whose only source corpus is the fetched pages, or of a whole-language reference, whose Language Guide step 5 reads from them
- A HARD HALT, once step 3 §2b has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### 1. Check Eligibility

Evaluate the following conditions. **If the condition fails, skip silently to section 7 (auto-proceed) with no output:**

1. **`doc_urls` is present in the brief data:** Check that `doc_urls` contains at least one URL entry from step 1 context. If `doc_urls` is absent or empty, skip silently.

No tier gate — if `doc_urls` are present, this step runs at Quick, Forge, and Deep tiers alike.

**Determine assembly shape (whole-language gate).** Resolve `{deriveAssemblyShapeHelper}` from `{deriveAssemblyShapeProbeOrder}` (first existing path wins) and run it on the brief:

```bash
uv run {deriveAssemblyShapeHelper} {brief_path}
```

If the result's `assembly_shape` is `whole-language-reference` (the brief carries ≥1 `doc_urls` entry with `source: language-registry` — a compiler/interpreter repo enriched with the language's canonical prose), set the in-context flag `whole_language_reference: true`. This changes ONLY how the registry-sourced corpora are handled below (§4a): their prose is retained as a **Language Guide** rather than shredded into per-export items. For every other brief the flag is false and this step behaves exactly as before — no change to ordinary skills.

### 2. Security Notice

Display an informational notice (not a gate — the user already approved these URLs in the brief):

"**Documentation fetch:** The following external URLs will be fetched:
{for each URL: `- {label}: {url}`}

Content fetched from external URLs is classified as **T3** (external, untrusted) and cited as `[EXT:{url}]`."

### 3. Fetch Documentation

**Discover available web fetching capability.** Try tools in any order — use whatever is accessible in the current environment (e.g., Firecrawl scrape, WebFetch, web-reader, MCP fetch, curl, browser tools). If no web fetching capability can be found:

- Log warning: "No web fetching capability available in this environment. Skipping documentation fetch."
- Continue at §5's **Zero-content check**: nothing was fetched.

Bind `{docs_staging}` ← `{project-root}/_bmad-output/{skill-name}-docs`, the folder that holds every page this step fetches. Just before the first page this run fetched is saved, create the folder or empty it (`mkdir -p "{docs_staging}" && rm -f "{docs_staging}"/*.md`), so a corpus kept from an earlier docs-only run (§5c) is replaced by this run's pages, never mixed with them, and stays as it was when every fetch fails.

**For each URL in `doc_urls`** (the `{n}`th entry, counting from 1):

- Fetch the content at `{url}` as clean markdown using the discovered web tool.
- **If fetch succeeds:** Store the markdown content with the URL as provenance source, and save it as `{docs_staging}/page-{n}.md`.
- **If fetch fails:** Log warning: "Failed to fetch {url}: {reason}. Skipping." Continue with remaining URLs.

**Subpage discovery (root URL detection):**

A documentation root page often holds no API content of its own: Mintlify, Docusaurus, ReadTheDocs and GitBook sites render it on subpages. Resolve `{detectDocsHelper}` from `{detectDocsProbeOrder}` (first existing path wins) and measure each saved page, from `{project-root}`:

```bash
uv run {detectDocsHelper} page-metrics --url "{url}" "{docs_staging}/page-{n}.md"
```

It prints `discover_subpages`, true when the page is a documentation root with little API content of its own (`uv run {detectDocsHelper} page-metrics --help` gives the test and the counts it prints with it). When it is false, the command exits non-zero, or no candidate resolves, keep the page as it is and look for no subpages.

**If `discover_subpages` is true:**

1. **Attempt sitemap/map discovery:** Use whatever discovery tool is available:
   - Firecrawl: `firecrawl_map({url})` to discover all subpages
   - Manual: fetch `{url}/sitemap.xml`
   - Crawl: if a crawl tool is available, use it with depth=1 on the root URL
   - If no discovery tool is available, keep the root page content as-is and continue

2. **Keep the subpages of the root's own site:** pass what discovery found to the helper on stdin, from `{project-root}`: pipe the sitemap in as below, or feed the map or crawl result (its JSON, or one URL per line) to the same command through a heredoc:

   ```bash
   curl -fsSL --max-time 30 "{url}/sitemap.xml" | uv run {detectDocsHelper} filter-urls --root "{url}" -
   ```

   It lists in `kept[]` the URLs on the root page's own site that may hold API content, each with the API words its path or title holds (`terms`), and in `sitemaps[]` the sitemaps a sitemap index names: filter each of them the same way (`uv run {detectDocsHelper} filter-urls --help` gives the rules). When it exits non-zero, leave that input out. Never fetch a URL the helper did not keep. From `kept[]`, choose the subpages most relevant to the skill's API: `terms` points at them.

3. **Fetch top subpages (in parallel):** Fetch up to **10** of the most relevant subpages **concurrently** — subpage fetches are independent and network-bound, so wall-clock benefits substantially from parallel execution. Bound concurrency to **4 in flight** at a time to stay polite to documentation hosts (Mintlify/Docusaurus typically allow more, but conservatism here protects against unrecognized rate limits).

   The parallel pattern depends on the fetch tool:

   - **LLM-driven tools** (Firecrawl `firecrawl_scrape`, `WebFetch`, MCP fetch, browser tools): issue up to 4 tool calls **in a single message**. The agent runtime executes parallel tool calls concurrently; collect results from the batch before issuing the next set of up to 4. Repeat until all up-to-10 subpages have been attempted or rate limiting halts the batch.
   - **Bash-driven tools** (`curl`, `wget`): use `xargs -P 4` to fan out from a newline-separated subpage list, numbering the subpages as it goes. Example, for the `{n}`th `doc_urls` entry:

     ```bash
     printf '%s\n' "${subpages[@]}" | awk '{ print NR, $0 }' | xargs -P 4 -L 1 sh -c '
       f="{docs_staging}/subpage-{n}-$0.md"
       curl -fsSL --max-time 30 "$1" -o "$f" || { rm -f "$f"; echo "fetch failed: $1" >&2; }
     '
     ```

   For each subpage (regardless of tool):
   - Use the same web fetching tool as the root URL, and save the page in `{docs_staging}` as `subpage-{n}-{k}.md`, `{k}` counting this root's subpages from 1, only when its fetch succeeded: a failed fetch leaves no file, as in the snippet
   - Store with the subpage URL as provenance: `[EXT:{subpage-url}]`
   - If a subpage fetch fails, skip it and continue with the rest of the batch — do not halt the whole stage

4. **Rate limiting:** If rate limiting (HTTP 429) is encountered during subpage fetching, stop discovery for this root URL. Keep results collected so far. Log: "Subpage discovery stopped due to rate limiting." For the parallel-tool-call pattern, drop any not-yet-issued tool calls from subsequent batches; for the `xargs` pattern, interrupt the pipeline (set `--max-procs 0` is **not** a graceful stop — the simplest stop is to kill the xargs PID and let in-flight writers complete naturally).

**If ALL URLs fail (including any subpage fetches):** Log warning: "No documentation could be fetched." `{docs_staging}` holds no page of this run: continue at §5's **Zero-content check**, which halts a `docs-only` brief and lets a source brief go on without T3 content.

### 4. Extract API Information from Fetched Content

Parse the successfully fetched markdown for:

- **Function/method signatures** and their parameters
- **Return types** and data structures
- **Configuration options** and their defaults
- **Usage examples** and code snippets

**Citation rule:** Every extracted item gets a T3 confidence citation: `[EXT:{url}]` where `{url}` is the source URL the item was extracted from.

**No hallucination:** If information cannot be found in the fetched content, exclude it. Do not infer or fabricate API details.

**Whole-language references (`whole_language_reference: true`): retain the prose, do not shred it.** For a whole-language reference the registry-sourced corpora (the guide/Book, the standard/library docs) ARE the product, not the compiler's internal exports. So for these briefs, extract no per-export items from the registry corpora (`source: language-registry`): §4a below keeps their pages as the Language Guide.

### 4a. Retain the Language Guide (whole-language references only)

**Skip this section entirely unless `whole_language_reference: true`.** When it is true, for each `doc_urls` entry whose `source` is `language-registry`:

- Do not reduce its fetched markdown to per-export items. Its pages stay in `{docs_staging}` as §3 saved them (`page-{n}.md` and its `subpage-{n}-{k}.md` files), and §5c keeps the folder: step 5 reads the prose from them and retains it as the skill's Language Guide, each block cited `[EXT:{url}]`.
- List the entry in a `language_guide[]` index, in `doc_urls` order, as `{url, label, pages}`: `pages` names the files of `{docs_staging}` that hold its fetched pages, and is empty when the fetch failed (warn: step 5 surfaces the gap rather than emitting a thin guide silently).

Write the index beside the extraction inventory, so step 5 finds the pages after a context compaction. Bind `{language_guide_json}` ← `{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json`, resolve `{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {atomicWriteHelper} write --target "{language_guide_json}" <<'SKF_LANGUAGE_GUIDE'
{"docs_folder": "{docs_staging}", "language_guide": [{"url": "...", "label": "...", "pages": ["page-1.md"]}]}
SKF_LANGUAGE_GUIDE
```

When it fails, or no path resolves, warn "The Language Guide was not saved: {its message}": step 5 then assembles without it. The guide is a **distinct** carrier: it is not merged into the extraction inventory and is not subject to the §5 conflict rule, so the canonical prose survives intact into step 5 (compile), which foregrounds it as the skill's Language Guide. Non-registry docs (README-detected, homepage, Pages, docs-folder) still flow through §4's normal per-export extraction and the §5 merge unchanged.

### 5. Build Doc-Fetch Inventory

**Mode determines merge behavior:**

- **`source_type: "docs-only"`**: the doc-fetch inventory IS the extraction inventory. Its T3 items fill the empty inventory step 3 wrote, since there was no source code to extract from.
- **`source_type: "source"` (supplemental mode)**: the T3 items join the exports step 3 extracted.

Either way, merge them into `{extraction_inventory}`, the file step 3 §5 wrote, one object per item with its `[EXT:{url}]` citation and, when the item documents an export, its `export_name`. Resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}` and, from `{project-root}`, run:

```bash
uv run {extractionInventoryHelper} add --inventory "{extraction_inventory}" --field t3_items <<'SKF_T3'
[{"export_name": "...", "kind": "signature|type|config|example", "content": "...", "citation": "[EXT:{url}]"}]
SKF_T3
```

**Conflict rule:** T3 items never override existing T1, T1-low, or T2 items for the same export. The helper applies it: an item whose `export_name` names an export the inventory already holds is left out and listed in `dropped`. When it exits non-zero, fix the JSON and run it once more.

**Language-Guide carve-out:** the `language_guide[]` from §4a (whole-language references) is not part of the export inventory and is therefore not subject to this conflict rule: it carries no export key, so it cannot collide with a T1 compiler export and can never be pruned. Step 5 reads it through `{language_guide_json}` and renders it as the foregrounded Language Guide section. Only the per-export T3 items participate in the T1/T2/T3 merge.

**Edge case: T1-zero supplemental mode.** If T1 extraction produced zero results and `doc_urls` are present in supplemental mode, compile uses the T3 items as the primary inventory, since no T1 data exists to conflict with.

**Aggregate totals for reporting:**
- URLs fetched successfully vs. total
- URLs that failed
- T3 items extracted

**Zero-content check.** Run `uv run {extractionInventoryHelper} summary --inventory "{extraction_inventory}"` from `{project-root}` and read its `counts`:

- **`source_type: "docs-only"`, no URL or subpage fetched in this run, and `counts.items` is 0:** there is nothing to compile, and a docs-only skill has no other source. Stage and promote nothing: **HARD HALT** (exit code 3, `docs-unreachable`, phase `fetch-docs`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "**No documentation could be fetched for `{skill-name}`, so there is nothing to compile.** Failed: {each `doc_urls` URL with its reason}. Check the network and that this environment has a web fetch tool, or fix `doc_urls` in the brief, then re-run create-skill."
- **`source_type: "source"`, `counts.exports` is 0 and every `doc_urls` fetch failed:** step 3 §6's zero-export check let this brief through because it declares `doc_urls`. Apply that check here: show its warning and offer **[C] Continue anyway** or **[R] Refine the brief**: stop here. **GATE [default: C]**: under `{headless_mode}`, log and record its `zero-exports` decision as step 3 §6 says, and continue. On [R], **HARD HALT** (exit code 6, `halted-for-brief-refinement`, phase `fetch-docs`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "**Halting create-skill:** no public export was extracted and no `doc_urls` page could be fetched. Fix `scope.include`, `target_version` or `doc_urls` in the brief (or re-run `skf-brief-skill`), then re-run `skf-create-skill`."
- **Otherwise:** continue. When no page of this run was saved (every fetch failed, or no fetch tool), skip §5b and §5c, which have nothing to index or remove, and go on to §6: `{docs_staging}` stays as it was.

### 5b. Index into QMD (Deep Tier Only)

**If tier is not Deep:** Skip this section silently.

**If tier is Deep and at least one URL was fetched successfully:**

1. The fetched pages are already in `{docs_staging}` (section 3), which this section indexes.
2. Index into QMD with atomic replace + rollback: if a `{skill-name}-docs` collection already exists, run `qmd collection remove {skill-name}-docs` first, then `qmd collection add {project-root}/_bmad-output/{skill-name}-docs/ --name {skill-name}-docs --mask "*.md"`. Resolve `{forgeTierRwHelper}` from `{forgeTierRwProbeOrder}`: every registry change of this section goes through it, and it holds `{sidecar_path}/forge-tier.yaml.lock` for its one read-modify-write, so no step takes a lock of its own. **If `qmd collection add` fails after a successful `remove`:** remove the registry entry too, so the registry matches QMD's actual state, warn in evidence-report, and skip steps 3 and 4, since docs enrichment degrades gracefully:

   ```bash
   uv run {forgeTierRwHelper} remove-qmd-collection --target "{forgeTierConfig}" --name {skill-name}-docs
   ```

3. Generate embeddings scoped to this collection (only if step 2 `add` succeeded): `qmd embed --collection {skill-name}-docs` (required for semantic `type:'vec'` and HyDE `type:'hyde'` sub-queries within the QMD `query` tool). If the installed `qmd` CLI does not accept `--collection`, gate the embed behind a freshness check: read the registry with `uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"`, skip re-embedding when the `{skill-name}-docs` entry in its `data.qmd_collections` was created within the last 24 hours, and log the skip in the evidence report to prevent unbounded batch-mode re-embedding.
4. Register the collection in the `qmd_collections` array (only if step 2 `add` succeeded). The helper replaces the entry with the same `name` or appends it:

   ```bash
   uv run {forgeTierRwHelper} register-qmd-collection --target "{forgeTierConfig}" <<'SKF_REGISTRY_ENTRY'
   {"name": "{skill-name}-docs", "type": "docs", "source_workflow": "create-skill", "skill_name": "{skill-name}", "created_at": "{current ISO date}"}
   SKF_REGISTRY_ENTRY
   ```

**If QMD indexing fails:** Warn: "QMD indexing of fetched docs failed. T3 items are still in the extraction inventory — enrichment will proceed without QMD-indexed docs." Continue.

### 5c. Keep or Remove the Fetched Pages

Once the pages are extracted, and at Deep tier indexed by §5b, remove `{docs_staging}` **only when `source_type` is `"source"` and the brief is not a whole-language reference** (`whole_language_reference` false): `rm -rf {project-root}/_bmad-output/{skill-name}-docs/`. A whole-language reference keeps the folder, since its Language Guide index (§4a) points step 5 at the pages in it. At Deep tier the folder is the source path of the `{skill-name}-docs` collection §5b registered; removing it is accepted for supplemental docs, whose T3 items already live in the extraction inventory. **When `source_type` is `"docs-only"`, keep the folder at every tier:** the fetched pages are the skill's only source corpus, since there is no code tree, so deleting them would leave nothing to verify citations against and, at Deep tier, the just-registered collection with nothing to refresh from. Record the kept path in the evidence report.

### 6. Report

Display:

"**Documentation fetch complete.**
**URLs processed:** {fetched}/{total}
**T3 items extracted:** {count}
**Confidence:** All doc-fetched items are T3 — `[EXT:{url}]` citations applied.
{If docs-only mode: '**Mode:** Docs-only — all skill content is T3. source_authority: community'}
{If docs-only mode or a whole-language reference: '**Docs corpus kept:** `{docs_staging}`{if the `{skill-name}-docs` collection was registered in §5b: ', the source path of QMD collection `{skill-name}-docs`'}'}

Proceeding to enrichment..."

### 7. Auto-Proceed

No user interaction. After the fetch completes or is skipped for any reason, load `{nextStepFile}`, read it fully, then execute it.
