---
created: "2026-10-12 13:14"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# PYTEST_ADDOPTS -q failures in test-skf-conftest.py

`test/test-skf-conftest.py` starts child `sys.executable -m pytest -q` runs (lines 153 and 202) with an env copied from the parent's `os.environ`, then asserts their summary line: `"2 passed"` and `"4 passed" in proc.stdout`. A `-q` in `PYTEST_ADDOPTS` stacks with that into `-qq`, pytest drops the final summary line, and those two tests fail although nothing is wrong. `npm run quality` failed exactly this way on 2026-10-12 and again on 2026-10-13; without the extra `-q` the file passes 8 of 8. Keep verbosity flags out of `PYTEST_ADDOPTS` (the `-o tmp_path_retention_policy=failed -o tmp_path_retention_count=1` options are safe there), and when one is set, read those two failures as an environment problem, not a regression.
