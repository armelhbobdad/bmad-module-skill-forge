---
created: "2026-04-20 21:32"
session: "10a74550-bf17-4196-bd75-0cb38ce14694"
source: claude-mem
source_table: observations
source_ids: [6647, 6682, 6728]
---

# conventional-changelog-cli kept despite deprecation warning

`conventional-changelog-cli@^5.0.0` is a devDependency on purpose although `package-lock.json` records `"deprecated": "This package is no longer maintained. Please use the conventional-changelog package instead."` and npm prints that warning on every install. The `conventional-changelog` package and git-cliff were weighed and rejected because the seeded CHANGELOG.md and every `release.yaml` cut since use this CLI's `conventionalcommits` preset heading shape (`## [X.Y.Z](compare-url) (YYYY-MM-DD)`); switching tools would mix heading shapes across versions. `quality.yaml` smoke-tests `npx --no-install conventional-changelog-cli --help` on Windows to catch bin-resolution breakage early. Treat the deprecation notice as expected, not a regression; a migration would need a re-seed of CHANGELOG.md and a matching change to the "Restore CHANGELOG preamble" awk step and the bogus-ref grep in release.yaml.
