# Description Guard Protocol

## Overview

External validators (`skill-check check --fix`, `skill-check split-body`, and any future tool that may rewrite SKILL.md frontmatter) occasionally replace, truncate, or otherwise mutate the `description` field — sometimes substituting a generic version, sometimes re-introducing angle-bracket tokens that earlier sanitization removed.

The on-disk description is **authoritative**: it has been compiled (in `skf-create-skill`) or merged (in `skf-update-skill`) with deliberate trigger-optimization. Losing it to a tool's well-meaning rewrite breaks agent discovery quality and can re-introduce angle brackets that create-skill removed, which the Claude platform does not accept in a skill description (it cannot contain XML tags).

Any tool invocation that may touch SKILL.md must run inside the four-phase guard below. Workflows invoke the deterministic phases (1, 3, 4) via `skf-description-guard.py`, which each calling step resolves as `{descriptionGuardHelper}` from its `descriptionGuardProbeOrder` (installed SKF module path first, src/ dev-checkout fallback); the LLM only performs phase 2 (the tool call itself).

## The Four-Phase Guard

### 1. Capture

Before invoking the tool, snapshot the on-disk `description` value into the run folder:

```bash
uv run {descriptionGuardHelper} \
    capture <skill-md-path> > <run-folder>/description-guard.json
```

The file holds `capture`'s output:

```json
{
  "description": "the snapshotted value",
  "schema_hash": "sha256:..."
}
```

A caller may read the `description` value from the file into workflow context as `guarded_description`, never into a shell string. Also keep the in-context copy synced with the on-disk pre-call state.

### 2. Execute

Run the tool as specified in its section. The LLM performs this step normally — `skill-check check --fix`, `skill-check split-body`, or whatever is documented in the calling stage.

### 3 + 4. Verify and Restore

After the tool completes, run:

```bash
uv run {descriptionGuardHelper} \
    verify-restore <skill-md-path> \
    --captured-file <run-folder>/description-guard.json
```

`--captured-file <path>` reads the snapshot from a JSON file's `description`: `capture`'s output saved in the run folder, or another JSON file whose `description` holds the value (quick-skill re-runs with its `metadata.json`). Every calling step passes the file, so the description never passes through a shell string. An empty or whitespace-only `description` in the file is refused like an empty `--captured-description` (below), and so is a file the helper cannot read or that holds no string `description`.

The alternative, `--captured-description <value>`, is for a caller that holds no file and runs the helper with an argument list, without a shell. A shell string must never carry a description: inside double quotes the shell runs backticks and `$(...)`, expands `$name`, and a `"` ends the argument or drops out of it, so the call breaks, or the guard writes a changed description over one the tool never touched.

The script:

1. Re-reads on-disk `description`
2. Compares it against the snapshot (the `description` in the `--captured-file` file, or `--captured-description`) using **token-stream equality**: split each string on whitespace, compare resulting token lists element-by-element
3. If diverged: atomically rewrites the frontmatter `description` field with the snapshot

Output JSON:

```json
{
  "diverged": true|false,
  "restored": true|false,
  "diff_kind": "none|whitespace-only|replaced|truncated|deleted",
  "current_description": "what was on disk before any restore"
}
```

If `restored == true`, also set the in-context copy of `description` to the snapshot's `description`, read from the file as `guarded_description`, so subsequent stages do not work from a stale tool-mutated version. Record `description_guard_restored: true` (with the tool name and the `diff_kind`) in workflow context for the evidence report.

**Empty snapshot refusal.** The helper exits 1 and leaves the file untouched when the snapshot is empty or whitespace-only: the `description` in `<run-folder>/description-guard.json`, or an empty `--captured-description`. It does the same when it cannot read that file, or the file holds no JSON with a string `description`. There is nothing to restore from: either the snapshot was lost between capture and verify, or the field was already empty before the tool ran. Never retry with the empty value: writing it back would blank the field the guard exists to protect. If the compiled description is still available in context (the in-context SKILL.md copy), write it as `{"description": <that value as a JSON string>}` to the same file with a file write, never `echo`, and re-run `verify-restore` on it once. Otherwise, or when that re-run exits 1 too, record `description_guard_restored: false` and `description_guard_refused: empty-capture` (with the tool name) in workflow context; the calling stage's evidence-report populator renders that as a fired guard (`Restored: false`, the triggering tool, `Original description preserved: false`, and a `Notes` line that names the `empty-capture` refusal) rather than as the clean-run state, whose follow-up fields all hold the template's no-fire dash, and the frontmatter validator surfaces the empty field through the normal artifact path.

## Why Token-Stream Comparison

Token-stream comparison is the documented sweet spot between two failure modes:

- **Looser fuzzy matching** would let a tool swap one word past the guard (e.g., replace "compile" with "build").
- **Naive whitespace-normalized equality** would trip on a tool that collapses `"foo  bar"` → `"foo bar"` (cosmetic whitespace fix), forcing unnecessary restore writes.

Splitting on whitespace and comparing token lists catches replaced words, truncation, deletion, and angle-bracket re-introduction while ignoring trailing newlines, re-wrapped quoted strings, and collapsed inner runs.

## What Counts as Divergence

- **`replaced`** — different content (any word changed)
- **`truncated`** — current tokens are a strict prefix of captured
- **`deleted`** — the field is empty or whitespace-only on disk
- **`whitespace-only`** — token streams match but raw strings differ (**not** divergence; do not restore)
- **`none`** — byte-identical (**not** divergence)

## Post-Restore Re-Validation (Optional)

Skills that run frontmatter compliance checks (e.g. `skf-create-skill validate.md`) should additionally re-validate the restored description against the frontmatter contract after restore — a restored value must still satisfy the length limit and required-field shape. (create-skill also checks the final description for angle brackets, in its validate §6, after every tool has run.) Run the frontmatter validator the calling step resolves (create-skill resolves `{frontmatterValidator}` from its `frontmatterValidatorProbeOrder`):

```bash
uv run {frontmatterValidator} <skill-md-path>
```

If the validator reports failure for the `description` field, flip the Schema row in the evidence report back to `FAIL` and record `description_guard_revalidation: FAIL` with the validator diagnostic. Do not halt — let the failure surface through the normal artifact path so step health-check and the result contract record it.

## Why This Protocol Is Centralized

Previously, each tool invocation in each calling stage carried its own copy of the capture/verify/restore prose. Duplicated defensive logic drifts: a fix in one section did not propagate to the other, and adding a new tool invocation required remembering to copy the pattern. This file is the maintainers' reference for the guard, and no stage loads this file at run time. The rules each calling stage acts on, the restore handling and the empty-snapshot refusal, are also stated in the stage's §0 (quick-skill states them beside its one guarded call): change them there, and keep this file in step.

## Calling Workflows

- `src/skf-create-skill/references/validate.md` — wraps `skill-check check --fix` (§2) and `split-body` (§4). Runs the optional post-restore re-validation.
- `src/skf-update-skill/references/write.md`: wraps `skill-check check --fix` and `skill-check split-body --write` in §7, then re-checks the [MANUAL] blocks. Does not run post-restore re-validation.
- `src/skf-quick-skill/references/write-and-validate.md`: wraps `skill-check check --fix` in §4, which also states the restore and empty-snapshot rules. With no guard helper it runs skill-check without `--fix`. Does not run post-restore re-validation.
