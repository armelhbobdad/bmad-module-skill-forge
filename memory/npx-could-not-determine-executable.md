---
created: "2026-03-06 17:51"
session: "b146433e-9e7e-4085-8fd0-39f374f5c698"
source: claude-mem
source_table: both
source_ids: [530, 531, 546, 554]
---

# npx 'could not determine executable to run' after publish

The first npm publish of `bmad-module-skill-forge` failed on `npx bmad-module-skill-forge install` with `npm error could not determine executable to run`. Four causes: package.json shipped `"bin": {}` and `"main": ""` (npm silently drops an empty bin at publish time), `.npmignore` excluded the whole `tools/` directory that holds the CLI, the CLI's runtime packages sat in devDependencies, and the wrapper lacked its exec bit. The working layout, modelled on the whiteport-design-studio (bmad-method-wds-expansion) package, is `bin` → `tools/skf-npx-wrapper.js` (chmod +x; re-spawns `tools/cli/skf-cli.js` with the caller's cwd when run from an `_npx`/`.npm` path), `main` → `tools/cli/skf-cli.js`, `.npmignore` naming only `tools/build-docs.js`, `tools/fix-doc-links.js` and `tools/validate-doc-links.js` under tools/, and chalk, commander, figlet, fs-extra, js-yaml and @clack/prompts under `dependencies`. Nothing before publish checks this — `release.yaml`'s `npm publish --dry-run` does not exercise bin, and `install-smoke.yaml` runs `npx … --version` only after publish on manual dispatch — so keep the tools/ CLI files in the tarball and their packages out of devDependencies.
