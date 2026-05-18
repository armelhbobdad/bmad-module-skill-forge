# Description Guard Protocol

## Overview

External validators (`skill-check check --fix`, `skill-check split-body`, and any future tool that may rewrite SKILL.md frontmatter) occasionally replace, truncate, or otherwise mutate the `description` field — sometimes substituting a generic version, sometimes re-introducing angle-bracket tokens that earlier sanitization removed.

The on-disk description is **authoritative**: it has been compiled (in `skf-create-skill`) or merged (in `skf-update-skill`) with deliberate trigger-optimization. Losing it to a tool's well-meaning rewrite breaks agent discovery quality and can re-introduce the angle-bracket failure mode that breaks tessl on the next run.

Any tool invocation that may touch SKILL.md must run inside the four-phase guard below. Workflows invoke the deterministic phases (1, 3, 4) via `src/shared/scripts/skf-description-guard.py`; the LLM only performs phase 2 (the tool call itself).

## The Four-Phase Guard

### 1. Capture

Before invoking the tool, snapshot the on-disk `description` value:

```bash
uv run {project-root}/src/shared/scripts/skf-description-guard.py \
    capture <skill-md-path>
```

Output JSON:

```json
{
  "description": "the snapshotted value",
  "schema_hash": "sha256:..."
}
```

Stash the `description` value in workflow context as `guarded_description`. Also keep the in-context copy synced with the on-disk pre-call state.

### 2. Execute

Run the tool as specified in its section. The LLM performs this step normally — `skill-check check --fix`, `skill-check split-body`, or whatever is documented in the calling stage.

### 3 + 4. Verify and Restore

After the tool completes, run:

```bash
uv run {project-root}/src/shared/scripts/skf-description-guard.py \
    verify-restore <skill-md-path> \
    --captured-description "{guarded_description}"
```

The script:

1. Re-reads on-disk `description`
2. Compares against `guarded_description` using **token-stream equality** — split each string on whitespace, compare resulting token lists element-by-element
3. If diverged: atomically rewrites the frontmatter `description` field with `guarded_description`

Output JSON:

```json
{
  "diverged": true|false,
  "restored": true|false,
  "diff_kind": "none|whitespace-only|replaced|truncated|deleted",
  "current_description": "what was on disk before any restore"
}
```

If `restored == true`, also update the in-context copy of `description` to match `guarded_description` so subsequent stages do not work from a stale tool-mutated version. Record `description_guard_restored: true` (with the tool name) in workflow context for the evidence report.

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

Skills that run frontmatter compliance checks (e.g. `skf-create-skill validate.md`) should additionally re-validate the restored description against the frontmatter contract after restore — a restored value must still satisfy length limits, forbidden-token rules, and required-field shape. Run:

```bash
uv run {project-root}/src/shared/scripts/skf-validate-frontmatter.py <skill-md-path>
```

If the validator reports failure for the `description` field, flip the Schema row in the evidence report back to `FAIL` and record `description_guard_revalidation: FAIL` with the validator diagnostic. Do not halt — let the failure surface through the normal artifact path so step health-check and the result contract record it.

## Why This Protocol Is Centralized

Previously, each tool invocation in each calling stage carried its own copy of the capture/verify/restore prose. Duplicated defensive logic drifts: a fix in one section did not propagate to the other, and adding a new tool invocation required remembering to copy the pattern. Centralizing the protocol gives every calling stage one place to update when external validator behavior changes.

## Calling Workflows

- `src/skf-create-skill/references/validate.md` — wraps `skill-check check --fix` (§2) and `split-body` (§4). Runs the optional post-restore re-validation.
- `src/skf-update-skill/references/write.md` — wraps `skill-check check --fix` and `skill-check split-body --write` in §7. Does not run post-restore re-validation today; the post-write checks in §1 catch downstream issues.
