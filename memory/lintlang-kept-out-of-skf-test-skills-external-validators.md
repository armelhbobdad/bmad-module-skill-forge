---
created: "2026-09-28 11:14"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# LintLang kept out of skf-test-skill's external validators

LintLang runs only as the `src/` CI gate: `npm run lint:instructions` (`uvx lintlang@0.8.2 scan src --fail-on fail`) and the `lintlang` job in `.github/workflows/quality.yaml`. On 2026-09-28 the maintainer accepted the recommendation not to add it as a third optional validator beside skill-check and Tessl Review in `src/skf-test-skill/references/external-validators.md` ("let's follow your genuine recommendations"), since lintlang 0.8.0 found nothing on 13 SKF-compiled skills. Its 0-100 score measures how much of a file the tool understood, not quality (every low-confidence skill scored 78, every high-confidence one 92 to 94.7), so it must never be averaged into the external score that `src/skf-test-skill/scripts/combine-external-scores.py` computes. Also declined as noise that `tools/validate-skills.js` and the husky hooks already cover: scanning `.` or `docs/` (0.8.0 read docs pages' `description:` frontmatter as skill descriptions, upstream hermes-labs-ai/lintlang#143), its Claude Code per-edit hook, and a pre-commit hook. Revisit only if a bad compiled skill ships that lintlang would have caught.
