---
nextStepFile: '../enrich.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
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

## MANDATORY SEQUENCE

### 1. Check Eligibility

Evaluate the following conditions. **If the condition fails, skip silently to section 7 (auto-proceed) with no output:**

1. **`doc_urls` is present in the brief data:** Check that `doc_urls` contains at least one URL entry from step 1 context. If `doc_urls` is absent or empty, skip silently.

No tier gate — if `doc_urls` are present, this step runs at Quick, Forge, and Deep tiers alike.

### 2. Security Notice

Display an informational notice (not a gate — the user already approved these URLs in the brief):

"**Documentation fetch:** The following external URLs will be fetched:
{for each URL: `- {label}: {url}`}

Content fetched from external URLs is classified as **T3** (external, untrusted) and cited as `[EXT:{url}]`."

### 3. Fetch Documentation

**Discover available web fetching capability.** Try tools in any order — use whatever is accessible in the current environment (e.g., Firecrawl scrape, WebFetch, web-reader, MCP fetch, curl, browser tools). If no web fetching capability can be found:

- Log warning: "No web fetching capability available in this environment. Skipping documentation fetch."
- Skip to section 7 (auto-proceed).

**For each URL in `doc_urls`:**

- Fetch the content at `{url}` as clean markdown using the discovered web tool.
- **If fetch succeeds:** Store the markdown content with the URL as provenance source.
- **If fetch fails:** Log warning: "Failed to fetch {url}: {reason}. Skipping." Continue with remaining URLs.

**Subpage discovery (root URL detection):**

After fetching a URL, apply the following heuristic to detect documentation root pages that contain no useful API content. This is common with modern documentation sites (Mintlify, Docusaurus, ReadTheDocs, GitBook) that render API content on subpages.

**Root page detection — apply only when the URL path ends in `/`, `/index`, `/index.html`, has no path component (bare domain), or has 1 path segment (e.g., `/docs`). For deeper URL paths (2+ segments like `/api/reference`), skip this heuristic and keep the content as-is.**

Subpage discovery is triggered if **either** of the following independent triggers fires:

**Trigger 1 — Content-based (both conditions must be true):**

1. **Zero API content indicators:** The fetched markdown contains none of: fenced code blocks (`` ``` ``), parameter tables (`|---|`), or function signature patterns (`def `, `function `, `fn `, `func `, `export `).
2. **High link density:** More than 70% of non-empty lines are markdown links (matching `[text](url)` with no other substantive content on the line).

**Trigger 2 — URL-based (independent of content analysis):**

The URL matches the path criteria above (ends in `/`, bare domain, or 1 segment) AND the fetched content is under **2000 words**. Short content on root-like URLs almost certainly indicates a navigation hub or landing page, even if it contains introductory code examples that would prevent Trigger 1 from firing. This handles modern doc sites (Mintlify, Docusaurus, GitBook) that include hero sections with code snippets on their root pages.

If neither trigger fires, keep the page content as-is and do NOT trigger subpage discovery.

**If a root URL with minimal content is detected:**

1. **Attempt sitemap/map discovery:** Use whatever discovery tool is available:
   - Firecrawl: `firecrawl_map({url})` to discover all subpages
   - Manual: try fetching `{url}/sitemap.xml` and parsing URLs from it
   - Crawl: if a crawl tool is available, use it with depth=1 on the root URL
   - If no discovery tool is available, keep the root page content as-is and continue

2. **Filter discovered URLs by relevance and origin:** Restrict candidates to the same **registrable domain** as the root URL — strip the URL down to its eTLD+1 (e.g., for root `https://docs.example.com/intro`, accept any subdomain of `example.com` such as `api.example.com` or `docs.example.com`, but reject `example.org` or `cdn.partner.io`). Cross-origin links must be discarded before any fetch. The same-registrable-domain rule prevents Mintlify/Docusaurus link clouds from pulling in tracking pixels, doc-site CDNs, or third-party embeds as if they were canonical docs. From the surviving same-domain candidates, select the most relevant pages by searching for API-related terms in the URL path or title (e.g., `api`, `reference`, `quickstart`, `setup`, `config`, `getting-started`, `guide`, `sdk`, `methods`, `functions`). Exclude pages that are clearly non-API content (e.g., `blog`, `changelog`, `pricing`, `about`, `careers`).

3. **Fetch top subpages (in parallel):** Fetch up to **10** of the most relevant subpages **concurrently** — subpage fetches are independent and network-bound, so wall-clock benefits substantially from parallel execution. Bound concurrency to **4 in flight** at a time to stay polite to documentation hosts (Mintlify/Docusaurus typically allow more, but conservatism here protects against unrecognized rate limits).

   The parallel pattern depends on the fetch tool:

   - **LLM-driven tools** (Firecrawl `firecrawl_scrape`, `WebFetch`, MCP fetch, browser tools): issue up to 4 tool calls **in a single message**. The agent runtime executes parallel tool calls concurrently; collect results from the batch before issuing the next set of up to 4. Repeat until all up-to-10 subpages have been attempted or rate limiting halts the batch.
   - **Bash-driven tools** (`curl`, `wget`): use `xargs -P 4 -n 1` to fan out from a newline-separated subpage list. Example:

     ```bash
     printf '%s\n' "${subpages[@]}" | xargs -P 4 -n 1 -I {} bash -c '
       url="{}"
       safe=$(echo -n "$url" | sha256sum | cut -c1-12)
       curl -sSL --max-time 30 "$url" > "{staging}/subpage-$safe.md" \
         || echo "fetch failed: $url" > "{staging}/subpage-$safe.md"
     '
     ```

   For each subpage (regardless of tool):
   - Use the same web fetching tool as the root URL
   - Store with the subpage URL as provenance: `[EXT:{subpage-url}]`
   - If a subpage fetch fails, skip it and continue with the rest of the batch — do not halt the whole stage

4. **Rate limiting:** If rate limiting (HTTP 429) is encountered during subpage fetching, stop discovery for this root URL. Keep results collected so far. Log: "Subpage discovery stopped due to rate limiting." For the parallel-tool-call pattern, drop any not-yet-issued tool calls from subsequent batches; for the `xargs` pattern, interrupt the pipeline (set `--max-procs 0` is **not** a graceful stop — the simplest stop is to kill the xargs PID and let in-flight writers complete naturally).

**If ALL URLs fail (including any subpage fetches):** Log warning: "No documentation could be fetched. Proceeding without T3 content." Skip to section 7 (auto-proceed).

### 4. Extract API Information from Fetched Content

Parse the successfully fetched markdown for:

- **Function/method signatures** and their parameters
- **Return types** and data structures
- **Configuration options** and their defaults
- **Usage examples** and code snippets

**Citation rule:** Every extracted item gets a T3 confidence citation: `[EXT:{url}]` where `{url}` is the source URL the item was extracted from.

**No hallucination:** If information cannot be found in the fetched content, exclude it. Do not infer or fabricate API details.

### 5. Build Doc-Fetch Inventory

**Mode determines merge behavior:**

- **`source_type: "docs-only"`** — The doc-fetch inventory IS the extraction inventory. It replaces the empty inventory from step 3, since there was no source code to extract from.
- **`source_type: "source"` (supplemental mode)** — Merge T3 items into the existing extraction inventory from step 3.

**Conflict rule:** T3 items NEVER override existing T1, T1-low, or T2 items for the same export. When an export already has a higher-confidence entry, the T3 item is discarded. T3 has the lowest priority.

**Edge case — T1-zero supplemental mode:** If T1 extraction produced zero results and `doc_urls` are present in supplemental mode, T3 items should be used as the primary inventory since no T1 data exists to conflict with.

**Aggregate totals for reporting:**
- URLs fetched successfully vs. total
- URLs that failed
- T3 items extracted

### 5b. Index into QMD (Deep Tier Only)

**If tier is not Deep:** Skip this section silently.

**If tier is Deep and at least one URL was fetched successfully:**

1. Write fetched markdown files to a staging directory: `_bmad-output/{skill-name}-docs/`
2. Index into QMD with atomic replace + rollback: if a `{skill-name}-docs` collection already exists, run `qmd collection remove {skill-name}-docs` first, then `qmd collection add {project-root}/_bmad-output/{skill-name}-docs/ --name {skill-name}-docs --mask "*.md"`. **If `qmd collection add` fails after a successful `remove`:** remove any matching `{skill-name}-docs` entry from `forge-tier.yaml` → `qmd_collections[]` to keep the registry consistent with QMD's actual state, warn in evidence-report, and skip the embed — docs enrichment degrades gracefully.
3. Generate embeddings scoped to this collection (only if step 2 `add` succeeded): `qmd embed --collection {skill-name}-docs` (required for semantic `type:'vec'` and HyDE `type:'hyde'` sub-queries within the QMD `query` tool). If the installed `qmd` CLI does not accept `--collection`, gate the embed behind a freshness check: skip re-embedding if the existing `{skill-name}-docs` registry entry is within 24 hours, and log the skip in the evidence report to prevent unbounded batch-mode re-embedding.
4. Register in forge-tier.yaml `qmd_collections` array — **acquire an exclusive `flock` on `{sidecar_path}/forge-tier.yaml.lock` for the read-modify-write** (see the locking pattern documented in step 3b §4). Write via `python3 {atomicWriteHelper} write --target {sidecar_path}/forge-tier.yaml`. If `flock` is unavailable, fall back to read-CAS-by-mtime (capture `st_mtime` before, re-check after; refuse to clobber if a concurrent run wrote in between).

```yaml
- name: "{skill-name}-docs"
  type: "docs"
  source_workflow: "create-skill"
  skill_name: "{skill-name}"
  created_at: "{current ISO date}"
```

5. Clean up staging directory after indexing: `rm -rf {project-root}/_bmad-output/{skill-name}-docs/`

**If QMD indexing fails:** Warn: "QMD indexing of fetched docs failed. T3 items are still in the extraction inventory — enrichment will proceed without QMD-indexed docs." Continue.

### 6. Report

Display:

"**Documentation fetch complete.**
**URLs processed:** {fetched}/{total}
**T3 items extracted:** {count}
**Confidence:** All doc-fetched items are T3 — `[EXT:{url}]` citations applied.
{If docs-only mode: '**Mode:** Docs-only — all skill content is T3. source_authority: community'}

Proceeding to enrichment..."

### 7. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After documentation fetch is complete (or skipped for any reason), immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- No `doc_urls` in brief: skip directly to next step with no output
- No web fetching available: skip with warning then auto-proceed
- All URLs failed: skip with warning then auto-proceed
- Successful fetch: display report then auto-proceed
- All failures degrade gracefully — skip and auto-proceed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN documentation is fetched and T3 items are merged into the extraction inventory (or the step is skipped due to no `doc_urls`, no web tools, or fetch failures) will you proceed to load `{nextStepFile}` for enrichment.

---

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:

- No `doc_urls` in brief: skipped silently, auto-proceeded
- `doc_urls` present: each URL fetched using whatever web tool is available
- Root URLs with minimal content: subpage discovery attempted, relevant subpages fetched
- Individual fetch failures handled gracefully (skip and continue)
- All extracted content cited as T3 with `[EXT:{url}]` provenance
- Existing T1/T1-low/T2 items never overridden by T3 data
- Docs-only mode: doc-fetch inventory correctly replaces empty extraction inventory
- Supplemental mode: T3 items merged into existing inventory respecting conflict rule
- Auto-proceeded to step 4

### SYSTEM FAILURE:

- Halting the workflow because web fetching is unavailable or a URL fails
- Including fetched content without `[EXT:{url}]` citations
- Overriding existing higher-confidence extractions (T1, T1-low, T2) with T3 data
- Hardcoding a specific fetching tool instead of being tool-agnostic
- Hallucinating API details not found in the fetched content
- Beginning compilation in this step (that is step 5)

**Master Rule:** Documentation fetching is best-effort T3 enrichment. Fetch what you can, cite everything as `[EXT:{url}]`, never override higher-confidence data, and move on. Failures degrade gracefully — they never block the skill compilation pipeline.
