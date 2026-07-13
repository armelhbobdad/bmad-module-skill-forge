---
# Static reference loaded by load-skill.md §1b only when
# `snippet_skill_root_override` is UNSET in config.yaml. When the
# override is set, every existing snippet's on-disk prefix is ground
# truth by contract — no probe needed and the entire authoring-repo
# escape hatch is already configured. Loaded once per export run, not
# per skill.
# Resolve `{rebuildManagedSectionsHelper}` by probing
# `{rebuildManagedSectionsProbeOrder}` in order (installed SKF module
# path first, src/ dev-checkout fallback); first existing path wins.
# The `root-probe` action reads each candidate snippet's first line,
# parses/strips the `root:` prefix, and returns `observed_prefixes` +
# `mismatch` — deterministic prefix comparison the LLM must not re-derive.
rebuildManagedSectionsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py'
  - '{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py'
---

<!-- Config: communicate in {communication_language}. Render the warning and gate prompt in {document_output_language}. -->

# Snippet Root Prefix Mismatch — Pre-flight Probe

## Purpose

Catch the authoring-repo case before step 4 silently rewrites root paths. In an authoring repo, skills typically live under a single shared directory (`skills/`) that does not match any per-IDE `skill_root` (`.claude/skills/`, `.cursor/skills/`, etc.). Without this probe, step 4's root-rewrite algorithm would replace the on-disk prefix with an IDE-mapped one that the snippet files do not actually reside under.

Loaded by `load-skill.md` §1b after `target_context_files` is resolved and `snippet_skill_root_override` is confirmed unset.

## Inputs

- `target_context_files[0].skill_root` — the reference IDE-mapped skill root (used because step 3 §2.7 picks this same entry for snippet generation when no override is set)
- `{skills_output_folder}` — for manifest-driven candidate enumeration
- Current skill's snippet path (resolved via manifest / `active` symlink / flat path per `knowledge/version-paths.md`)
- `{headless_mode}` — boolean flag from workflow context

## Probe Algorithm

1. Collect candidate snippet paths (manifest-driven orchestration — stays in-prompt):
   - Read `{skills_output_folder}/.export-manifest.json` if it exists. For each skill in `exports` with a resolvable `active_version`, add `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`.
   - Also include the current skill's snippet if present.
2. **Read the prefixes and compare via the helper** — reading each snippet's first line, parsing/stripping the `root:` prefix, collecting the unique set, and comparing against the reference is deterministic prefix arithmetic with one correct answer per input. Resolve `{rebuildManagedSectionsHelper}` from `{rebuildManagedSectionsProbeOrder}` (frontmatter — first existing path wins; if no candidate exists, skip the probe and continue to §2 without a warning rather than blocking export on a missing dev-only helper), then run:

   ```bash
   python3 {rebuildManagedSectionsHelper} root-probe {candidate-snippet-1} {candidate-snippet-2} … --reference-root {target_context_files[0].skill_root}
   ```

   Pass every candidate snippet path from step 1 as a positional argument and the reference `skill_root` as `--reference-root`. The helper reads each snippet that exists, parses its first-line `root:` value, strips the trailing `{skill-name}/` (recovered from the row's own `[skill-name v...]` header) to extract the prefix, and returns:

   ```json
   {"status": "ok", "reference_root": "…", "observed_prefixes": ["…"], "mismatch": true}
   ```

   Set `observed_prefixes = result["observed_prefixes"]` (already unique and sorted; missing or root-less snippets contribute nothing). `result["mismatch"]` is `true` when any observed prefix differs from the reference `skill_root` — the trigger for the Mismatch Gate below.

## Mismatch Gate

**If `result["mismatch"]` is `true`** (some value in `observed_prefixes` does not match the reference `skill_root`):

Emit a single warning (once, not per snippet) and present resolution options before continuing to §2:

> **Snippet root prefix mismatch detected.**
> Existing snippets use: `{observed_prefixes}`
> IDE-mapped skill_root:  `{target_context_files[0].skill_root}`
>
> This usually means you are in an authoring repo where skills live under a single shared directory. Options:
>
> - **(a) Set override** — add `snippet_skill_root_override: {observed_prefix}` to `config.yaml`. Snippets keep their on-disk prefix; the managed section references the real location.
> - **(b) Proceed with IDE mapping** — step 4 will rewrite every snippet's root path to the IDE's skill_root. Use this only if the IDE's skill directory actually contains the skill files.
> - **(c) Cancel** — abort export and investigate.
> - **(d) Use observed prefix for this run only** — set the effective snippet root to the single observed on-disk prefix for this export run, without writing to `config.yaml`. The managed section references the real on-disk location. (Only offered when exactly one prefix was observed.)
>
> If multiple distinct prefixes were observed, the snippets disagree with each other — investigate before choosing (a) or (d).

Wait for user choice.

**Headless default:** when `{headless_mode}`, default to **(b) Proceed with IDE mapping** and log the observed prefix(es) so the mismatch is visible in run logs (not silent).

## Choice handling

### (a) Set override

Halt and instruct the user to update `config.yaml` with `snippet_skill_root_override: {observed_prefix}`, then re-run export. Exit code 6, `halt_reason: "user-cancelled"` (configuration change is out-of-band — workflow does not edit config.yaml on the user's behalf).

### (b) Proceed with IDE mapping

Continue to §2. Step 4's root-rewrite algorithm will rewrite every snippet's prefix to the reference `skill_root`. The user is accepting that the IDE's skill directory contains the actual files; if it does not, the resulting managed section will reference paths that don't resolve.

### (c) Cancel

HALT. Exit code 6, `halt_reason: "user-cancelled"`. No files written.

### (d) Use observed prefix for this run only

**Only available when `observed_prefixes` contains exactly one value.** Set the effective snippet root for this run to that single observed prefix — do NOT mutate `config.yaml`. Step 4's root-rewrite algorithm uses this value as the reference instead of `target_context_files[0].skill_root`, so snippets keep their on-disk prefix and the managed section resolves to the real location. Print a one-line hint: "Persist `snippet_skill_root_override: {observed_prefix}` in config.yaml to skip this prompt on future exports." Continue to §2.

## No-mismatch fast path

**If all observed prefixes match the reference `skill_root` (or no existing snippets were found):** no warning, no gate. Return control to §1b and proceed silently to §2.
