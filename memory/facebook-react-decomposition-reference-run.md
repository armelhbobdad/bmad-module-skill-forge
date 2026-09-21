---
created: "2026-06-03 10:20"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: observations
source_ids: [14495, 14529, 14530]
---

# facebook/react as the decomposition reference run

facebook/react (React 19.2.7, checked 2026-06) is the live end-to-end check for the §3a/§3b decomposition path in `src/skf-analyze-source/references/step-auto-scope.md`: `skf-shape-detect.py` should classify it `library-API` at ~0.9 confidence with ~109 packages and 129 exports, §3a fires (`package_count > 3`), §3b merges into one `full-library` skill scoped to react + react-dom, and the facet-coverage guard lists react-server-dom-*, the specialized renderers (react-art/native/test/noop), reconciler/scheduler internals, devtools, eslint-plugin-react-hooks, react-refresh and the compiler as excluded facets in `scope.notes`. Before PRs #419/#422 (manifest discovery) and #424 (shape detection) it was misclassified as `reference-app` 0.85 with only 38 packages found — the "react 38 packages" figure still quoted in §3b's prose is that pre-fix count, not a target. Seeing 38 packages or a reference-app verdict on React again means workspace discovery or the non-core-member gating in `src/shared/scripts/skf-shape-detect.py` regressed; no fixture in `test/test-skf-shape-detect.py` encodes this real-repo benchmark.
