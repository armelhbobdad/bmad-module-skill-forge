---
name: 'step-03c-fetch-docs'
description: 'Fetch remote documentation from URLs for T3-confidence content — all tiers, tool-agnostic'
nextStepFile: './step-04-enrich.md'
---

# Step 3c: Fetch Remote Documentation

## STEP GOAL:

Fetch remote documentation from brief-specified URLs using whatever web fetching capability is available in the agent's environment, extract API information, and add T3-confidence content to the extraction inventory. Tool-agnostic — the agent uses Firecrawl, WebFetch, web-reader, curl, or any available web tool.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- CRITICAL: Read the complete step file before taking any action
- ALWAYS follow the exact instructions in the step file
- TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- You are a skill compilation engine fetching external documentation for T3 enrichment
- Doc fetching is best-effort — individual URL failures never block the workflow
- Graceful degradation is paramount — if no web fetching tools are available, skip with a warning and proceed

### Step-Specific Rules:

- No tier gate — this step runs at any tier when `doc_urls` are present in the brief
- Tool-agnostic — use whatever web fetching capability is available (Firecrawl, WebFetch, web-reader, curl, browser tools, etc.)
- FORBIDDEN to halt the workflow if web fetching is unavailable or fails
- FORBIDDEN to override existing T1, T1-low, or T2 extraction data with T3 content
- FORBIDDEN to begin compilation — that is step-05

## EXECUTION PROTOCOLS:

- Follow MANDATORY SEQUENCE exactly
- Every extracted item receives a T3 confidence citation: `[EXT:{url}]`
- Merge doc-fetch results into the extraction inventory per the conflict rule in section 5
- Do NOT hallucinate content — if information is not in the fetched text, exclude it

## CONTEXT BOUNDARIES:

- Available: brief_data (including `doc_urls`, `source_type`), tier, extraction_inventory from step-03
- Focus: Fetching external documentation and producing T3-confidence extraction items
- Limits: Do NOT modify existing T1/T1-low/T2 items, begin enrichment, or compile content
- Dependencies: Step-03 extraction must be complete (even if inventory is empty for docs-only briefs)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Eligibility

Evaluate the following conditions. **If the condition fails, skip silently to section 7 (auto-proceed) with no output:**

1. **`doc_urls` is present in the brief data:** Check that `doc_urls` contains at least one URL entry from step-01 context. If `doc_urls` is absent or empty, skip silently.

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

2. **Filter discovered URLs by relevance:** From the discovered subpage list, select the most relevant pages by searching for API-related terms in the URL path or title (e.g., `api`, `reference`, `quickstart`, `setup`, `config`, `getting-started`, `guide`, `sdk`, `methods`, `functions`). Exclude pages that are clearly non-API content (e.g., `blog`, `changelog`, `pricing`, `about`, `careers`).

3. **Fetch top subpages:** Fetch up to **10** of the most relevant subpages. For each:
   - Use the same web fetching tool as the root URL
   - Store with the subpage URL as provenance: `[EXT:{subpage-url}]`
   - If a subpage fetch fails, skip it and continue

4. **Rate limiting:** If rate limiting (HTTP 429) is encountered during subpage fetching, stop discovery for this root URL. Keep results collected so far. Log: "Subpage discovery stopped due to rate limiting."

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

- **`source_type: "docs-only"`** — The doc-fetch inventory IS the extraction inventory. It replaces the empty inventory from step-03, since there was no source code to extract from.
- **`source_type: "source"` (supplemental mode)** — Merge T3 items into the existing extraction inventory from step-03.

**Conflict rule:** T3 items NEVER override existing T1, T1-low, or T2 items for the same export. When an export already has a higher-confidence entry, the T3 item is discarded. T3 has the lowest priority.

**Aggregate totals for reporting:**
- URLs fetched successfully vs. total
- URLs that failed
- T3 items extracted

### 5b. Index into QMD (Deep Tier Only)

**If tier is not Deep:** Skip this section silently.

**If tier is Deep and at least one URL was fetched successfully:**

1. Write fetched markdown files to a staging directory: `_bmad-output/{skill-name}-docs/`
2. Index into QMD: `qmd collection add {project-root}/_bmad-output/{skill-name}-docs/ --name {skill-name}-docs --mask "*.md"`
3. Generate embeddings: `qmd embed` (required for `vector_search` and `deep_search`)
4. Register in forge-tier.yaml `qmd_collections` array:

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
- Auto-proceeded to step-04

### SYSTEM FAILURE:

- Halting the workflow because web fetching is unavailable or a URL fails
- Including fetched content without `[EXT:{url}]` citations
- Overriding existing higher-confidence extractions (T1, T1-low, T2) with T3 data
- Hardcoding a specific fetching tool instead of being tool-agnostic
- Hallucinating API details not found in the fetched content
- Beginning compilation in this step (that is step-05)

**Master Rule:** Documentation fetching is best-effort T3 enrichment. Fetch what you can, cite everything as `[EXT:{url}]`, never override higher-confidence data, and move on. Failures degrade gracefully — they never block the skill compilation pipeline.
