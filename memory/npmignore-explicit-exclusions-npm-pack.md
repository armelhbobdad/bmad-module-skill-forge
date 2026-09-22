---
created: "2026-03-06 16:24"
session: "16eaf640-7cea-416c-ab4d-6238288a3fd9"
source: claude-mem
source_table: both
source_ids: [511, 5119, 5123]
---

# .npmignore must name every dev-only directory; verify against a clean checkout of the tag

`package.json` has no `files` allow-list and, because `.npmignore` exists, npm ignores `.gitignore` entirely: every tracked or gitignored path not listed in `.npmignore` ships in the tarball. This bit repeatedly: the first cut shipped 1.2 MB / 169 files (website/, build/, tools/, _bmad-output/, temp/, IDE dirs missing); narrowing `*.md` to `/*.md` (root-only, so subdirectory READMEs ship) pulled 44+ `.cursor/commands/*.md` in until `.cursor/`, `.claude/`, `.entire/` and `_bmad/` were listed by name; before v1.0.0 the gitignored `skills/` reports (404 files), `__pycache__`/`*.pyc` and `tools/validate-skills.js`/`validate-file-refs.js` leaked (1.5 MB tarball, 369 KB after). The `npm publish --dry-run` step in `.github/workflows/release.yaml` only catches validation failures, never bloat, so nothing in CI reports a leak.

The v2.2.0 scoping is the worked example of the trap's current shape. Commit `1c0aac99` enabled IWE memory and added 291 tracked notes under `memory/` plus `.iwe/config.toml` and `.iwe/schemas/memory.yaml`; `.npmignore` named neither directory, so the tarball went from 377 files to 670 and would have published every note — session UUIDs, 85 notes quoting the user verbatim, the release pipeline's auth model, inventories of unfixed defects. Caught pre-dispatch and fixed in PR #482 by adding `memory/` and `.iwe/`; the cut then published at exactly 377 files. **npm publishes are immutable**, so a leak caught after the cut is unfixable — this check belongs before dispatch, not after.

Measure by packing **the last tag in a clean `git worktree`** and diffing its path list against `HEAD`, not by eyeballing `npm pack --dry-run` in the working tree: a working-tree pack also picks up untracked local dirt that a CI checkout will never have, so it over-reports and its file count cannot be compared against what the registry actually holds. Packing the `v2.1.0` tag this way reproduces the published figures exactly (377 files / 3,591,214 B), which is what validates the comparison before trusting the delta.

Two corrections to what this note previously claimed, both verified against a clean pack of the tag: v2.1.0 shipped **377 files / 3.59 MB**, not "379 files, 1.1 MB"; and `.iwe/` did **not** ship at v2.1.0 — it did not become tracked until `1c0aac99`, after that release. What the note got right and still holds: `release-audits/` and `docs/_internal/{RELEASING,STABILITY}.md` were shipping at v2.1.0 and still ship at v2.2.0. A separate long-standing gap found in the same audit: `.npmignore` excludes `tools/validate-doc-links.js` (singular) while `tools/validate-docs-links.js` (plural) and `tools/validate-docs-drift.js` ship — all three files coexist, which is why the slip survived. Both are tracked in issue #487, not fixed.
