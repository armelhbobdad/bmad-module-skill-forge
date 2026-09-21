---
created: "2026-05-21 10:41"
session: "c28d21cc-4bc1-470b-80ac-f37b8f270bd6"
source: claude-mem
source_table: observations
source_ids: [10439, 10444, 10451, 10887, 10904, 10915]
---

# Improvement-queue remediation protocol

When the user points at a consumer project's `{forge_data_folder}/improvement-queue/` (the `hc-*.md` health-check findings that installed SKF writes per `src/shared/health-check.md` §5c, each pinned to the SKF version that consumer had installed), first verify every finding against current `src/` with file:line evidence — several are usually already fixed on main — and test an "already fixed" verdict empirically, not by reading: the `replace` `--content is None` guard in `src/shared/scripts/skf-rebuild-managed-sections.py` looked fixed by inspection while empty stdin (`""` is not `None`) still wiped the managed section; the guard is now `content_arg is None or not content_arg.strip()`. Then land the live findings as the minimal set of commits and PRs, one branch and PR per root cause, opened one at a time with the user merging each on GitHub before the next is rebased or opened (see `memory/minimal-commits-prs-multi-item-work` and `memory/sequential-pr-merge-gate`). Review each change for breaking changes and regressions, keep local artefacts (consumer paths, `fp-xxxxxxx` fingerprints, queue filenames) out of commit messages, PR bodies and skill prose (`memory/no-local-artefacts-in-commits`), and use party mode or advanced elicitation only when necessary. User: "some may already fixed so you should check if they are really valide issue. we should end up with the minimal commits and PRs. Review all the changes for any breaking changes, or missing impacts/bugs/regressions and ect... DO NOT HALLUCINATE. Activate party mode and/or advanced elicitation only if it is necessary. The commit and PRs messages should not content local artefacts. We will go PRs by PRs at once."
