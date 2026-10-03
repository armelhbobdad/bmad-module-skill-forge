---
created: "2026-10-03 04:16"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# A skill named after its library cannot be renamed (accepted exception)

Rename Skill rewrites only the slots it owns (the frontmatter and metadata names, the snippet's header and `root:` lines and the provenance map), and `skf-verify-no-trace.py` then refuses any other leftover of the old name. A skill named after its library, as Quick Skill names one (for example `cognee`), keeps that name in its `description`, its `metadata.json` description and its snippet `|api:` or `|gotchas:` lines, so the verifier stops the rename with `verify-failed` (exit 5) and the rollback leaves the old skill intact. This is deliberate: the rewrite makes no meaning call, so every token outside the owned slots blocks the commit (`src/shared/scripts/skf-rewrite-skill-name.py` module docstring, `src/knowledge/version-paths.md`, `docs/troubleshooting.md` "Rename Skill stops with `verify-failed`", pinned by `test/test-skf-verify-no-trace.py` (case `description`) and `test/test-skf-rewrite-skill-name.py`).

The maintainer accepted it on 2026-10-03 as a written exception for the step 5b quality gate: the BMad Builder finding that a library-named skill cannot be renamed (skf-rename-skill determinism-1 in the 2026-10-02-2316-final run, verified real and fail-safe) is listed under `excluded_findings` with this note as its reason, not counted. The recovery is in the `verify-failed` halt message and the troubleshooting entry: edit that line in the old skill, or create the skill again under the new name with Brief Skill and Create Skill.
