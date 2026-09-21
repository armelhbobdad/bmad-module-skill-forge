---
created: "2026-04-20 19:14"
session: "29472acb-d68a-4d99-97f0-bb4461d415ae"
source: claude-mem
source_table: session_summaries
source_ids: [1962, 1978]
---

# Token in publish env bypasses Trusted Publisher

When a token (`NODE_AUTH_TOKEN`, or an `NPM_TOKEN` picked up from the runner env) is present in the publish step, npm authenticates with it and never consults the Trusted Publisher matcher: OIDC is exercised only when no token is set. A publish from an unregistered workflow therefore still "succeeds", with provenance attributed to that workflow — an audit-trail mismatch rather than the loud 404 ("npm could not match your workflow run") the OIDC path would give. This is why `.github/workflows/release.yaml` sets `NPM_TOKEN: ""` on both the pre-publish dry-run and the publish step (`docs/_internal/RELEASING.md` § npm Trusted Publisher), and why token-free publishing can only be validated with every token absent from the environment. The legacy `publish.yaml` that used `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` was deleted in Story 6.1 and the repo secret in Story 6.3.
