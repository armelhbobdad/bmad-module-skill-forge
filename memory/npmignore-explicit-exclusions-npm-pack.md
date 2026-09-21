---
created: "2026-03-06 16:24"
session: "16eaf640-7cea-416c-ab4d-6238288a3fd9"
source: claude-mem
source_table: both
source_ids: [511, 5119, 5123]
---

# .npmignore must name every dev-only directory; verify with npm pack --dry-run

`package.json` has no `files` allow-list and, because `.npmignore` exists, npm ignores `.gitignore` entirely: every tracked or gitignored path not listed in `.npmignore` ships in the tarball. This bit repeatedly: the first cut shipped 1.2 MB / 169 files (website/, build/, tools/, _bmad-output/, temp/, IDE dirs missing); narrowing `*.md` to `/*.md` (root-only, so subdirectory READMEs ship) pulled 44+ `.cursor/commands/*.md` in until `.cursor/`, `.claude/`, `.entire/` and `_bmad/` were listed by name; before v1.0.0 the gitignored `skills/` reports (404 files), `__pycache__`/`*.pyc` and `tools/validate-skills.js`/`validate-file-refs.js` leaked (1.5 MB tarball, 369 KB after). At v2.1.0 `npm pack --dry-run` still shows the untracked `.iwe/` directory, `release-audits/` and `docs/_internal/{RELEASING,STABILITY}.md` in the tarball (379 files, 1.1 MB), and the `npm publish --dry-run` step in `.github/workflows/release.yaml` only catches validation failures, not bloat. Run `npm pack --dry-run` before every release and add any new dev-only, gitignored or IDE directory to `.npmignore` by name.
