---
created: "2026-11-01 20:36"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# install-smoke.json record clobbered by a re-dispatch

`.github/workflows/install-smoke.yaml` is `workflow_dispatch` only, and its `record` job ends with `gh release upload "v${TESTED}" install-smoke.json --clobber`, so dispatching it again for a version that already has a record replaces the original post-publish record on the GitHub Release `v<ver>` while that Release is not immutable. A re-dispatch is still the only way to exercise a Dependabot bump of `actions/upload-artifact` or `actions/download-artifact`, since only this workflow uses them and PR CI never runs it. Back up the record first with `gh release download v<ver> -p install-smoke.json -D <dir>`, then restore it with `gh release upload v<ver> <file> --clobber` if the original should stay; the user's pick was "Back up, then run". On 2026-11-01 the v4.0.0 record from the 2026-10-15 run was backed up this way and replaced by run 41329503262, whose record the Release still holds.
