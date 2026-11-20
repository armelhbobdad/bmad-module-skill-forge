---
created: "2026-11-19 23:19"
session: "413c0d2d-59a9-403f-82a2-819c50fabe29"
---

# Timing-budget test failures under parallel full-suite load

`test/test-skf-locate-export-segments.py::test_many_owners_in_one_block_finish_quickly` asserts that 300 owners resolve in under 5 seconds of `time.perf_counter()`, and under heavy load it fails the pre-commit hook with `assert (255129.926958906 - 255123.221770848) < 5` (about 6.7 s). On 2026-11-19 it failed three link commits while eight full `npm test` runs and another project's test runner shared the machine (load average 19), then passed when run alone and in the same commits retried unchanged. Before treating that failure as a code break, rerun it alone with `UV_PYTHON=3.11 uv run --with pytest --with pyyaml --with jsonschema --with ast-grep-cli==0.45.3 pytest test/test-skf-locate-export-segments.py -k finish_quickly`, then retry the commit: the failed hook leaves the files staged ([A failed commit leaves its files staged for the next commit](failed-commit-leaves-files-staged.md)). It is the same kind of load failure as [test:cli Suite 14 failures under parallel quality gates](test-cli-suite-14-failures-under-parallel-quality-gates.md), so stagger full-suite runs when several lanes commit at once.
