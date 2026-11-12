---
created: "2026-10-04 20:52"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# npm registry 404s in the minutes after a publish

The npm registry lags a publish by minutes at two stages, and both 404s look like a failure scenario in `docs/_internal/RELEASING.md`. On the 3.0.0 cut (release run 37216479630, 2026-10-04), with `Publish to npm via OIDC trusted publishing` green and the tag pushed, `npm view bmad-module-skill-forge@3.0.0` failed with `npm error 404 No match found for version 3.0.0` for a few minutes, even with `Cache-Control: no-cache`. That matches Scenario D's trigger (tag exists but npm publish failed), so read the publish step's log and keep polling, and treat only a 404 that persists after a failed publish step as Scenario D. On the 9.0.0 cut (2026-11-08), `latest` already said 9.0.0 while `https://registry.npmjs.org/bmad-module-skill-forge/-/bmad-module-skill-forge-<v>.tgz` still returned `HTTP/2 404`, so `install-smoke.yaml` failed on ubuntu, windows and macos with E404. Poll `curl -s -o /dev/null -w '%{http_code}' <tgz url>` until 200 before `gh workflow run install-smoke.yaml --ref main -f version=<v>`. When a smoke failure's only error is E404 on the .tgz, rerun it (`gh release upload --clobber` replaces `install-smoke.json` on the Release) instead of following § After the publish into Scenario B (deprecate and ship forward).
