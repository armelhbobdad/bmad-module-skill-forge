---
nextStepFile: 'ccc-index.md'
# Resolve `{detectToolsHelper}` by probing `{detectToolsProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — the script is the source of truth for
# tool detection and tier calculation; no fallback to prose-driven probes.
detectToolsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-tools.py'
  - '{project-root}/src/shared/scripts/skf-detect-tools.py'
---

<!-- Config: communicate in {communication_language}. The first-run preamble below is user-visible — render it in the user's language. -->

# Step 1: Detect Tools and Determine Tier

## STEP GOAL:

Verify availability of the four forge tools (ast-grep, gh, qmd, ccc), read any existing configuration for re-run comparison, check for tier override, and calculate the capability tier — all via `{detectToolsHelper}` so the deterministic work is done once, by a tested script, never by the LLM.

## Rules

- Focus only on tool detection and tier calculation — do not write any files (Step 02)
- Never reimplement tool probes or the tier rules in prose — the script is authoritative
- Tool command failures are not errors — they indicate unavailability (the script swallows them)

## MANDATORY SEQUENCE

### 1. Check for Existing Configuration (Re-run Detection)

Prior state lives in two files; the detector helper (§2) reads forge-tier.yaml itself when invoked with `--prior-state-from`, so this section only handles preferences.yaml directly and the first-run preamble.

**Read existing preferences.yaml** at `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml`:

- If exists: check for `tier_override` value
- If not found: set `{tier_override}` to null

**First-run preamble** — when the prior-state read (§2 below, `prior.previous_tier`) returns null AND `{headless_mode}` is `false`, display this preamble before continuing so the user knows what is about to happen and can abort cleanly with Esc / Ctrl+C before any writes. (When `{headless_mode}` is true, skip the preamble entirely — pipelines never need it.)

"**About to set up the forge.** This workflow will:

- Detect available tools (ast-grep, gh, qmd, ccc) — read-only probes only
- Write `{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml` (capability tier + tool state)
- Write `{project-root}/_bmad/_memory/forger-sidecar/preferences.yaml` (first-run defaults)
- Create `{forge_data_folder}/` if missing
- When ccc is available: augment `{project-root}/.cocoindex_code/settings.yml` with SKF exclusion patterns, then create or refresh the project ccc index

**About tiers:** SKF picks one of four tiers (Quick / Forge / Forge+ / Deep) based on which tools are installed. **All four are fully usable** — higher tiers add power, they don't fix gaps. If you're new and only have a base Python install, Quick tier is the right starting point and the report at the end will show you exactly which tools to install if you want to climb later.

Press Esc or Ctrl+C now if this isn't the right project — no files have been written yet."

### 2. Run Detection Helper

Build the Bash invocation: `uv run {detectToolsHelper} --prior-state-from "{project-root}/_bmad/_memory/forger-sidecar/forge-tier.yaml"`. If `{tier_override}` is non-null, append `--tier-override "{tier_override}"`. If `{require_tier}` is non-null, append `--require-tier "{require_tier}"`. Then execute. (The script's PEP 723 metadata is why `uv run` is required — bare `python3` skips dependency resolution.)

The script (see `src/shared/scripts/skf-detect-tools.py` docstring for the full `DETECT_OUTPUT_SCHEMA`) probes ast-grep / gh / qmd / ccc concurrently with two-step verification for qmd and ccc (binary-identity check + daemon-health check, including the `CocoIndex Code` identity-marker substring check that rejects PATH-shadowing aliases). It applies the 4-rule tier table, performs the tier-override sanity check (override is honored but flagged unsafe when underlying tools are missing), and evaluates `--require-tier` using a tool-prerequisite check (Deep does NOT subsume Forge+ — Deep does not require ccc). Output is one JSON document on stdout.

### 3. Parse Output and Set Context Flags

From the JSON, set these context flags. Field paths are relative to the script's top-level object.

From `tools`:

- `{ast_grep}` ← `tools.ast_grep.available`
- `{ast_grep_version}` ← `tools.ast_grep.version`
- `{gh_cli}` ← `tools.gh_cli.available`
- `{gh_cli_version}` ← `tools.gh_cli.version`
- `{qmd}` ← `tools.qmd.available`
- `{qmd_status}` ← `tools.qmd.status` (`"absent" | "daemon_stopped" | "healthy"` — drives the climb-hint distinction in step 4)
- `{qmd_version}` ← `tools.qmd.version`
- `{ccc}` ← `tools.ccc.available`
- `{ccc_daemon}` ← `tools.ccc.daemon` (`"healthy" | "stopped" | "error" | null`)
- `{ccc_version}` ← `tools.ccc.version`
- `{security_scan}` ← `tools.security_scan.available` (informational only — never affects tier)

From `tier`:

- `{calculated_tier}` ← `tier.calculated` — the tier downstream steps act on
- `{detected_tier}` ← `tier.detected` — what would have been chosen without override
- `{tier_override_active}` ← `tier.override_applied`
- `{tier_override_invalid}` ← `tier.override_invalid`
- `{tier_override_invalid_value}` ← `tier.override_invalid_value`
- `{tier_override_invalid_suggestion}` ← `tier.override_invalid_suggestion` (closest valid tier name from a fuzzy match — `null` when no candidate cleared the cutoff or when override is valid; consumed by step 4's invalid-override note as a "did you mean ...?" hint)
- `{tier_override_unsafe}` ← `tier.override_unsafe`
- `{tier_override_unsafe_missing}` ← `tier.override_unsafe_missing` (a list — step 4 joins with `", "` for display)

From `require_tier`:

- `{require_tier_satisfied}` ← `require_tier.satisfied` (`true | false | null`; null when `--require-tier` was not set)
- `{require_tier_failure_missing_tools}` ← `require_tier.missing_tools` (a list)

From `prior` (populated by `--prior-state-from`; all fields null/empty on first run):

- `{previous_tier}` ← `prior.previous_tier`
- `{previous_detection_date}` ← `prior.previous_detection_date`
- `{previous_tools}` ← `prior.previous_tools`
- `{previous_ccc_index_status}` ← `prior.previous_ccc_index_status`
- `{previous_ccc_indexed_path}` ← `prior.previous_ccc_indexed_path`
- `{previous_ccc_last_indexed}` ← `prior.previous_ccc_last_indexed`
- `{previous_ccc_staleness_threshold_hours}` ← `prior.previous_ccc_staleness_threshold_hours`

From `deltas` (computed by the script from current tools + prior; eliminates LLM-side set arithmetic in the report banner):

- `{tools_added}` ← `deltas.tools_added` (the list)
- `{tools_removed}` ← `deltas.tools_removed` (the list)
- `{tier_changed}` ← `deltas.tier_changed` (boolean)

**The script is the source of truth.** Every tier-rules edge case (override-honored-but-unsafe, Deep-doesn't-subsume-Forge+, qmd-binary-vs-daemon distinction, ccc-identity-marker rejection of foreign binaries) is locked into the test suite at `test/test-skf-detect-tools.py`. Substituting prose-driven logic for the script's output here will cause subtle re-run regressions that the prompt's prose is no longer detailed enough to catch.

### 4. Auto-Proceed

After context flags are populated, display "**Proceeding to CCC index check...**", then load `{nextStepFile}`, read it fully, and execute it.
