---
created: "2026-04-25 05:18"
session: "54440a56-2192-43ea-a4b6-c161b345b4cd"
source: claude-mem
source_table: observations
source_ids: [7512, 7513, 7523, 7524]
---

# Literal `${{ }}` inside a run block breaks release.yaml parsing

GitHub Actions scans the text of every `run:` block for `${{` and evaluates what follows, even inside a shell comment, so a literal empty pair `${{ }}` makes GitHub reject the whole workflow: `gh workflow run release.yaml -f version_bump=...` returns HTTP 422 `failed to parse workflow: An expression was expected` (reported at the `run: |` line, not the offending comment), and every push-triggered run shows an empty jobs list. `python -c 'yaml.safe_load'` still passes, and nothing in `.github/workflows/quality.yaml` parses workflow files, so the regression sat latent on `main` from PR #226 through five failed push runs until the next release attempt (fixed in commit 3458d6af, PR #240, by describing interpolation in prose). Never write `${{` in comments or prose inside a `run:` block of any workflow; describe expression interpolation in words. A 422 on dispatch is a parse error, not a permissions problem.
