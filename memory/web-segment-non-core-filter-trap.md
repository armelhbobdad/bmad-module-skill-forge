---
created: "2026-06-02 21:09"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14415, 14425, 14426]
---

# Ambiguous web/site segments break shape-detect non-core filter

`_NON_CORE_PATH_SEGMENTS` in `src/shared/scripts/skf-shape-detect.py` (line 183) marks monorepo members under docs/tooling directories as non-core so they do not contribute `reference-app` signals. Adding `web` or `site` to that set (to catch `website/`-style directories) also marks genuine app packages such as `apps/web/package.json` non-core, so a monorepo whose only app runtime-depends on `next` classifies as `unknown` instead of `reference-app`; `test_genuine_monorepo_app_member_still_reference_app` (`test/test-skf-shape-detect.py:1323`) fails with exactly this. Both segments were removed during the #421 fix (commit a9b4682b) and the more specific `website`, `websites`, `www` stayed. Only add a segment that is unambiguous as a directory name; if it can also name a product package, use `_NON_CORE_NAME_FRAGMENTS` or a narrower check instead.
