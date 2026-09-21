---
created: "2026-06-03 14:12"
session: "8aadba72-75f0-4137-baee-001708b5202b"
source: claude-mem
source_table: observations
source_ids: [14606, 14612, 14628, 14634]
---

# Surfaces to touch when adding an ecosystem manifest

Making `skf-scan-manifests.py` discover a new manifest is not enough: `skf-shape-detect.py` hard-halts with `UNSUPPORTED_MANIFEST` (exit 2) on any basename missing from `_PARSERS`, and `step-auto-scope.md` filters the scanner's output down to that same list before shape detection, so a repo with only the new manifest silently falls back to interactive. Adding an ecosystem (go.mod, then pom.xml/build.gradle/Package.swift each followed this) touches: (1) a `_parse_*` function returning `{ecosystem, name, deps, runtime_deps, has_bin, has_library_structure, export_count}` registered in `_PARSERS` and `path_to_manifest_name` in `src/shared/scripts/skf-shape-detect.py`; (2) the sparse-checkout glob and supported-manifest filter in `src/skf-analyze-source/references/step-auto-scope.md`, plus the supported-manifests list in `step-shape-detect.md`; (3) a manifest-to-language row in `_MANIFEST_RULES` of `src/shared/scripts/skf-detect-language.py`; (4) the always-included root-files list in `src/skf-create-skill/references/source-resolution-protocols.md`; (5) a `TestGoMod`-style class in `test/test-skf-shape-detect.py`. `src/shared/data/language-corpora.json` only needs an entry when the language itself becomes a whole-language reference target. No test ties these lists together, so a missed surface fails silently.
