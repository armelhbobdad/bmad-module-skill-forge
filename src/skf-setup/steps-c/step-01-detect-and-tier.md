---
nextStepFile: './step-01b-ccc-index.md'
tierRulesData: 'references/tier-rules.md'
---

# Step 1: Detect Tools and Determine Tier

## STEP GOAL:

Verify availability of the four forge tools (ast-grep, gh, qmd, ccc), read any existing configuration for re-run comparison, check for tier override, and calculate the capability tier.

## Rules

- Focus only on tool detection and tier calculation — do not write any files (Step 02)
- Do not skip any tool check — all 4 must be verified
- Tool command failures are not errors — they indicate unavailability

## MANDATORY SEQUENCE

### 1. Load Tier Rules

Load and read {tierRulesData} for the tool detection commands and tier calculation logic.

### 2. Check for Existing Configuration (Re-run Detection)

**Read existing forge-tier.yaml** at `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml`:
- If exists: store the current `tier` value as `{previous_tier}`, `tier_detected_at` as `{previous_detection_date}`, and the `tools` map as `{previous_tools}` (for tool-set delta detection in step-04 — same-tier re-runs surface newly-installed tools that didn't change the tier).
- If not found: set `{previous_tier}` to null and `{previous_tools}` to an empty map (first run).

**Read existing preferences.yaml** at `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml`:
- If exists: check for `tier_override` value
- If not found: set `{tier_override}` to null

**First-run preamble** — when `{previous_tier}` is null AND `{headless_mode}` is `false`, display this preamble before continuing to tool detection so the user knows what is about to happen and can abort cleanly with Esc / Ctrl+C before any writes:

"**About to set up the forge.** This workflow will:

- Detect available tools (ast-grep, gh, qmd, ccc) — read-only probes only
- Write `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` (capability tier + tool state)
- Write `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml` (first-run defaults)
- Create `{forge_data_folder}/` if missing
- When ccc is available: augment `{project-root}/.cocoindex_code/settings.yml` with SKF exclusion patterns, then create or refresh the project ccc index

Press Esc or Ctrl+C now if this isn't the right project — no files have been written yet."

### 3. Verify Tool: ast-grep

Run: `ast-grep --version`

- If succeeds: record `{ast_grep: true}` and store version string
- If fails (command not found or error): record `{ast_grep: false}`

### 4. Verify Tool: gh

Run: `gh --version`

- If succeeds: record `{gh_cli: true}` and store version string
- If fails: record `{gh_cli: false}`

### 5. Verify Tool: qmd

Run: `qmd status`

- If succeeds and indicates operational: record `{qmd: true}`
- If fails or indicates not initialized: record `{qmd: false}`

### 6. Check Optional: Security Scan (SNYK_TOKEN)

Check if the `SNYK_TOKEN` environment variable is set:

- If `SNYK_TOKEN` is non-empty: record `{security_scan: true}`
- If `SNYK_TOKEN` is empty or unset: record `{security_scan: false}`

This is informational only — security scan availability does NOT affect the tier level. It is recorded in forge-tier.yaml so that create-skill's validation step can report actionable guidance when security scanning is unavailable.

### 7. Verify Tool: ccc (cocoindex-code)

**Step A — Binary identity:** Run `ccc --help`

- If exits 0 AND the help output contains the identity marker `CocoIndex Code` (case-insensitive substring match — present in the genuine cocoindex-code CLI banner): identity confirmed. Continue to Step B.
- If exits 0 BUT the marker is absent (e.g. `ccc` is shadowed by an alias for an unrelated tool such as `code2prompt`): record `{ccc: false}`. Skip Step B. Do not run `ccc doctor` against a foreign binary — its exit code says nothing about cocoindex-code health.
- If fails (command not found or error): record `{ccc: false}`. Skip Step B.

**Step B — Daemon health:** Run `ccc doctor`

- If daemon is running and model check OK: record `{ccc: true, ccc_daemon: "healthy"}` and store version string from output
- If daemon is not running: record `{ccc: true, ccc_daemon: "stopped"}` — binary available, daemon needs starting. Step-01b will handle this.
- If error or timeout: record `{ccc: true, ccc_daemon: "error"}` — binary works but daemon has issues.

ccc availability gates the Forge+ tier and enhances Deep tier when present.

### 8. Calculate Tier

**If `{tier_override}` is set and valid (Quick, Forge, Forge+, or Deep):**
- Use `{tier_override}` as `{calculated_tier}`
- Note that override is active for the report step

**If no override, apply tier rules from {tierRulesData} in order — the first matching rule wins. Do not continue checking once a match is found:**
- `{ast_grep}` AND `{gh_cli}` AND `{qmd}` all true → **Deep**
- `{ast_grep}` AND `{ccc}` both true, but NOT (`{gh_cli}` AND `{qmd}`) → **Forge+**
- `{ast_grep}` true (regardless of ccc/gh/qmd) → **Forge**
- Otherwise → **Quick**

**If `{tier_override}` is set but invalid (any value other than the case-sensitive `Quick`, `Forge`, `Forge+`, or `Deep`):** ignore it, use detected tier. Set `{tier_override_invalid: true}` and `{tier_override_invalid_value: <the bad value>}` in context for step-04 reporting.

### 8b. Evaluate `--require-tier` (when set)

If `{require_tier}` is set (resolved in On Activation), check whether the available tools satisfy the requested tier — independent of which tier was *named* — using the tool prerequisites from `{tierRulesData}`:

- `Quick` — always satisfied.
- `Forge` — satisfied iff `{ast_grep}` is true.
- `Forge+` — satisfied iff `{ast_grep}` AND `{ccc}` are both true.
- `Deep` — satisfied iff `{ast_grep}` AND `{gh_cli}` AND `{qmd}` are all true.

This is a tool-prerequisite check, not a tier-name comparison. Deep does not subsume Forge+ (Deep does not require ccc), so a `Deep` calculation with no ccc still fails `--require-tier=Forge+`.

Set the following context flags for step-04:

- `{require_tier_satisfied: true|false}`
- `{require_tier_failure_missing_tools: <comma-separated list of missing tools, e.g. "gh, qmd">}` (only when not satisfied)

If `{require_tier}` is null (not set), set `{require_tier_satisfied: null}` so step-04 knows to skip the failure block entirely.

### 9. Auto-Proceed

After all 4 core tools have been verified, the optional security scan checked, and the tier calculated, display "**Proceeding to CCC index check...**", then load `{nextStepFile}`, read it fully, and execute it.

