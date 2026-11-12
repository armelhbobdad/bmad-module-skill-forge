---
created: "2026-10-09 20:08"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# Lazy-load tests on the _SIBLINGS cache, not sys.modules

The `_sibling()` loaders in `src/shared/scripts/` (`skf-compare-file-hashes.py`, `skf-detect-scripts-assets.py` and eight others) load helpers with `importlib.util.spec_from_file_location`, `module_from_spec` and `exec_module` and cache them in a module-level `_SIBLINGS` dict, never in `sys.modules`. A test asserting that a helper is absent from `sys.modules` therefore passes even when the script loads it eagerly; the #696/#697 review (PR #701) caught lazy-load tests with exactly this blind spot. Reset and assert the module's own cache instead: `monkeypatch.setattr(mod, "_SIBLINGS", {})`, run the code path, then `assert mod._SIBLINGS == {}`. `test_no_brief_loads_no_sibling` in `test/test-skf-compare-file-hashes.py` and `test_the_scope_test_loads_only_with_brief` in `test/test-skf-detect-scripts-assets.py` follow this pattern; write any new lazy-load test the same way.
