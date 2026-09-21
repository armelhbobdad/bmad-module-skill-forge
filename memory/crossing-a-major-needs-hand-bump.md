---
created: "2026-04-21 07:20"
session: "95aee86f-9196-447b-b757-b4a2d1a4c95a"
source: claude-mem
source_table: both
source_ids: [6737, 6940, 6975, 6980]
---

# Crossing a major needs a manual hand-bump

`.github/workflows/release.yaml` bumps `alpha|beta|rc` with `npm version prerelease --no-git-tag-version --preid=<type>`, which only increments inside the current line (2.1.0 → 2.1.1-rc.0, never 3.0.0-rc.0); its `version_bump` choices are alpha|beta|rc|patch|minor|major, and a `premajor-rc` option was rejected as surface bloat for a one-time event. Starting a new major's RC line therefore needs a one-time hand-bump PR on `main` first: `npm version X.0.0-rc.0 --no-git-tag-version`, touching only `package.json` and `package-lock.json` (including `packages[""]`) and leaving `.claude-plugin/marketplace.json` and `CHANGELOG.md` alone because the workflow's own steps update them and would race; a normal `version_bump: rc` dispatch then yields X.0.0-rc.1 under `--tag rc`, and a later `major` dispatch strips the suffix (`docs/_internal/RELEASING.md` § Cutting v1.0.0 under --tag latest). This is how 1.0.0-rc.0 was reached (PR #197, "chore(release): pre-RC bump to 1.0.0-rc.0"); the hand-bump procedure itself was removed from RELEASING.md in c0b2b670 and is documented nowhere else. 2.0.0 was cut straight from 1.9.0 with `major`, so an RC line is optional for a new major — but if one is wanted, the hand bump comes first.
