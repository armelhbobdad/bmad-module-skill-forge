---
created: "2026-06-01 20:08"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14084, 14085]
---

# Non-GitHub sources lose doc discovery and pins

GitLab, Bitbucket and self-hosted git URLs clone fine (`src/skf-create-skill/references/source-resolution-protocols.md` is host-agnostic and `src/skf-analyze-source/references/step-auto-scope.md:51` routes them to standard auto-scope), but both `src/shared/scripts/skf-validate-pins.py:343-350` and `skf-detect-docs.py:628-632` match `_GITHUB_URL_RE` and exit 2 with `{"error": "Not a GitHub URL: ...", "code": "INVALID_URL"}` for anything else. Per `step-auto-scope.md` §0b a non-GitHub URL with `--pin` HARD HALTs with `halt_reason: "resolution-failure"`, an unpinned one silently continues without pinning, and `src/skf-create-skill/references/step-doc-sources.md:63` records only `"Doc sources: detection partial — skf-detect-docs.py error (exit 2)"`, so such repos compile without doc discovery or enforced pins and no clear warning. Nothing in `docs/` or `docs/troubleshooting.md` states this limitation and no GitHub issue tracks it (it was carried informally as "Move #2" and deferred repeatedly).
