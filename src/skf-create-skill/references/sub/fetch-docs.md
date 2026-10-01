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
# If neither path exists, §3 looks for no subpages: a docs fetch never
# halts the workflow.
detectDocsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-docs.py'
  - '{project-root}/src/shared/scripts/skf-detect-docs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3c: Fetch Remote Documentation

## STEP GOAL:

Fetch remote documentation from brief-specified URLs using whatever web fetching capability is available in the agent's environment, extract API information, and add T3-confidence content to the extraction inventory. Tool-agnostic — the agent uses Firecrawl, WebFetch, web-reader, curl, or any available web tool.

## Rules

- No tier gate — runs at any tier when `doc_urls` are present in the brief
- Tool-agnostic — use whatever web fetching capability is available
- Do not halt the workflow if web fetching is unavailable or fails
- Do not override existing T1, T1-low, or T2 extraction data with T3 content
- Never delete the staging directory of a `docs-only` skill — the fetched pages are its only source corpus

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
- Skip to section 7 (auto-proceed).

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

**If ALL URLs fail (including any subpage fetches):** Log warning: "No documentation could be fetched. Proceeding without T3 content." Skip to section 7 (auto-proceed): `{docs_staging}` holds no page of this run.

### 4. Extract API Information from Fetched Content

Parse the successfully fetched markdown for:

- **Function/method signatures** and their parameters
- **Return types** and data structures
- **Configuration options** and their defaults
- **Usage examples** and code snippets

**Citation rule:** Every extracted item gets a T3 confidence citation: `[EXT:{url}]` where `{url}` is the source URL the item was extracted from.

**No hallucination:** If information cannot be found in the fetched content, exclude it. Do not infer or fabricate API details.

**Whole-language references — retain prose, do not shred (`whole_language_reference: true`):** For a whole-language reference the registry-sourced corpora (the guide/Book, the standard/library docs) ARE the product, not the compiler's internal exports. Reducing that prose to per-export signature items and then discarding it under the §5 "T3 never overrides T1" rule (the compiler's AST already owns names like `Vec`, `Option`, `HashMap`) would gut exactly the content the skill exists to teach. So for these briefs, skip §4a below for the registry corpora.

### 4a. Retain the Language Guide (whole-language references only)

**Skip this section entirely unless `whole_language_reference: true`.** When it is true, for each `doc_urls` entry whose `source` is `language-registry`:

- Do not reduce its fetched markdown to per-export items. Instead retain the cleaned prose as a Language-Guide entry `{url, label, prose}`, where `prose` is the substantive body (narrative, idioms, usage examples, conceptual reference) lightly trimmed of navigation/boilerplate, each block cited `[EXT:{url}]`.
- Collect these into a `language_guide[]` context artifact, in `doc_urls` order.

This artifact is a **distinct** carrier — it is not merged into the extraction inventory and is not subject to the §5 conflict rule, so the canonical prose survives intact into step 5 (compile), which foregrounds it as the skill's Language Guide. Non-registry docs (README-detected, homepage, Pages, docs-folder) still flow through §4's normal per-export extraction and the §5 merge unchanged.

**If a registry corpus could not be fetched** (network failure), record it in `language_guide[]` as `{url, label, prose: null}` and warn — step 5 surfaces the gap rather than emitting a thin guide silently.

### 5. Build Doc-Fetch Inventory

**Mode determines merge behavior:**

- **`source_type: "docs-only"`** — The doc-fetch inventory IS the extraction inventory. It replaces the empty inventory from step 3, since there was no source code to extract from.
- **`source_type: "source"` (supplemental mode)** — Merge T3 items into the existing extraction inventory from step 3.

**Conflict rule:** T3 items never override existing T1, T1-low, or T2 items for the same export. When an export already has a higher-confidence entry, the T3 item is discarded — T3 has the lowest priority.

**Language-Guide carve-out:** the `language_guide[]` artifact from §4a (whole-language references) is not part of the export inventory and is therefore not subject to this conflict rule — it carries no export key, so it cannot collide with a T1 compiler export and can never be pruned. It is passed separately into step 5, which renders it as the foregrounded Language Guide section. Only the per-export T3 items participate in the T1/T2/T3 merge.

**Edge case — T1-zero supplemental mode:** If T1 extraction produced zero results and `doc_urls` are present in supplemental mode, T3 items should be used as the primary inventory since no T1 data exists to conflict with.

**Aggregate totals for reporting:**
- URLs fetched successfully vs. total
- URLs that failed
- T3 items extracted

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

Once the pages are extracted, and at Deep tier indexed by §5b, remove `{docs_staging}` **only when `source_type` is `"source"`**: `rm -rf {project-root}/_bmad-output/{skill-name}-docs/`. At Deep tier the folder is the source path of the `{skill-name}-docs` collection §5b registered; removing it is accepted for supplemental docs, whose T3 items already live in the extraction inventory. **When `source_type` is `"docs-only"`, keep the folder at every tier:** the fetched pages are the skill's only source corpus, since there is no code tree, so deleting them would leave nothing to verify citations against and, at Deep tier, the just-registered collection with nothing to refresh from. Record the kept path in the evidence report.

### 6. Report

Display:

"**Documentation fetch complete.**
**URLs processed:** {fetched}/{total}
**T3 items extracted:** {count}
**Confidence:** All doc-fetched items are T3 — `[EXT:{url}]` citations applied.
{If docs-only mode: '**Mode:** Docs-only — all skill content is T3. source_authority: community'}
{If docs-only mode: '**Docs corpus kept:** `{docs_staging}`{if the `{skill-name}-docs` collection was registered in §5b: ', the source path of QMD collection `{skill-name}-docs`'}'}

Proceeding to enrichment..."

### 7. Auto-Proceed

No user interaction. After the fetch completes or is skipped for any reason, load `{nextStepFile}`, read it fully, then execute it.
