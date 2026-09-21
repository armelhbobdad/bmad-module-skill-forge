---
created: "2026-04-21 13:23"
session: "9713e66f-7f75-4067-b7c5-b6281fa6587a"
source: claude-mem
source_table: both
source_ids: [6802, 6804, 6835]
---

# Dry-run --tag parity for prerelease publishes

`npm publish --dry-run` of a prerelease fails with `You must specify a tag using --tag when publishing a prerelease version` — the first alpha cut (0.10.1-alpha.0) died at the "Pre-publish dry-run" step of `.github/workflows/release.yaml` for exactly this, before any tag was pushed. The step now derives the dist-tag (alpha/beta/rc/latest) from the version string and runs `npm publish --dry-run --tag "$TAG"`, mirroring the real "Publish to npm via OIDC trusted publishing" step (commit de2334b). Keep the two steps' tag logic in parity: the dry-run step carries no comment explaining the `--tag`, and dropping it breaks every prerelease cut.
