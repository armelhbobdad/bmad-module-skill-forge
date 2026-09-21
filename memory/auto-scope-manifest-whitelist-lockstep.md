---
created: "2026-06-01 21:24"
session: "b80a57cb-2940-450e-9ffb-35e6c9e3019d"
source: claude-mem
source_table: both
source_ids: [14142, 14144, 14556, 14557, 14560]
---

# Auto-scope manifest whitelist and shape-detect parsers lockstep

`src/skf-analyze-source/references/step-auto-scope.md` §2 keeps two hand-written lists of manifest types — the sparse-checkout globs (`git -C "$tmp" sparse-checkout set ...`, ~line 186) and the "Supported manifest paths" filter (~line 197) — that must match the `_PARSERS` dict in `src/shared/scripts/skf-shape-detect.py` (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Package.swift`). The §2 filter is load-bearing: `skf-scan-manifests.py` recognises more (`Gemfile`, `composer.json`, `requirements.txt`, `setup.py`, `setup.cfg`, `Pipfile`), and when only unsupported manifests remain the empty filtered list routes to interactive `scan-project.md`, whereas handing one of them to shape-detect dies with `Unsupported manifest type: <name>` (`UNSUPPORTED_MANIFEST`, exit 2 → pipeline HARD HALT exit 3), and an empty `--manifests` with no grammar/tree signals dies with `MISSING_MANIFESTS`. No test cross-checks the markdown lists against `_PARSERS`. Adding an ecosystem therefore means changing all three places in one PR (Go was once half-wired — referenced in §5, filtered out in §2, rejected by shape-detect — until commit 3b3404df); widening the whitelist without a parser turns the graceful interactive fallback into a hard halt.
