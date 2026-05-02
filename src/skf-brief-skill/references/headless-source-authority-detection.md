# Headless Source-Authority Detection

Loaded by step-01 §8 only when **all three** preconditions hold:

1. `{headless_mode}` is true
2. `source_authority` is absent from the validator's `normalized` output (the validator intentionally leaves it absent so detection can run here — when it was supplied in args, the supplied value wins and detection does not run)
3. `source_type=source` AND `target_repo` is a GitHub URL

When any precondition is unmet, skip this entire procedure: docs-only forces `community` in §3.2; local-path targets default to `community` directly; non-GitHub source URLs are not classifiable from `gh api user` and also default to `community`.

## Procedure

Probe the operator's GitHub login:

```bash
gh api user --jq .login
```

Compare the result to the `owner` segment of `target_repo` (URL pattern `https://github.com/<owner>/<repo>`) — **lower-case both values before comparing**. GitHub owner matching is case-insensitive but the API preserves case in responses, so a literal-string comparison would miss the match.

| Outcome | Set | Rationale |
|---------|-----|-----------|
| login matches owner (case-insensitive) | `source_authority: "official"` | The operator is the repo's GitHub owner |
| login does not match | `source_authority: "community"` | The operator is a downstream consumer |
| `gh api user` errors (unauthenticated, network failure, missing binary) | `source_authority: "community"` (fallback) | Log `"warn: source-authority detection skipped — gh api user failed"` |
| Local-path target | `source_authority: "community"` (no probe) | Comparison does not apply |
