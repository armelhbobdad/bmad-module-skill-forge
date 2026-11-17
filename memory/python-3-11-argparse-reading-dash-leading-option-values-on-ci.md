---
created: "2026-11-13 04:21"
session: "72e9f28d-d28a-41b5-917c-b01a8cd78569"
---

# Python 3.11 argparse reading dash-leading option values on CI

The `python` jobs of `.github/workflows/quality.yaml` (ubuntu-latest and windows-latest) run Python 3.11, while a local `uv run` may pick 3.14, and before 3.14 argparse reads an option value that starts with `-` and is not a plain negative number, such as `-1:keep`, as another option and exits 2 with its usage line. So `test_a_mark_of_another_form_or_index_is_refused[-1:keep]` passed locally and failed only on CI (#1205), the helper printing no JSON. `_join_mark_values` in `src/skf-test-skill/scripts/gap-ledger.py` joins such values as `--not-applicable=<mark>` before parsing (its docstring says 3.12, but 3.11 to 3.13 all refuse `--mark -1:keep`, checked 2026-11-17). Pass dash-leading values as `--opt=value` and run changed helper tests under `uv run --python 3.11` before pushing.
