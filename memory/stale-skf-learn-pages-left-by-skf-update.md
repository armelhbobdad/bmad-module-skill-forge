---
created: "2026-10-04 22:02"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Stale _skf-learn pages left by skf update

`Installer.copyLearningMaterial` in `tools/cli/lib/installer.js` copies the package's `docs/` over `_skf-learn/` with `fs.copy`, filtering only `404*` files and never removing what is already there. `npx bmad-module-skill-forge update` (`tools/cli/commands/update.js`) runs the same `installer.install` path, so a page a newer SKF stopped shipping stays in the consumer project. On 2026-10-04, updating oh-my-skills' `forge` branch from SKF 1.0.0 to 3.0.0 left `_skf-learn/RELEASING.md` and `_skf-learn/STABILITY.md`, which commit 784921c4 moved to `docs/_internal/`. After updating a consumer repo, diff `_skf-learn/` against the installed package's `docs/` (the npx copy under `~/.npm/_npx/`) and `git rm` the leftovers in the update commit. A real fix would prune `_skf-learn/` before copying.
