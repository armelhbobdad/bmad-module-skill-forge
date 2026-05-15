---
nextStepFile: 'fetch-docs.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

# Step 3b: Fetch Temporal Context

## STEP GOAL:

To fetch temporal context (issues, PRs, changelogs, release notes) from the source repository and index it into a QMD collection for Deep tier enrichment. This ensures step 4 has historical data to search when annotating extracted functions with T2 provenance.

## Rules

- Deep tier only — Quick, Forge, and Forge+ tiers skip this step entirely and silently
- GitHub repositories only — other source types degrade gracefully
- Do not halt the workflow if fetching or indexing fails
- Do not modify extraction data from step 3 — this step only creates QMD collections

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Eligibility

Evaluate the following conditions sequentially. **If ANY condition fails, skip silently to section 5 (auto-proceed) with no output:**

1. **Tier is Deep:** If tier is Quick, Forge, or Forge+, skip silently.
2. **Source is GitHub:** Verify `source_repo` is a GitHub URL (`https://github.com/...`) or `owner/repo` format. If the source is a local path, a non-GitHub URL, or any other format, attempt GitHub remote detection (section 1b) before skipping.
3. **`gh` CLI is available:** Run `timeout 10s gh auth status` to verify the CLI is installed and authenticated (the short timeout protects against a misconfigured network or hung auth helper blocking the workflow). If it fails or times out, skip silently.

All three conditions must pass to proceed to section 2.

### 1b. GitHub Remote Detection for Local Sources

**Only runs when condition 2 above fails because `source_repo` is a local path.**

Local repositories that are clones of GitHub repos contain temporal context (issues, PRs, releases) accessible via `gh`. Detect this automatically:

1. Check if the local path is a git repository: `git -C "{source_repo}" rev-parse --is-inside-work-tree`
2. If not a git repo: skip silently to section 5 (current behavior).
3. Extract the origin remote: `git -C "{source_repo}" remote get-url origin`
4. If the remote URL contains `github.com`:
   - Extract `owner/repo` from the remote URL (strip `.git` suffix, handle both HTTPS and SSH formats)
   - Log: "**Local source with GitHub remote detected:** {owner}/{repo} — fetching temporal context."
   - Use the extracted `owner/repo` for all `gh` API calls in sections 3-4. Continue to condition 3 (gh CLI check).
5. If no remote, or remote is not GitHub: skip silently to section 5 (current behavior).

### 2. Check Cache (Skip If Fresh)

Read `forge-tier.yaml` from the sidecar path.

- Look for a `qmd_collections` entry where `skill_name` matches the current brief AND `type` is `"temporal"`.
- If found AND `created_at` is within the last **7 days** (rationale: temporal context — issues, PRs, changelogs — rarely changes meaningfully on shorter horizons; a 7-day window balances freshness against re-fetch cost and GitHub rate limits): the temporal collection is fresh. Display:

"**Temporal context: cached.** Collection `{skill-name}-temporal` is fresh ({days} days old). Skipping re-fetch."

Skip to section 5 (auto-proceed).

- If not found OR `created_at` is older than 7 days: continue to section 3.

### 3. Fetch Temporal Context

Create a staging directory: `_bmad-output/{skill-name}-temporal/`

Resolve the `owner` and `repo` from `source_repo` (e.g., `acme/toolkit` from `https://github.com/acme/toolkit`).

Execute the following fetches, writing output as markdown files to the staging directory. **If any individual fetch fails, log a warning and continue with the others:**

1. **Issues (last 100):** (rationale: 100 is `gh issue list`'s default max-per-page; a single paginated call captures recent activity without extra round trips or rate-limit pressure)

   ```bash
   gh issue list -R {owner}/{repo} --state all --limit 100 --json number,title,state,labels,createdAt,closedAt,body | ...
   ```

   Write to `{staging}/issues.md` — format as a markdown document with one section per issue (number, title, state, labels, body summary).

2. **Merged PRs (last 100):** (rationale: same 100-per-page convention as issues — captures the most recent merges in one API call)

   ```bash
   gh pr list -R {owner}/{repo} --state merged --limit 100 --json number,title,mergedAt,labels,body | ...
   ```

   Write to `{staging}/prs.md` — format as a markdown document with one section per PR.

3. **Releases (last 10):** (rationale: release notes accumulate slowly relative to issues/PRs; the most recent 10 tags cover roughly the last 6-18 months of changelog-relevant history for typical OSS projects, which is enough context for T2-past annotations without fanning out to dozens of `gh release view` calls)

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

   Iterate over every `tagName` from Step 1's JSON array. **Append each release to `{staging}/releases.md` immediately after its `gh release view` call returns** — do not buffer the entire loop in memory and write once at the end. The append-per-release pattern guarantees that a mid-loop abort (rate limit, network drop, user interrupt) leaves a partial but well-formed `releases.md` with every release fetched so far, rather than discarding all of them because the loop didn't reach its final write.

   Write an empty `{staging}/releases.md` with a header (`# Releases (partial if interrupted)`) before the loop, then append one `## {tagName} — {name} ({publishedAt})` section per successful fetch. Failed individual fetches get a one-line placeholder: `## {tagName} — fetch failed: {error}`.

   If `gh release view` fails for a specific tag, log a warning and skip that release — continue with remaining tags. If a rate limit (HTTP 429) is hit, stop the release loop, keep the partial `releases.md` file in place (do NOT delete it), and log: "Release fetch stopped at tag {N}/{total} due to rate limiting — partial releases.md retained."

   Format each section as a markdown block with tag, name, date, and body.

4. **Changelog (if exists):**

   Check if `CHANGELOG.md` or `RELEASES.md` exists in the repository root:

   ```bash
   gh api repos/{owner}/{repo}/contents/CHANGELOG.md --jq '.content' | base64 -d
   ```

   If found, write to `{staging}/changelog.md`. If not found (404), skip silently.

#### 3b. Targeted Function Searches (Uses Extraction Inventory)

After the generic fetches above, perform **targeted searches** using the top-level public API function names from `extraction_inventory.top_exports[]`. This produces high-signal results that generic list fetches miss.

**Short-circuit on empty `top_exports`:** If `extraction_inventory.top_exports` is missing or `== []` (docs-only mode, or a source extraction that produced zero public exports), skip this sub-section entirely with a one-line log: "No exports in inventory — skipping targeted function searches." The generic fetches from §3 remain in place and continue to provide baseline temporal context.

**Limit:** Search the top **10 function names** maximum to control API call volume and avoid `gh` rate limiting. (rationale: 10 targeted searches + generic fetches from §3 stays well under GitHub's unauthenticated search rate limit of 10 requests/minute and authenticated 30/minute; matches the `top_exports[]` size emitted by step 3 §5 so every tracked export gets one search.)

For each function name in `top_exports[]` (up to 10), **sanitize first**: strip every character that is not in `[A-Za-z0-9_]` from `function_name` to produce `safe_name`. This prevents shell injection and `gh` query parser errors when an export name contains punctuation (e.g., `<T>`, `.method`, `::namespace`, quotes). If `safe_name` is empty after sanitization (the original was entirely punctuation — rare but possible for symbol exports), fall back to piping the original name through stdin via `--query-from-file -`-style indirection if your `gh` version supports it; otherwise skip that one entry with a log line — never substitute the unsanitized name back into the shell command.

```bash
# safe_name = re.sub(r'[^A-Za-z0-9_]', '', function_name); skip if empty
# --limit 5: top-5 issues per function keeps signal-to-noise high (most matches
# below rank 5 are typically keyword coincidences, not targeted discussions) and
# caps the total response size across 10 function fan-outs at 50 issues.
gh search issues --repo {owner}/{repo} "{safe_name}" --limit 5 --json number,title,state,body
```

Aggregate all targeted search results into a single file: `{staging}/targeted-issues.md`. Format as a markdown document with one section per function name, listing the matching issues/PRs found.

**If `gh search` is unavailable** (older `gh` CLI versions): skip targeted searches silently. The generic fetches from section 3 still provide baseline temporal context.

**If rate limiting occurs** (HTTP 429 or similar): stop targeted searches immediately, keep results collected so far. Log: "Targeted search stopped at function {N}/{total} due to rate limiting."

**After all fetching,** verify at least one file was written to the staging directory. If the staging directory is empty (all fetches failed), log a warning and skip to section 5.

### 4. Index Into QMD & Register

**Index the staging directory:**

If a `{skill-name}-temporal` collection already exists, remove and recreate for atomic replace. **Wrap the remove + add pair with rollback on `add` failure** — a `remove` that succeeds followed by an `add` that fails must not leave the registry claiming a collection that no longer exists in QMD:

```bash
qmd collection remove {skill-name}-temporal
if ! qmd collection add {project-root}/_bmad-output/{skill-name}-temporal/ --name {skill-name}-temporal --mask "*.md"; then
  # add failed after remove succeeded — the collection is gone from QMD. Clean the registry too.
  # Remove any {skill-name}-temporal entry from forge-tier.yaml qmd_collections[].
  # Warn the user, do not fail the workflow (temporal enrichment degrades gracefully).
  echo "WARN: qmd add failed after remove — registry entry for {skill-name}-temporal removed to keep forge-tier.yaml consistent with QMD state."
  # [skip the embed step]
else
  qmd embed --collection {skill-name}-temporal
fi
```

**Rollback rule:** if the `qmd collection add` step fails (non-zero exit, network error, parse error) AND the prior `remove` succeeded, the canonical registry entry in `forge-tier.yaml` MUST be removed to match QMD's actual state. A dangling registry entry that points at a non-existent QMD collection poisons subsequent cache-hit checks in §2. Emit a warning in evidence-report and skip the embed — enrichment degrades to no-QMD for this run.

**Scope the embed:** Always pass `--collection {skill-name}-temporal` to `qmd embed`. An unscoped `qmd embed` re-embeds every collection in the QMD store, which can take minutes per run in batch mode and generates wasteful GPU/API cost. If the installed `qmd` CLI does not accept `--collection` (older upstream versions), gate the embed behind a per-skill check: if a previous `{skill-name}-temporal` entry already exists in `qmd_collections` and its `created_at` is within 24 hours, skip the embed entirely and warn "qmd embed skipped — upstream qmd lacks --collection scope; re-embedding all collections would be wasteful in batch mode". Log the skip in the evidence report.

**Note:** `qmd embed` generates vector embeddings required for semantic (`type:'vec'`) and HyDE (`type:'hyde'`) sub-queries inside the QMD `query` tool. Without embeddings, only BM25 (`type:'lex'`) keyword search works. Run `qmd embed` after every `qmd collection add`.

**Update the registry** in `forge-tier.yaml` under a file lock to prevent concurrent batch runs from clobbering each other's entries:

1. Acquire an exclusive `flock` on `{sidecar_path}/forge-tier.yaml.lock` (create the lock file if absent). Use `flock -x {lockfile} -c "..."` or an equivalent `fcntl.flock(LOCK_EX)` guard.
2. Read the current `forge-tier.yaml`, capturing its `st_mtime` as `mtime_before`.
3. Perform the read-modify-write below.
4. Write via `python3 {atomicWriteHelper} write --target {sidecar_path}/forge-tier.yaml`.
5. Release the flock.

**Fallback when `flock` is unavailable:** re-stat the file after the write; if the on-disk `st_mtime` is newer than `mtime_before` by more than this run's own write timestamp, halt with "forge-tier.yaml modified mid-update by another process — refusing to clobber. Re-run after the other run completes." This read-CAS-by-mtime is the belt-and-braces safety net for environments without `flock`.

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

