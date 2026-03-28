---
name: 'step-03b-fetch-temporal'
description: 'Fetch temporal context (issues, PRs, changelogs) and index into QMD — Deep tier only'
nextStepFile: './step-03c-fetch-docs.md'
---

# Step 3b: Fetch Temporal Context

## STEP GOAL:

To fetch temporal context (issues, PRs, changelogs, release notes) from the source repository and index it into a QMD collection for Deep tier enrichment. This ensures step-04 has historical data to search when annotating extracted functions with T2 provenance.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine fetching temporal data for QMD enrichment
- ✅ Temporal context is best-effort — failures never block the workflow
- ✅ Graceful degradation is paramount — non-GitHub repos or missing tools are silent skips, not errors

### Step-Specific Rules:

- 🎯 Deep tier only — Quick, Forge, and Forge+ tiers skip this step entirely and silently
- 🎯 GitHub repositories only — other source types degrade gracefully
- 🚫 FORBIDDEN to halt the workflow if fetching or indexing fails
- 🚫 FORBIDDEN to modify extraction data from step-03 — this step only creates QMD collections
- 💾 Write fetched content to a staging directory, index into QMD, then clean up

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Write fetched markdown files to a staging directory: `_bmad-output/{skill-name}-temporal/`
- 📖 Index the staging directory into QMD and register in `forge-tier.yaml`
- 🚫 Never leave staging files on disk after indexing — always clean up

## CONTEXT BOUNDARIES:

- Available: brief_data, tier, source_location from step-01; extraction_inventory from step-03
- **Used from extraction_inventory:** `top_exports[]` — the list of top-level public API function names (typically 10-20). Used for targeted GitHub searches (section 3b). If `extraction_mode: "docs-only"` or `top_exports` is absent/empty, skip targeted searches silently.
- Focus: Creating a QMD temporal collection for the source repository
- Limits: Do NOT modify extraction data, begin enrichment, or compile content
- Dependencies: Extraction must be complete from step-03

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Eligibility

Evaluate the following conditions sequentially. **If ANY condition fails, skip silently to section 5 (auto-proceed) with no output:**

1. **Tier is Deep:** If tier is Quick, Forge, or Forge+, skip silently.
2. **Source is GitHub:** Verify `source_repo` is a GitHub URL (`https://github.com/...`) or `owner/repo` format. If the source is a local path, a non-GitHub URL, or any other format, attempt GitHub remote detection (section 1b) before skipping.
3. **`gh` CLI is available:** Run `gh auth status` to verify the CLI is installed and authenticated. If it fails, skip silently.

All three conditions must pass to proceed to section 2.

### 1b. GitHub Remote Detection for Local Sources

**Only runs when condition 2 above fails because `source_repo` is a local path.**

Local repositories that are clones of GitHub repos contain temporal context (issues, PRs, releases) accessible via `gh`. Detect this automatically:

1. Check if the local path is a git repository: `git -C {source_repo} rev-parse --is-inside-work-tree`
2. If not a git repo: skip silently to section 5 (current behavior).
3. Extract the origin remote: `git -C {source_repo} remote get-url origin`
4. If the remote URL contains `github.com`:
   - Extract `owner/repo` from the remote URL (strip `.git` suffix, handle both HTTPS and SSH formats)
   - Log: "**Local source with GitHub remote detected:** {owner}/{repo} — fetching temporal context."
   - Use the extracted `owner/repo` for all `gh` API calls in sections 3-4. Continue to condition 3 (gh CLI check).
5. If no remote, or remote is not GitHub: skip silently to section 5 (current behavior).

### 2. Check Cache (Skip If Fresh)

Read `forge-tier.yaml` from the sidecar path.

- Look for a `qmd_collections` entry where `skill_name` matches the current brief AND `type` is `"temporal"`.
- If found AND `created_at` is within the last **7 days**: the temporal collection is fresh. Display:

"**Temporal context: cached.** Collection `{skill-name}-temporal` is fresh ({days} days old). Skipping re-fetch."

Skip to section 5 (auto-proceed).

- If not found OR `created_at` is older than 7 days: continue to section 3.

### 3. Fetch Temporal Context

Create a staging directory: `_bmad-output/{skill-name}-temporal/`

Resolve the `owner` and `repo` from `source_repo` (e.g., `acme/toolkit` from `https://github.com/acme/toolkit`).

Execute the following fetches, writing output as markdown files to the staging directory. **If any individual fetch fails, log a warning and continue with the others:**

1. **Issues (last 100):**

   ```bash
   gh issue list -R {owner}/{repo} --state all --limit 100 --json number,title,state,labels,createdAt,closedAt,body | ...
   ```

   Write to `{staging}/issues.md` — format as a markdown document with one section per issue (number, title, state, labels, body summary).

2. **Merged PRs (last 100):**

   ```bash
   gh pr list -R {owner}/{repo} --state merged --limit 100 --json number,title,mergedAt,labels,body | ...
   ```

   Write to `{staging}/prs.md` — format as a markdown document with one section per PR.

3. **Releases (last 10):**

   **Note:** `gh release list --json` does **not** support the `body` field. Use a two-step approach: list tags first, then fetch each release individually with `--json` (which IS supported on `gh release view`).

   ```bash
   # Step 1: Get release tags (body NOT available here)
   gh release list -R {owner}/{repo} --limit 10 --json tagName,name,publishedAt
   ```

   If Step 1 returns an empty array (no releases), skip Step 2 and omit the releases section entirely.

   ```bash
   # Step 2: For EACH tagName from Step 1, fetch the full release
   gh release view {tagName} -R {owner}/{repo} --json tagName,name,publishedAt,body
   ```

   Iterate over every `tagName` from Step 1's JSON array. If `gh release view` fails for a specific tag, log a warning and skip that release — continue with remaining tags. If a rate limit (HTTP 429) is hit, stop the release loop, keep results collected so far, and log: "Release fetch stopped at tag {N}/{total} due to rate limiting."

   Write to `{staging}/releases.md` — format as a markdown document with one section per release (tag, name, date, body).

4. **Changelog (if exists):**

   Check if `CHANGELOG.md` or `RELEASES.md` exists in the repository root:

   ```bash
   gh api repos/{owner}/{repo}/contents/CHANGELOG.md --jq '.content' | base64 -d
   ```

   If found, write to `{staging}/changelog.md`. If not found (404), skip silently.

#### 3b. Targeted Function Searches (Uses Extraction Inventory)

After the generic fetches above, perform **targeted searches** using the top-level public API function names from `extraction_inventory.top_exports[]`. This produces high-signal results that generic list fetches miss.

**Limit:** Search the top **10 function names** maximum to control API call volume and avoid `gh` rate limiting.

For each function name in `top_exports[]` (up to 10):

```bash
gh search issues --repo {owner}/{repo} "{function_name}" --limit 5 --json number,title,state,body
```

Aggregate all targeted search results into a single file: `{staging}/targeted-issues.md`. Format as a markdown document with one section per function name, listing the matching issues/PRs found.

**If `gh search` is unavailable** (older `gh` CLI versions): skip targeted searches silently. The generic fetches from section 3 still provide baseline temporal context.

**If rate limiting occurs** (HTTP 429 or similar): stop targeted searches immediately, keep results collected so far. Log: "Targeted search stopped at function {N}/{total} due to rate limiting."

**After all fetching,** verify at least one file was written to the staging directory. If the staging directory is empty (all fetches failed), log a warning and skip to section 5.

### 4. Index Into QMD & Register

**Index the staging directory:**

If a `{skill-name}-temporal` collection already exists, remove and recreate for atomic replace:

```bash
qmd collection remove {skill-name}-temporal
qmd collection add {project-root}/_bmad-output/{skill-name}-temporal/ --name {skill-name}-temporal --mask "*.md"
qmd embed
```

**Note:** `qmd embed` generates vector embeddings required for `vector_search` and `deep_search`. Without it, only BM25 keyword `search` works. Run it after every `qmd collection add`.

**Update the registry** in `forge-tier.yaml`:

If an entry with `name: "{skill-name}-temporal"` already exists in `qmd_collections`, replace it. Otherwise, append:

```yaml
  - name: "{skill-name}-temporal"
    type: "temporal"
    source_workflow: "create-skill"
    skill_name: "{skill-name}"
    created_at: "{current ISO date}"
```

**Clean up** the staging directory after successful indexing:

```bash
rm -rf {project-root}/_bmad-output/{skill-name}-temporal/
```

**Error handling:**

- If QMD indexing fails: log the error, note that temporal enrichment will be unavailable. Do NOT fail the workflow.
- If registry update fails: log the error, continue. The collection may exist in QMD even if the registry entry failed.
- If cleanup fails: log a warning and continue.

Display brief confirmation:

"**Temporal context indexed.** Collection `{skill-name}-temporal` created ({file_count} files: {list files}). Proceeding to enrichment..."

### 5. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After temporal context is fetched and indexed (or skipped for any reason), immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Quick/Forge/Forge+ tiers skip directly to next step with no output
- Non-GitHub sources skip directly to next step with no output
- Cached collections (< 7 days old) skip with brief cache-hit message
- Deep tier with fresh fetch displays brief confirmation then auto-proceeds
- All failures degrade gracefully — skip and auto-proceed

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN temporal context is indexed into QMD (or the step is skipped due to eligibility, cache, or failure) will you proceed to load `{nextStepFile}` for documentation fetch.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Non-eligible scenarios (Quick/Forge/Forge+ tier, non-GitHub source, no `gh` CLI) skipped silently
- Cached collections (< 7 days old) detected and re-fetch skipped
- Temporal data fetched via `gh` CLI into staging directory (generic + targeted)
- Targeted searches performed for up to 10 top_exports function names
- At least one temporal file written (issues, PRs, releases, changelog, or targeted-issues)
- Collection `{skill-name}-temporal` indexed into QMD
- Registry entry added/updated in forge-tier.yaml with type `"temporal"`
- Staging directory cleaned up after indexing
- Auto-proceeded to step-03c

### ❌ SYSTEM FAILURE:

- Halting the workflow due to a `gh` CLI, QMD, or network failure
- Leaving staging files on disk after indexing (must clean up)
- Overwriting or modifying extraction data from step-03
- Displaying skip messages for Quick/Forge/Forge+ tiers (should be silent)
- Attempting to fetch temporal data from non-GitHub sources
- Not registering the collection in forge-tier.yaml after successful indexing

**Master Rule:** Temporal context is best-effort enrichment data. Fetch what you can, index it, clean up, and move on. Failures degrade gracefully — they never block the skill compilation pipeline.
