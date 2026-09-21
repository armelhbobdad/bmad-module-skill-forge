---
created: "2026-04-21 13:05"
session: "9713e66f-7f75-4067-b7c5-b6281fa6587a"
source: claude-mem
source_table: observations
source_ids: [6777]
---

# package.json repository.url is bound to npm provenance

`package.json` `repository.url` is `git+https://github.com/armelhbobdad/bmad-module-skill-forge.git` and must keep pointing at the real GitHub repository. `.github/workflows/release.yaml` publishes through npm OIDC trusted publishing with an auto-attached SLSA provenance attestation, and npm checks the attested source repository against `repository.url` at publish time, refusing to publish on a mismatch — so editing or dropping the field (for example after a repo rename or transfer, or a metadata cleanup) breaks the release even when the Trusted Publisher binding described in `docs/_internal/RELEASING.md` § npm Trusted Publisher is intact. RELEASING.md lists the four npm-side binding fields but not this package.json coupling.
