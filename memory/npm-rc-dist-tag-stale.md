---
created: "2026-04-24 12:39"
session: "8a676f24-3a63-4136-8093-1bbf2a9a49b0"
source: claude-mem
source_table: session_summaries
source_ids: [2182]
---

# npm rc dist-tag still points at 1.0.0-rc.3

The npm `rc` dist-tag for `bmad-module-skill-forge` has pointed at `1.0.0-rc.3` since the v1.0.0 GA cut on 2026-04-23 and was never moved or removed: at v2.1.0, `npm view bmad-module-skill-forge dist-tags --json` still returns `{alpha: 0.10.1-alpha.0, rc: 1.0.0-rc.3, latest: 2.1.0}`, so `npm install bmad-module-skill-forge@rc` resolves to a pre-GA candidate two majors old. `.github/workflows/release.yaml` (lines 718-721) only writes the dist-tag that matches the version being cut (`alpha`/`beta`/`rc`/`latest`), so nothing moves `rc` until another rc is cut; `release-audits/v1.0.0-launch-audit.md:466` records `rc` UNCHANGED at GA. Whether to `npm dist-tag rm`, re-point it at `latest`, or document it was left open — treat `@rc` as stale, not as a preview channel.
