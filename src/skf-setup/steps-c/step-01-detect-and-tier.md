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

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Tier Rules

Load and read {tierRulesData} for the tool detection commands and tier calculation logic.

### 2. Check for Existing Configuration (Re-run Detection)

**Read existing forge-tier.yaml** at `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml`:
- If exists: store the current `tier` value as `{previous_tier}` and `tier_detected_at` as `{previous_detection_date}`
- If not found: set `{previous_tier}` to null (first run)

**Read existing preferences.yaml** at `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml`:
- If exists: check for `tier_override` value
- If not found: set `{tier_override}` to null

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

**Step A — Binary existence:** Run `ccc --help`

- If exits 0: binary confirmed. Continue to Step B.
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

**If `{tier_override}` is set but invalid:** ignore it, use detected tier, flag for warning in report.

### 9. Auto-Proceed

"**Proceeding to CCC index check...**"

#### Menu Handling Logic:

- After tier calculation is complete, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after detection and calculation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all 4 core tools have been verified, optional security scan checked, and the tier calculated will you load and read fully `{nextStepFile}` to execute the CCC index check step.

