# Tessl Review Collect

Step 6 (`validate.md`) §6b loads this file when `submit` returned `pending` or `reviewed`, or printed no JSON. The keys it names are step 6's frontmatter keys, and a bare § names a section of step 6.

## Collect the Review

A review takes Tessl about two minutes, so no call waits for all of it. When the review is on, `submit` sends a copy of the skill to Tessl and returns `pending` with Tessl's run id as soon as Tessl accepts it; when it is off or cannot run, `submit` returns that result instead. While `{tessl_status}` is `pending`, collect the review, at most six times, and add `--final` to the sixth call, which turns a review still running into `timeout`:

```bash
uv run {tesslReviewHelper} collect "{tessl_run_id}" --workspace "{tessl_workspace}" --tessl-version "{tessl_version}"
```

Each call ends within two minutes (a `collect` checks the review for up to 90 seconds, then returns `pending` again or the result), so run each one with your shell tool's default time limit. If the shell tool stops a call before it prints its JSON, or it prints none, make that the last call: set `{tessl_status}` to `failed`, `{tessl_summary}` to `failed: stopped before skf-tessl-review.py reported a result` and `{tessl_warnings}` to the one line `Tessl Review: {tessl_summary}`, keep `{tessl_run_id}` and the other values the calls before it bound, add that line to the Remaining Warnings and continue to §7. Otherwise rely on the JSON, not the exit code, and bind these from the `submit` JSON and again from each `collect` JSON, whose values replace the earlier ones:

- `{tessl_status}` ← `status`
- `{tessl_summary}` ← `summary`
- `{tessl_warnings}` ← `warnings`
- `{tessl_workspace}` ← `workspace`
- `{tessl_version}` ← `tessl_version`
- `{tessl_run_id}` ← `run_id`
- `{tessl_review_score}` ← `review_score`
- `{tessl_description_score}` ← `description_score`
- `{tessl_content_score}` ← `content_score`
- `{tessl_validation}` ← `validation`
- `{tessl_description_suggestions}` ← `description_suggestions`
- `{tessl_content_suggestions}` ← `content_suggestions`

Every key is always present: the scores and `{tessl_validation}` are null and the suggestion lists are empty unless `{tessl_status}` is `reviewed`, and `{tessl_run_id}` is null until Tessl has accepted the review. After the last call, add each entry of `{tessl_warnings}` to the evidence report's Remaining Warnings: a score below 60%, validation errors or, for any status other than `reviewed` and `off`, why the review produced no score. When `{tessl_status}` is `reviewed`, resolve `{tesslReviewRules}` ← first existing path in `{tesslReviewRulesProbeOrder}`, load it, and mark each entry of `{tessl_content_suggestions}` that one of its rules matches with `(not applicable: <rule-id>)`; if neither path exists, list the suggestions unmarked. Apply no suggestion: content suggestions would add text SKF cannot cite to source, and the description comes from the brief. The staged skill holds no `scripts/` or `assets/` until step 7 copies them, so for a brief with scripts or assets, validation findings about missing `scripts/` or `assets/` paths are expected here; test-skill reviews the finished package. §8 records the result.

## Report the Review

After its `- Result: {tessl_summary}` line, the evidence report's `## Tessl Review` section (§8) holds:

- Workspace: {tessl_workspace, or an em dash} · tessl {tessl_version, or an em dash} · Run: {tessl_run_id, or an em dash}
- Validation findings: {each {tessl_validation} finding as `name (status): message`, or "none"}
- Description suggestions (to act on one, edit the description in the brief and re-run create-skill): {each of {tessl_description_suggestions}, or "none"}
- Content suggestions (advisory, not applied): {each of {tessl_content_suggestions} with its `(not applicable: <rule-id>)` mark, or "none"}

When `{tessl_status}` is not `reviewed`, the `## Tessl Review` section holds only its Result line and, when `{tessl_run_id}` is set, its Workspace line, so the report names the run of a review that may still finish.
