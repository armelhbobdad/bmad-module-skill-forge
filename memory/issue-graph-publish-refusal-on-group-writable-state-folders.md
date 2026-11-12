---
created: "2026-11-09 11:56"
session: "77252030-8c80-4285-b88e-c15f43930eb7"
---

# issue-graph publish refusal on group-writable state folders

`issue-graph query github:<owner>/bmad-module-skill-forge --json --no-open`, the external CLI used to triage this repository's issues, returned `{"schemaVersion":1,"error":{"code":"RUNTIME_ERROR","message":"refusing to publish under a directory other accounts can modify: <home>/.issue-graph"}}` on 2026-11-09. The cause is this machine's umask `0002`, which leaves `~/.issue-graph` and each per-run folder issue-graph creates in it (`<owner>-bmad-module-skill-forge-<issue numbers>`) at mode 775. `chmod go-w ~/.issue-graph ~/.issue-graph/*-bmad-module-skill-forge-*` fixed it and the clustered view published. The parent is 755 now, but the per-run folder created on 2026-11-11 is 775 again, so rerun that chmod whenever the error comes back rather than debugging issue-graph itself.
