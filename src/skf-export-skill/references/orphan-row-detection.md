---
# Static reference loaded by update-context.md §4c.1 only when
# `orphan_managed_rows` is non-empty (i.e. the cheap pre-check in
# §4c.1 found `[skill-name v...]` entries in the prior managed
# section that are absent from the manifest-driven exported skill
# set built in §4b). The reference carries the (a)/(b)/(c) gate
# protocol, headless default, deviations[] contract, and §6
# result-contract integration; the trigger detection itself stays
# inline in §4c.1 so the LLM knows when to invoke this protocol.
---

<!-- Config: communicate in {communication_language}. Render the orphan list and gate prompt in {document_output_language}. -->

# Orphan Managed-Section Rows — Gate Protocol

## Purpose

Handle the (a) Drop / (b) Preserve verbatim / (c) Cancel gate when the prior managed section in the first target context file contains `[skill-name v...]` rows for skills that are not in the manifest-driven exported skill set — typically externally-installed skills authored in a different repo and dropped into `{skills_output_folder}` without going through export-skill.

Strict ADR-K would silently drop such rows, but the user's managed section is load-bearing — silent removal of an installed skill is a regression. The convention captured in `skills/export-skill-result-latest.json` deviations is to make this an explicit operator (or `{headless_mode}`) choice.

## Inputs

- `orphan_managed_rows` — list of `{skill_name, version, snippet_text}` entries built by §4c.1's pre-check (each `snippet_text` is the original snippet line(s) captured verbatim from the prior section, so they can be re-emitted unchanged if (b) is chosen)
- `target_context_files[0].context_file` — the file the orphans were detected in (used in the gate prompt for traceability)
- `{headless_mode}` — boolean flag from workflow context

## Gate Protocol

Emit the gate:

> **Managed-section rows present but absent from manifest:**
>
> {list each as `- {skill_name} v{version}`}
>
> These skills appear in the existing managed section in `{first-context-file}` but no entry exists in `.export-manifest.json` and no source draft exists under `{skills_output_folder}/{skill_name}/`. They were likely installed from a different repo and never run through export-skill in this project. Options:
>
> - **(a) Drop** — remove these rows from the rebuilt managed section (strict ADR-K behavior). The skills' on-disk files are not touched, but they will no longer appear in any context file's managed index.
> - **(b) Preserve verbatim** — copy each orphan's existing snippet line(s) into the rebuilt managed section unchanged. Records `deviations[].kind = "preserve_external_skills"` with the affected skill names and versions in the result contract for audit.
> - **(c) Cancel** — abort export. Run export-skill against each external skill (or remove the orphan rows from the context file manually) before re-running.

Wait for user choice.

**Headless default** (when `{headless_mode}`): auto-select **(b) Preserve verbatim**, with the same `deviations[]` entry. Emit a loud log line:

> `headless: {N} managed-section rows had no manifest entry; preserving verbatim with deviations[].kind = preserve_external_skills. Run export-skill against each to migrate them into the manifest.`

Silent drop under automation would regress the user's managed section without consent; cancel under automation would block the whole export over an externally-installed skill the user did not author. Preservation matches the prior-attentive-operator convention.

## Choice handling

### (a) Drop

Do not include any orphan rows in the rebuilt section. Record:

```
orphans_dropped = [{skill_name, version}, …]
```

in workflow context for the §6 result contract.

### (b) Preserve verbatim

Append each captured `snippet_text` to the assembled section after the manifest-driven entries, preserving alphabetical order in the merged list (sort the combined set of `manifest-driven` + `orphan` snippets by `skill_name`).

Append the following entry to the `deviations[]` array in the §6 result contract:

```json
{
  "kind": "preserve_external_skills",
  "skills": [{"name": "...", "version": "..."}, …],
  "rationale": "managed-section row exists but no manifest entry / no source draft"
}
```

The same orphans are written to **every** target context file in the §4–§9a loop, so all configured IDEs end up with consistent managed sections.

### (c) Cancel

HALT the workflow:

- Do not rewrite any context file.
- Do not update the manifest.
- Do not produce a result contract.
- Exit code 6, `halt_reason: "user-cancelled"` (matches the §8 Menu cancel semantics).
- In headless mode this branch is never taken (headless default is (b)), so this exit path is interactive-only.

## Downstream contract

After this protocol completes, §4c.1 returns control to §4d with these workflow-context variables populated:

- `orphans_dropped: []` — set when the user chose (a) or stayed empty otherwise
- `deviations[]` — extended with the `preserve_external_skills` entry when the user chose (b)
- The assembled managed section contains the orphan rows verbatim when (b) was chosen, and excludes them when (a) was chosen

## Scope note

This detection runs once per export run (not per target context file) — orphan rows are inherent to the prior state of the first context file and the choice is global. The §B1 multi-file fix (issue #331 — Workstream B1) tracks expanding this to iterate over every entry in `target_context_files`; until then, asymmetric orphans (a row present in `.cursorrules` but not in `CLAUDE.md`, when `target_context_files[0]` is `CLAUDE.md`) are not detected by this protocol.
