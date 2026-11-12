---
created: "2026-11-03 12:21"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Concurrent pytest runs delete shared tmp_path folders

pytest puts every run without `--basetemp` in a numbered folder under one per-user root, `/tmp/pytest-of-<user>/pytest-N`, shared by every session and project on the machine, so another run's cleanup can delete a folder a suite here is still using. On 2026-11-03 a pre-commit `npm test` failed in files the change never touched, with 12 ERRORs in `test/test-skf-write-skill-brief.py`, `FAILED test/test-skf-source-tree.py::TestAdvance::test_hygiene_restores_ccc_gitignore` and spurious "No such file or directory" errors. Its `pytest-36` folder vanished mid-run while another project's session was creating `pytest-133` to `pytest-135`, which the session put down to pytest pruning the older numbered folders. Neither `.husky/pre-commit` nor `test:python` in `package.json` sets `TMPDIR` or `--basetemp`, and exporting a private root first (`export TMPDIR=/tmp/skf-ship-tmp; mkdir -p "$TMPDIR"`, emptied afterwards) made the retry pass. Give every commit hook, worktree agent and review agent its own TMPDIR, and when a run shows mass ERRORs or "No such file or directory" in unrelated files, check `ps -eo args | grep -E "[p]ytest"` and rerun on a private TMPDIR before debugging the code.
