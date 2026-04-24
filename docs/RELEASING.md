---
title: Releasing SKF
description: Maintainer reference for the release pipeline — branch protection, release workflow, and rollback procedures.
---

This document records the configuration that gates releases of `bmad-module-skill-forge`. It exists so a future maintainer (including future-you) can audit, restore, or extend the pipeline without reverse-engineering GitHub settings.

For background on GitHub rulesets vs legacy branch protection, see the [GitHub ruleset docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

## Branch Protection on `main`

`main` is gated by a **GitHub repository ruleset** (not legacy branch protection). The legacy "Settings → Branches → Branch protection rules" surface returns 404 for this repo.

**Ruleset:** `Default` — id `13855503` — applies to `~DEFAULT_BRANCH` (currently `main`) — enforcement `active`.

**Active rules (5):**

| Rule                     | Effect                                                                                                                     |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `deletion`               | Branch cannot be deleted.                                                                                                  |
| `non_fast_forward`       | Force-push blocked.                                                                                                        |
| `pull_request`           | Requires ≥ 1 approving review; `require_code_owner_review: true` (see CODEOWNERS note below); merge/squash/rebase allowed. |
| `code_quality`           | Blocks merge on `severity: errors` from GitHub code-quality checks.                                                        |
| `required_status_checks` | Merge blocked until all seven `quality.yaml` checks pass (names below).                                                    |

**Required status checks (7):** sourced from `.github/workflows/quality.yaml` job keys. Matrix jobs expand to `jobname (matrix-value)`:

- `prettier`
- `eslint`
- `markdownlint`
- `validate (ubuntu-latest)`
- `validate (windows-latest)`
- `python (ubuntu-latest)`
- `python (windows-latest)`

**Coupling with `quality.yaml`:** if that workflow renames a job or changes the `strategy.matrix.os` for `validate` or `python`, the ruleset's `required_status_checks` list must be updated in lock-step — otherwise merges to `main` will either block on a check name that no longer reports, or silently pass without the renamed check. Update both in the same PR.

**`strict_required_status_checks_policy: false`** — PR branches are not forced to be up-to-date with `main` before merging. This avoids constant rebases on a low-traffic repo. Flip to `true` if concurrent merges start producing logical conflicts the checks can't catch.

**CODEOWNERS note:** the `pull_request` rule has `require_code_owner_review: true`, but no `.github/CODEOWNERS` file exists in the repo today. GitHub treats the code-owner requirement as vacuously satisfied when the file is absent, so this setting is currently a no-op — the only active review gate is `required_approving_review_count: 1`. If a CODEOWNERS file is added later, make sure the listed owners can actually approve PRs from other authors. GitHub's universal rule is that a PR author cannot approve their own PR — so a CODEOWNERS file that lists only a solo maintainer would deadlock every PR that maintainer opens (they'd be the sole eligible code-owner reviewer but also the author).

**Bypass actors:** `RepositoryRole` actor_id=5 (Admin), `bypass_mode: pull_request`. Admins can bypass the ruleset **only via a pull request**, never via direct push. This preserves `non_fast_forward` and the required-checks gate for the `github-actions[bot]` account that the future `release.yaml` workflow (Story 3.1) will use to push tags and commits to `main`. **Do not add a bot-specific bypass**; it would defeat the whole purpose of this ruleset.

### Inspect current state

```bash
gh api repos/armelhbobdad/bmad-module-skill-forge/rulesets/13855503
```

### Restore from a saved baseline

A JSON baseline captured before any change can be replayed via:

```bash
# Extract the full set of fields required by a ruleset PUT from a saved baseline.json.
# PUT replaces the resource wholesale — omitting any of these fields either 422s or
# silently resets them server-side. `bypass_actors` is optional (empty array is the
# default) but is included here to preserve the admin-via-PR bypass.
jq '{name, target, enforcement, conditions, rules, bypass_actors}' baseline.json > /tmp/restore.json

gh api --method PUT \
  repos/armelhbobdad/bmad-module-skill-forge/rulesets/13855503 \
  --input /tmp/restore.json
```

The GitHub ruleset API uses `PUT` (not `PATCH`) for updates, and the `rules` array is replaced wholesale — it is not merged server-side. Always fetch current state, modify the in-memory copy, and `PUT` the complete list.

## Release Environment

The publish job is gated by a **GitHub [deployment environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) with a required-reviewer rule** (not by workflow logic). A job declaring `environment: release` pauses until a listed reviewer clicks "Approve and deploy" in the Actions UI.

**Environment:** `release` — id `14347249917` — created 2026-04-20.

| Setting                    | Value                                                                                                                                                                                                                                                    |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `wait_timer`               | `0` (no artificial delay; approval is the only gate)                                                                                                                                                                                                     |
| `prevent_self_review`      | `false` — see rationale below                                                                                                                                                                                                                            |
| `reviewers`                | `armelhbobdad` (user id `132626034`), 1 approver                                                                                                                                                                                                         |
| `deployment_branch_policy` | `custom_branch_policies: true`, list: `main` only                                                                                                                                                                                                        |
| Environment-scoped secrets | `0` (invariant — see "No secret is scoped to this environment" note below)                                                                                                                                                                               |
| Cost                       | `$0` on public-repo tier (environments, required reviewers, and branch policies are [free for public repositories](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#about-environments)) |

**`prevent_self_review: false` — correctness constraint, not a loosened control.** Solo-maintainer setups cannot self-approve when this is `true`, so the gate would deadlock on any maintainer-triggered publish. The value flips to `true` the moment a second reviewer joins — do not leave it loose by inertia.

**No secret is scoped to this environment.** The repo no longer carries an `NPM_TOKEN` secret at any scope (removed in Story 6.3 post-v1.0.0 once OIDC trusted publishing was operationally proven by the v1.0.0 launch). The invariant: the `release` env must have zero environment-scoped secrets, and the repo must have zero `NPM_TOKEN`-shaped secrets at any scope. If a future change scopes any secret to this environment, or if an `NPM_TOKEN` secret is ever re-added at repo scope, re-audit whether the OIDC trusted-publisher path is still in force — the OIDC path SHOULD be self-sufficient and a re-added token is a signal that something has regressed off the canonical path.

**Audit command.** Both halves of the invariant are machine-checkable:

```bash
# Repo-scope: expect 0
gh secret list --repo armelhbobdad/bmad-module-skill-forge | grep -ci npm_token

# Env-scope: expect {"total_count":0,"secrets":[]}
gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release/secrets
```

**Coupling with npm trusted publishing (Story 1.3).** The npm trusted publisher binds on four fields — `organization=armelhbobdad`, `repository=bmad-module-skill-forge`, `workflow filename=release.yaml`, `environment=release`. The environment name above is load-bearing: any rename here must be accompanied by a matching npm-side update in the same change, or the next publish returns 404.

### Inspect current state

```bash
# Environment itself (reviewers, branch-policy shape, prevent_self_review)
gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release

# Allowed deployment branches (expect: one entry, name "main")
gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release/deployment-branch-policies

# Environment-scoped secrets (expect: zero)
gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release/secrets
```

### Restore / re-apply

Two-call pattern — the environment and its branch-policy list are separate resources. Creating the environment alone with `custom_branch_policies: true` leaves the allow-list empty, which rejects every dispatch; the second call is mandatory.

```bash
# (1) Create or update the environment with the required-reviewer gate
gh api --method PUT repos/armelhbobdad/bmad-module-skill-forge/environments/release --input - <<'JSON'
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": [{ "type": "User", "id": 132626034 }],
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
JSON

# (2) Add main to the allowed deployment branches.
#     Returns HTTP 422 ("already_exists") if main is already on the list —
#     safe to ignore on re-apply. To pre-check:
#     gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release/deployment-branch-policies
gh api --method POST repos/armelhbobdad/bmad-module-skill-forge/environments/release/deployment-branch-policies --input - <<'JSON'
{ "name": "main" }
JSON
```

### Temporarily allowing a feature branch

A release workflow that declares `environment: release` will be rejected from any branch not on the allow-list. For legitimate validation cuts from a feature branch (Story 3.2's alpha cut is the canonical case), widen the allow-list for the duration of the test and tighten it back immediately:

```bash
# Allow the feature branch and capture the returned policy id into a shell var.
# Using command substitution + --jq .id avoids the "eyeball the JSON and paste
# the id later" footgun — if the POST succeeds, $POLICY_ID is ready for the revoke.
POLICY_ID=$(gh api --method POST \
  repos/armelhbobdad/bmad-module-skill-forge/environments/release/deployment-branch-policies \
  --input - --jq .id <<'JSON'
{ "name": "feat/my-validation-branch" }
JSON
)
echo "POLICY_ID=$POLICY_ID"  # confirm a numeric id was captured before proceeding

# ... run the validation cut, approve via the reviewer UI, confirm publish ...

# Revoke immediately — the allow-list must return to { main } before leaving the session.
# Quote the expansion so the shell never interprets the id as a redirection token.
gh api --method DELETE \
  "repos/armelhbobdad/bmad-module-skill-forge/environments/release/deployment-branch-policies/$POLICY_ID"
```

Leaving a feature branch on the allow-list is an unguarded hole — any later `workflow_dispatch` from that branch would be able to reach the publish path. Treat the revoke as the last step of the validation, not a follow-up.

## npm Trusted Publisher

The future `release.yaml` workflow (Story 3.1) publishes to npm via **OIDC trusted publishing** — no `NPM_TOKEN` is consulted during the publish step, and every published version carries an auto-attached SLSA Build Level 2 provenance attestation. For this to work, the npm package `bmad-module-skill-forge` has a trusted-publisher entry on npmjs.com that binds on four fields exactly matching what the workflow asserts at run time. A mismatch on any field causes an opaque `404` at publish time — the error ("npm could not match your workflow run") surfaces the failure class but does not name which of the four fields is wrong.

**Registered:** 2026-04-20 by `armelhbobdad`.

| Field             | Value                     |
| ----------------- | ------------------------- |
| Publisher type    | `GitHub Actions`          |
| Organization/user | `armelhbobdad`            |
| Repository        | `bmad-module-skill-forge` |
| Workflow filename | `release.yaml`            |
| Environment       | `release`                 |

**Inspect current state:** visit the [npm package settings for `bmad-module-skill-forge`](https://www.npmjs.com/package/bmad-module-skill-forge) → **Settings** tab → **Trusted Publisher** section (npm UI as of 2026-04-20; if the tab is reorganised later, the section still lives on the package Settings page). Modification requires 2FA re-entry on the maintainer account. No CLI or public API for programmatic inspection of Trusted Publisher state exists as of 2026-04-20 — drift detection is UI-only until npm exposes one.

**Case-sensitive.** All four fields above use the exact lowercase forms shown; npm's matcher is an exact-string comparison. Do not capitalize on re-registration even if GitHub's UI surfaces a display-form with capitals.

**Rename coupling — the four fields are load-bearing.** Renaming OR deleting the `release` GitHub environment (see § Release Environment), renaming or moving `release.yaml` within `.github/workflows/`, or flipping the extension between `.yaml` and `.yml` each require matching updates in the same PR to: (a) the npm-side Trusted Publisher, (b) the Registered table above, and (c) the `## Release Process` enumeration in `README.md` (which names both `release` and the Trusted Publisher). Skipping any of these produces an opaque `404` on the next publish — the error names the failure class, not the specific field.

**Pre-registration inversion.** This entry was registered **before** `release.yaml` was authored (Story 3.1). The first live validator of the full OIDC chain is Story 3.2's alpha cut. If that cut's publish step 404s, open a **three-way comparison**: (1) the npm Settings tab, (2) the workflow YAML's `name` / `on` / `jobs.<id>.environment` lines, and (3) the Registered table above. The table is the ground truth because it captured the values at npm-save time — compare both the npm record and the workflow header against the table, never the workflow against itself (verifying the workflow against its own header will silently confirm a typo).

**`NPM_TOKEN` is gone — OIDC is the only publish credential surface.** The token was removed from repo-level secrets in Story 6.3 (post-v1.0.0, once OIDC trusted publishing was operationally proven by the v1.0.0 launch). SKF's npm publish credential surface is now OIDC-only. Future incidents requiring credential revocation involve npmjs.com's trusted-publisher config, not a repo secret. `release.yaml` authenticates via Trusted Publisher OIDC and continues to set `NPM_TOKEN: ""` explicitly in both the pre-publish dry-run step and the final publish step as defense-in-depth against a stale token being auto-picked-up by npm from the runner env — those literal empty-string assignments are not `secrets.*` reads and stay load-bearing regardless of the secret's presence or absence. Both sites carry a `# DO NOT REMOVE — FR4 defense-in-depth` inline comment so a future cleanup pass does not silently delete them; audit with `grep -c 'NPM_TOKEN: ""' .github/workflows/release.yaml` (expect `2`). If a future OIDC incident forces a last-resort token-based re-publish path, re-adding `NPM_TOKEN` at repo scope is the exception-path, not the default — document the flip in the commit body, file an issue for the OIDC incident class that required it, and remove the token again the moment OIDC is restored.

**Fixing a bad registration.** The npm UI exposes both **Edit** and **Delete** on an existing Trusted Publisher entry (observed 2026-04-20). Prefer edit for a single-field typo; prefer delete-and-re-add if multiple fields are wrong or the edit form ever feels ambiguous. **Pre-Story 3.2**: there is no destructive side effect because no publish is attempted yet, and delete-and-re-add keeps the audit trail cleaner. **Post-Story 3.2**: a publish that fires during the delete-and-re-add window will 404 — gate any delete-and-re-add behind a manual publish freeze (pause any active `release.yaml` runs, confirm no tags are in-flight) before touching the entry.

<!-- Rollback Playbook — added in Story 4.1 -->

## Rollback Playbook

> **NEVER `npm unpublish` v1.0.0.** Once `bmad-module-skill-forge` is published under `--tag latest` at v1.0.0, the version is immutable by policy (NFR6). The default rollback is `npm deprecate` + ship forward. See Scenario C for the narrow 72h / zero-dependents exception — which applies to **pre-v1.0.0 versions only**.

Scenarios A–F are recovery paths for a bad publish; Scenario G is a meta-recovery path for the release workflow itself. Each scenario follows a five-element shape: **Trigger** → **CLI** → **Expected outcome** → **Constraints** → **Verification**. A compact [cross-reference matrix](#cross-reference-matrix) sits at the end of this section for under-pressure triage. All `gh api` examples in this section use name-based lookups (ruleset by `name=="Default"`, environment by literal `release`) so they survive ruleset or environment re-creation.

Placeholder substitutions used throughout:

- `<bad>` — the broken version just published (e.g. `0.10.1`).
- `<previous_good>` — the last known-good version immediately before `<bad>` (e.g. `0.10.0`).
- `<next_version>` — the fix version produced by the next `release.yaml` dispatch (e.g. `0.10.2`).
- `<run-id>` — a GitHub Actions run id visible in the Actions UI and via `gh run list --workflow=release.yaml`.

### Scenario A — "Bad version published to `latest`, no users yet (within ~minutes)"

- **Trigger.** Maintainer notices a defect within minutes of publish; `npm view bmad-module-skill-forge dist-tags` still shows `<bad>` on `latest`; download count is negligible; no dependents have pinned `<bad>` yet.

  > **Note on cache lag.** `npm view … dist-tags` reads through a CDN with multi-second to multi-minute eventual consistency. "Still shows `<bad>` on `latest`" is not an authoritative "no users yet" signal. For freshness, cross-check with `npm view bmad-module-skill-forge@<bad> time --json | jq '. | to_entries | last'`.

- **CLI.**

  ```bash
  # Flip latest back to the last known-good version.
  npm dist-tag add bmad-module-skill-forge@<previous_good> latest

  # Verify the flip landed.
  npm dist-tag ls bmad-module-skill-forge

  # Warn anyone who did install <bad> in the meantime.
  npm deprecate bmad-module-skill-forge@<bad> "Pulled - use <previous_good> instead"

  # Cut the fix forward via the canonical workflow (OIDC publish, SLSA-L2 provenance).
  gh workflow run release.yaml -f version_bump=patch
  ```

- **Expected outcome.** `latest` now resolves to `<previous_good>`; `npm install bmad-module-skill-forge@<bad>` emits a deprecation warning; the subsequent patch cut advances `latest` to `<next_version>` cleanly.
- **Constraints.** Valid only while the blast radius is small. If any downstream has already pinned to `<bad>`, Scenario B applies instead — reverting `latest` won't reach those installs.
- **Verification.**

  ```bash
  npm view bmad-module-skill-forge dist-tags --json
  # expected: {"latest":"<previous_good>", ...}
  # Other dist-tags (e.g. "alpha") may also appear depending on prior releases.
  ```

### Scenario B — "Bad version live for hours/days, users may be installing it"

- **Trigger.** Defect discovered after `<bad>` has held `latest` long enough that download count is non-zero, or dependents may have already pinned.
- **CLI.**

  ```bash
  # Warn immediately — every install of <bad> now prints this string.
  npm deprecate bmad-module-skill-forge@<bad> "Critical bug - use <next_version> instead"

  # Cut the fix forward. release.yaml's dist-tag case-chain auto-updates `latest`
  # for non-prerelease versions, so no manual `dist-tag add` is needed here.
  gh workflow run release.yaml -f version_bump=patch
  ```

- **Expected outcome.** `npm install bmad-module-skill-forge` starts emitting the deprecation warning; the new patch publishes cleanly; `latest` advances to `<next_version>`.
- **Constraints.** **Do NOT** `npm dist-tag add @<previous_good> latest` in this scenario. For post-v1.0.0 releases that is an NFR6 violation (it re-exposes a deprecated version as `latest`); for pre-v1.0.0 it fragments user expectation and hides the fix. Ship forward via patch bump.
- **Verification.**

  ```bash
  # Confirm the deprecation message landed on the registry (no install required —
  # `npm install` would mutate the cwd's package.json/package-lock.json).
  npm view bmad-module-skill-forge@<bad> deprecated
  # expected: the exact deprecation string set above ("Critical bug - use <next_version> instead")
  ```

  NFR3 (rollback frequency <1/quarter post-v1.0.0) is evaluated against the frequency of Scenario B invocations — each trip through Scenario B is an NFR3 data point.

### Scenario C — "Bad version within last 72h, zero downloads, zero dependents"

- **Trigger.** A narrow eligibility window per the [npm unpublish policy](https://docs.npmjs.com/policies/unpublish/): less than 72 hours since publish **AND** zero downloads **AND** zero dependent packages registered on npmjs.com. All three conditions must be true. Compute the 72-hour boundary from the `time.modified` field of `npm view bmad-module-skill-forge@<bad> --json`, NOT from the responder's local clock — npm's policy engine uses its server timestamp and a drift of even a few minutes at the boundary will 422 the unpublish.

  > **Caveat on the "zero downloads" criterion.** npm's downloads API is documented as eventually consistent with up to 24–48h lag post-publish. A version can show "0 downloads" while having been installed by hundreds of CI runs in that window. When in doubt in the first 24–48 hours, treat C as Scenario B.

- **CLI.**

  ```bash
  npm unpublish bmad-module-skill-forge@<bad>
  ```

- **Expected outcome.** The version disappears from `npm view`. **But** the version _number_ is permanently burned — npm rejects any future publish of that same version string forever.

  > **Permanent-burn warning.** The version number is burned. After `npm unpublish bmad-module-skill-forge@0.10.1`, the next `release.yaml` dispatch with `version_bump: patch` on `0.10.0` will produce `0.10.2`, **not** `0.10.1` again. Attempting `npm version 0.10.1 --no-git-tag-version` would drive the workflow's `npm publish` toward an npm-burned version and return `403`. Treat the unpublish as a one-way jump in the version number line, not a true undo.

- **Constraints.** **This scenario does NOT apply to v1.0.0.** Per NFR6, v1.0.0 is never unpublished regardless of eligibility window — use Scenario B instead. Scenario C is a pre-v1.0.0-only path.
- **Verification.**

  ```bash
  npm view bmad-module-skill-forge@<bad> 2>&1
  # expected: npm error 404 No match found for version <bad>
  ```

### Scenario D — "Tag exists but npm publish failed"

- **Trigger.** `release.yaml` pushed the `v*` tag (tag-creation step runs before the npm publish step) and then the publish step failed — OIDC 404, tarball validation error, network drop. `npm view bmad-module-skill-forge@<version>` returns 404; `git tag -l v<version>` shows the tag locally and on origin.
- **CLI.**

  ```bash
  # VERIFY FIRST that npm did NOT publish — a tag-delete after a successful
  # publish would orphan the npm artifact. If this returns a manifest, STOP
  # and go to Scenario E.
  npm view bmad-module-skill-forge@<version> 2>&1

  # Tag-only recovery: clear the tag locally and on origin, then re-dispatch.
  git tag -d v<version>
  git push --delete origin v<version>

  # Re-dispatch with the same bump input — release.yaml will produce a fresh
  # clean tag and successful publish.
  gh workflow run release.yaml -f version_bump=<same-input-as-before>
  ```

- **Expected outcome.** Tag cleared from origin; re-run produces a fresh clean tag plus a successful publish under the next version number.
- **Constraints.** Only safe if publish failed. If npm _did_ publish, use Scenario E — tag-deletion after a successful publish leaves the npm artifact without a matching git ref.
- **Do-NOT clause.** Never re-use the burned `<version>` number. `release.yaml` will produce the next version on redispatch (for example, re-running an `alpha` bump over `0.10.1-alpha.0` produces `0.10.1-alpha.1`, not `0.10.1-alpha.0` again). Forcing the original version back via `npm version <exact> --no-git-tag-version` is out of scope for rollback.
- **Story 3.2 load-bearing context.** The current `release.yaml` pushes the git tag **before** the npm publish step (see the `Create and push tag` job step vs. the `Publish to npm via OIDC trusted publishing` step). This ordering is pre-existing from Story 3.1 and tracked in `_bmad-output/implementation-artifacts/deferred-work.md` under `§ 3-1/3-2 code review "Create and push tag pushes the git tag BEFORE Publish to npm"` as a post-v1.0.0 hardening candidate. Until that lands, Scenario D's tag-delete path **is** the recovery.
- **Verification.**

  ```bash
  # Tag gone on origin.
  gh api repos/armelhbobdad/bmad-module-skill-forge/git/refs/tags/v<version> 2>&1
  # expected: 404 Not Found
  ```

### Scenario E — "npm publish succeeded but GitHub Release / tag push failed"

- **Trigger.** Publish succeeded (`npm view bmad-module-skill-forge@<version>` returns a manifest) but **one of**: tag-push to origin failed (network drop, branch-protection edge case); the `Create GitHub Release` softprops step failed (API rate limit, auth expiry); the `Push commit to main` step was (correctly) skipped but the release artifact diverged from `main`.
- **Premise inversion note.** In the research doc's scenario ordering, publish was assumed to happen before tag push — so publish failure was the likely branch. In the live `release.yaml` the ordering is reversed: the tag push runs **before** the npm publish. That means a publish-succeeded-but-tag-missing window is small, but real — the `Create GitHub Release` and `Push commit to main` steps still run after publish and either can fail independently. This scenario covers the post-publish-tag-or-release-missing recovery path.
- **CLI — tag recovery.**

  ```bash
  # Obtain the commit-sha the workflow used as its HEAD during the publish run
  # (returns the SHA directly; do not grep the run log — the bump-commit echo
  # line does not contain the SHA, only the post-commit confirmation does).
  COMMIT_SHA=$(gh api \
    repos/armelhbobdad/bmad-module-skill-forge/actions/runs/<run-id> \
    --jq .head_sha)

  # Recreate the annotated tag and push.
  git tag -a v<version> "$COMMIT_SHA" -m "Release v<version>"
  git push origin v<version>
  ```

- **CLI — GitHub Release recovery.** The workflow's `Generate release notes`
  step writes to `release_notes.md` inside the runner; that file is **not**
  uploaded as an artifact, so it does not exist outside the run. Either scrape
  the body from the run log first, or use `--generate-notes` to let GitHub
  regenerate from commit subjects.

  ```bash
  # Option A: scrape the notes body from the run log into a local file.
  gh run view <run-id> --log \
    | sed -n '/^## Generate release notes/,/^##[^#]/p' \
    > release_notes.md
  gh release create v<version> \
    --notes-file release_notes.md \
    --title "Skill Forge (SKF) v<version>"

  # Option B: let GitHub regenerate from commit subjects (loses the curated
  # changelog body but always works).
  gh release create v<version> \
    --generate-notes \
    --title "Skill Forge (SKF) v<version>"
  ```

- **Expected outcome.** Tag landed on origin pointing at the correct commit; GitHub Release page reflects the published npm artifact; npm + GitHub + git state are now consistent.
- **Constraints.** **npm state is immutable.** Do NOT try to "clean up" the npm artifact so the release can be re-run from scratch. The npm artifact plus the orphaned post-recovery git state **is** the canonical record — NFR5 (audit-trail completeness) is satisfied by the successful npm publish plus the recovered tag and GitHub Release, not by a clean rerun.
- **Orphaned-commit caveat (Story 3.2 context).** If the run was dispatched from a feature branch and `Push commit to main` was correctly skipped, the `release: bump to v<version>` commit lives only in the workflow run log until the recovered tag above anchors it. This is NFR12-compliant and expected pre-v1.0.0 behavior; the tag is the authoritative pointer. This is exactly the pattern observed in the Story 3.2 alpha cut (`bmad-module-skill-forge@0.10.1-alpha.0`, run `24714953668`, tag `v0.10.1-alpha.0`, orphaned commit `2a57dcbd`).
- **Verification.**

  ```bash
  # Tag resolves.
  gh api repos/armelhbobdad/bmad-module-skill-forge/git/refs/tags/v<version>

  # GitHub Release exists.
  gh release view v<version>

  # npm + GitHub provenance still match.
  npm view bmad-module-skill-forge@<version> --json | jq '.dist.attestations'
  ```

### Scenario F — "Suspected OIDC compromise / unauthorized publish"

- **Trigger (any of).**
  - `npm view bmad-module-skill-forge time` shows a publish with a timestamp no maintainer triggered.
  - `npm audit signatures` on a published tarball reports attestation verification failure.
  - A GitHub Actions run shows reviewer approval that was not given.
  - npm support notifies of suspected compromise.
- **Immediate CLI (within minutes of detection).** Revoke the OIDC trust surface before doing anything else:
  - Visit `https://www.npmjs.com/package/bmad-module-skill-forge` → **Settings** tab → **Trusted Publisher** section → **Delete** the registration.
  - This blocks _all_ future OIDC publishes until re-registered, stopping any further unauthorized use of the OIDC path mid-incident.
- **Audit CLI.**

  ```bash
  # Full publish timeline.
  npm view bmad-module-skill-forge time

  # Per-version provenance shape (script-friendly).
  npm view bmad-module-skill-forge@<suspect> --json \
    | jq '.dist.attestations'
  # expected shape:
  # {
  #   "url": "https://registry.npmjs.org/-/npm/v1/attestations/bmad-module-skill-forge@<suspect>",
  #   "provenance": { "predicateType": "https://slsa.dev/provenance/v1" }
  # }

  # Human-friendly signature-chain check. `npm audit signatures` operates on
  # the cwd's installed dependency tree — running it in an empty dir returns
  # "0 packages have verified attestations", which is a false-clean signal
  # mid-incident. Wrap the install in a throwaway dir, ignore lifecycle
  # scripts (the suspect tarball may be hostile), then audit.
  mkdir -p /tmp/skf-incident-verify && cd /tmp/skf-incident-verify
  npm init -y >/dev/null
  npm install --ignore-scripts bmad-module-skill-forge@<suspect>
  npm audit signatures
  # expected: "X packages have verified attestations" with attestation count >= 1
  ```

  If `dist.attestations` is missing or the `url` field points somewhere unexpected, the publish bypassed the OIDC path.

- **Coordination CLI.** If a malicious version was actually published, contact `support@npmjs.com` with the version string, the attestation URL, and the Trusted Publisher registration timestamp; request a manual takedown. npm support can unpublish outside the 72-hour window for security-compromise cases.
- **Lockdown CLI.**

  ```bash
  # Confirm no unexpected secrets were added to the repo.
  gh api repos/armelhbobdad/bmad-module-skill-forge/actions/secrets

  # Confirm the write-access list is unchanged.
  gh api repos/armelhbobdad/bmad-module-skill-forge/collaborators

  # Review all workflows for any pull_request trigger type that could run
  # attacker-controlled code with repo secrets (e.g. `types: [opened]`
  # without a trusted-author gate).
  grep -rn "pull_request:" .github/workflows/
  ```

- **Post-incident reactivation.** After audit completes and root cause is identified and patched, re-register the Trusted Publisher via the npm UI with the four fields matching the table in `## npm Trusted Publisher` above (`organization=armelhbobdad`, `repository=bmad-module-skill-forge`, `workflow filename=release.yaml`, `environment=release`). Re-verify via an alpha cut (dispatch `release.yaml` from a temporarily-allowed feature branch per the `## Release Environment § Temporarily allowing a feature branch` procedure) before any stable release.
- **Pre-v1.0.0 context.** Trusted Publisher was pre-registered on 2026-04-20 (Story 1.3). A compromise discovered pre-v1.0.0 is recoverable via delete-and-re-register with no downstream-consumer blast radius (no stable release users yet). Post-v1.0.0, the incident has downstream blast radius and the `support@npmjs.com` coordination path is load-bearing.
- **Do-NOT clause — `NPM_TOKEN` rotation is not OIDC incident response.** Do NOT rotate `NPM_TOKEN` as a first response. The token is not on the OIDC path; rotating it does nothing to stop an OIDC compromise.
  - If an `NPM_TOKEN` exists at repo scope at the time of an incident (exception-path per § npm Trusted Publisher), revoke it at `https://www.npmjs.com` → **Access Tokens** AND remove it from the repo: `gh secret delete NPM_TOKEN --repo armelhbobdad/bmad-module-skill-forge`. A compromised `NPM_TOKEN` would be a **separate incident class** from OIDC compromise. **Expected outcomes of the delete command under incident pressure** — read the response before escalating: (a) `Secret deleted` = success, token revoked at repo-scope; (b) `could not find secret NPM_TOKEN` (exit 1, 404) = no-op SAFE, the token is already absent per the post-Story-6.3 default and this is the expected normal-operation state, not a broken scope or auth issue; (c) any `401` / `403` / scope-permission error = investigate before retrying, likely a `gh auth` or org-permissions issue unrelated to the token's presence. Story 6.3 removed the token in 2026-04 post-v1.0.0 so outcome (b) is the default; outcome (a) only applies during the exception-path window where a temporary token re-add has already happened. During a window where OIDC is revoked AND an exception-path token is also compromised, there is no valid publish path — the repo enters lockdown until Trusted Publisher is re-registered. Document the flip in the incident post-mortem; do not publish via any stale path.

### Scenario G — "release.yaml disabled, reverted, or missing from main"

- **Trigger.** `release.yaml` is the single-rooted release workflow (Story 3.3 Patch A neutralized the legacy `publish.yaml` `v*` tag trigger). If `release.yaml` is reverted, renamed, moved, or disabled at the repo-settings level (`gh workflow disable release.yaml`) and someone tries to cut a release, **no workflow fires**. Silent no-op until a maintainer checks `npm view` or the Actions UI.
- **Detection.** After any PR that touches `.github/workflows/*` — and before any release attempt — run:

  ```bash
  gh api repos/armelhbobdad/bmad-module-skill-forge/actions/workflows \
    --jq '.workflows[] | select(.name=="Release") | {name, state, path}'
  # expected: {"name":"Release","state":"active","path":".github/workflows/release.yaml"}
  ```

  If `state` is not `active` (the GitHub Actions API reports `disabled_manually` when disabled via the UI or `gh workflow disable`), or no matching workflow is returned at all (file renamed, moved, or deleted), Scenario G applies.

- **Recovery CLI.**

  ```bash
  # Case 1: workflow is disabled but the file is present.
  gh workflow enable release.yaml

  # Case 2: the file is missing or reverted.
  # Revert the offending PR via the normal branch-protection review path.
  # Do NOT hand-edit main — branch protection blocks direct push anyway.
  gh pr view <offending-pr-number>
  # `gh pr revert` opens a NEW revert PR; it does not merge anything itself.
  # Capture the URL it prints, then approve + merge that revert PR through
  # the standard review path before retrying the release.
  gh pr revert <offending-pr-number>
  # After approval (manual review step required by branch protection):
  gh pr merge <revert-pr-number> --squash
  ```

- **Expected outcome.** `release.yaml` is back on `main` with `state: "active"`; next dispatch fires normally.
- **Prevention.** Single-root invariants to spot-check after any workflow-dir PR. The globs below cover both `.yaml` and `.yml` extensions (the repo currently has at least one `.yml` workflow):

  ```bash
  # Any workflow with id-token: write should be a known release/provenance workflow.
  grep -l 'id-token: write' .github/workflows/*.{yaml,yml} 2>/dev/null
  # expected set:
  #   - docs.yaml (GitHub Pages — orthogonal to release)
  #   - release.yaml (canonical)

  # No `v*` push trigger should exist in any workflow — release.yaml is workflow_dispatch-only.
  # Scan the 3 lines following each `push:` block for a v* tag pattern.
  grep -A3 -E '^\s*push:' .github/workflows/*.{yaml,yml} 2>/dev/null \
    | grep -E "['\"]v\*['\"]"
  # expected: zero matches.
  ```

- **Escalation path — PR-revert only.** There is no out-of-band emergency hatch. Recovery flows exclusively through the Case 2 PR-revert path above: revert the offending workflow change via `gh pr revert`, merge through branch protection, then retry the release via `release.yaml`. Every release threads through branch protection + code review + OIDC Trusted Publisher, matching NFR2 and NFR3.

- **Constraints.** Branch protection on `main` blocks direct pushes — recovery goes through a PR in every case. Do not attempt to sidestep branch protection to "fix" `release.yaml` faster; the cost of a bad release (NFR5 audit-trail breakage, NFR10 commit-trail breakage) far exceeds the cost of a normal-review PR.

### Cross-reference matrix

| Scenario | Trigger class                   | Primary CLI verb                 | NFR linkage       |
| -------- | ------------------------------- | -------------------------------- | ----------------- |
| A        | Fresh bad latest                | `dist-tag` + `deprecate`         | NFR3              |
| B        | Stale bad latest                | `deprecate` + ship forward       | NFR3, NFR6        |
| C        | Eligible unpublish              | `unpublish`                      | (pre-v1.0.0 only) |
| D        | Tag orphan (publish failed)     | `tag -d` + `push --delete`       | NFR12             |
| E        | Post-publish state drift        | `tag -a` + `gh release create`   | NFR5              |
| F        | OIDC compromise                 | revoke Trusted Publisher + audit | NFR7              |
| G        | `release.yaml` disabled/missing | `workflow enable` / `pr revert`  | NFR5, NFR10       |

### Baseline snapshots

The ruleset-restore snippet at the top of this document (`## Branch Protection on main § Restore from a saved baseline`) uses `gh api --method PUT .../rulesets/<id>`. That call returns `404` if the `Default` ruleset has been deleted, not merely edited. Keeping a recent `baseline-ruleset-Default-YYYYMMDD.json` on disk lets the PUT-then-POST fallback below recover from either case.

**One-time capture pattern** — run after any maintainer-initiated change to the ruleset or to the `release` environment, **not on a schedule**:

```bash
# Capture the current Default ruleset as a disaster-recovery baseline.
# Uses name-based lookup so the snippet survives ruleset re-creation (IDs change, names don't).
RULESET_ID=$(gh api repos/armelhbobdad/bmad-module-skill-forge/rulesets \
  --jq '.[] | select(.name=="Default") | .id')
gh api "repos/armelhbobdad/bmad-module-skill-forge/rulesets/$RULESET_ID" \
  > "_bmad-output/planning-artifacts/baseline-ruleset-Default-$(date +%Y%m%d).json"

# Capture the release environment + its branch policy list (two separate resources).
gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release \
  > "_bmad-output/planning-artifacts/baseline-env-release-$(date +%Y%m%d).json"
gh api repos/armelhbobdad/bmad-module-skill-forge/environments/release/deployment-branch-policies \
  > "_bmad-output/planning-artifacts/baseline-env-release-branch-policies-$(date +%Y%m%d).json"
```

Baselines live in `_bmad-output/planning-artifacts/` (already git-tracked, not shipped with the npm package). The filename date stamp makes the freshness of the baseline obvious at a glance.

**Ruleset-deletion recovery path — PUT-then-POST.** The canonical restore flow is:

1. Try `PUT` first. If the ruleset exists but drifted, this reconciles it in place.

   ```bash
   RULESET_ID=$(gh api repos/armelhbobdad/bmad-module-skill-forge/rulesets \
     --jq '.[] | select(.name=="Default") | .id')
   # Pick the most recent baseline file (the YYYYMMDD suffix is a real date
   # written by the capture command above; the glob avoids hard-coding it).
   BASELINE=$(ls -t _bmad-output/planning-artifacts/baseline-ruleset-Default-*.json \
     | head -1)
   jq '{name, target, enforcement, conditions, rules, bypass_actors}' "$BASELINE" \
     > /tmp/restore.json
   gh api --method PUT \
     "repos/armelhbobdad/bmad-module-skill-forge/rulesets/$RULESET_ID" \
     --input /tmp/restore.json
   ```

2. If the `PUT` returns `404` (ruleset was deleted, not edited), recreate via `POST`:

   ```bash
   gh api --method POST \
     repos/armelhbobdad/bmad-module-skill-forge/rulesets \
     --input /tmp/restore.json
   ```

The `POST` body needs the same `name`, `target`, `enforcement`, `conditions`, `rules`, and `bypass_actors` fields as the PUT — all captured by the baseline snapshot above. Try `PUT` first; on `404`, `POST` recreates with identical semantics. The ruleset gets a new id on re-creation (IDs are not stable across delete+create cycles); update any hard-coded id references in this document on the next planned edit pass.

For the `release` environment, a deletion+restore similarly uses the two-call pattern already documented at `## Release Environment § Restore / re-apply` — feed the environment-level baseline JSON to the `PUT .../environments/release` call, then re-POST each entry from the branch-policies baseline to `.../environments/release/deployment-branch-policies`.

### Cutting v1.0.0 under --tag latest

- **Trigger.** The passing RC has survived a clean-environment smoke test (`release-audits/v1.0.0-launch-audit.md § Story 5.2 RC Cut + Smoke Test § Decision: PASS — cleared for Story 5.3 promotion to v1.0.0 under --tag latest with manual approval`); `npm view bmad-module-skill-forge@rc version` returns the passing RC (at Story 5.3 dispatch time: `1.0.0-rc.3`); Story 5.3 is ready to promote to `latest` under manual approval.
- **CLI.**

  ```bash
  git checkout main && git pull

  # Pre-dispatch sanity check (read version from remote, not local clone).
  gh api repos/armelhbobdad/bmad-module-skill-forge/contents/package.json \
    --jq '.content' | base64 -d | jq -r .version
  # expected: the passing RC (e.g., 1.0.0-rc.3)

  # Dispatch the canonical release workflow. `version_bump: major` on
  # 1.0.0-rc.N strips the prerelease suffix and produces 1.0.0 (node-semver
  # inc(ver, 'major') behavior on a prerelease). `--ref main` is explicit
  # (gh defaults to the repo's default branch, but any non-main ref takes
  # the legacy tag-only path inside release.yaml, so pass it defensively).
  gh workflow run release.yaml -f version_bump=major --ref main

  # Capture the run id for monitoring + audit transcript.
  RUN_ID=$(gh run list --workflow=release.yaml --limit 1 \
    --json databaseId --jq '.[0].databaseId')
  gh run watch $RUN_ID
  ```

  The workflow pauses at **two** gates that the maintainer must clear in the browser. Gate 1 requires explicit approval; gate 2 accepts either approval or admin-bypass-merge:

  1. The `release` environment deployment gate (at job start). Approve via "Review deployments" → "Approve and deploy" on the run page.
  2. The bot PR review-decision gate (after the 7 required status checks pass). EITHER approve the bot PR via the review UI, OR admin-bypass-merge via the PR merge button — both paths are accepted by `release.yaml`'s `Wait for PR approval or admin-bypass merge` step. Admin-bypass-merge is the observed pattern for prior cuts (PRs #209 and #213).

  Expected wall-clock: ~5–8 minutes end-to-end when both gates are approved promptly.

- **Expected outcome.** `main` tip advances by 2 commits (the `release: bump to v1.0.0` commit on the bot temp branch `release/bot/v1.0.0-<run_id>`, plus the merge commit from the auto-merged or admin-bypass-merged bot PR); `jq -r .version package.json` → `1.0.0`; `jq -r '.plugins[0].version' .claude-plugin/marketplace.json` → `1.0.0`; `npm view bmad-module-skill-forge dist-tags.latest` → `1.0.0` (flipped from the prior stable, e.g. `0.10.0`); `rc` dist-tag UNCHANGED at the prior RC; SLSA L2 provenance attached (NFR4); GitHub Release `v1.0.0` with `prerelease: false` (NFR6 threshold — `1.0.0` contains no `alpha|beta|rc` substring); tag `v1.0.0` anchors on the bot PR's merge commit per Story 3.4 P9 (the tag is annotated, so `git rev-parse 'v1.0.0^{}'` gives the commit SHA to compare against `main` tip).

- **Constraints.**
  - Execute ONLY after the RC audit `§ Sign-off` is populated AND the smoke-test `Decision` is `PASS`.
  - The cut is IRREVERSIBLE — once `npm publish --tag latest` succeeds for `1.0.0`, NFR6 forbids unpublish regardless of eligibility window. Rollback is `npm deprecate` + ship-forward (Scenarios A / B).
  - The CHANGELOG reconciliation is a POST-workflow step (authored as a separate sign-off commit on `feat/v1-final-signoff`). Do NOT hand-edit the `## [1.0.0] - TBD` placeholder BEFORE dispatch — let the workflow auto-generate its `## [1.0.0]` block (which may be EMPTY when there are zero conventional-commit `feat:` / `fix:` entries between the RC and the final cut, which is the normal case), then merge the hand-curated prose into the auto-gen header's position and delete the stale placeholder in one commit.
  - Do NOT pre-bump `package.json` or `.claude-plugin/marketplace.json` — the workflow's `Bump version` and `Update marketplace.json version` steps handle both atomically and own those files.
  - If `npm version major` unexpectedly emits `2.0.0` instead of `1.0.0` on `1.0.0-rc.N`, the node-semver engine behavior has regressed. Abort the dispatch and investigate before retry — a workflow override (`npm version 1.0.0 --no-git-tag-version`) would be required in `release.yaml`.

- **Verification.**

  ```bash
  # Confirm the latest dist-tag flipped to 1.0.0.
  npm view bmad-module-skill-forge dist-tags --json
  # expected: {"latest":"1.0.0","alpha":"...","rc":"1.0.0-rc.N"}

  npm view bmad-module-skill-forge@latest version
  # expected: 1.0.0

  # Confirm SLSA L2 provenance (NFR4 CRITICAL). A null attestation is a
  # blocker — emergency-deprecate + cut 1.0.1 with provenance per Scenario B.
  npm view bmad-module-skill-forge@1.0.0 --json | jq '.dist.attestations'
  # expected: non-null object; .provenance.predicateType starts with
  #           "https://slsa.dev/provenance/"

  # Confirm the GitHub Release exists and is NOT a prerelease (NFR6 threshold).
  gh release view v1.0.0 --json tagName,isPrerelease
  # expected: {"tagName":"v1.0.0","isPrerelease":false}

  # Confirm the v1.0.0 tag is reachable from main (annotated tag — dereference with ^{}).
  # Uses --is-ancestor so the check stays valid after subsequent commits land on main;
  # pin to the recorded merge SHA if you need strict tag-anchor equivalence.
  git fetch origin --tags
  git merge-base --is-ancestor "$(git rev-parse 'v1.0.0^{}')" origin/main && echo OK
  # expected: OK

  # Confirm CHANGELOG reconciliation after the sign-off commit lands on main.
  grep -c '^## \[1\.0\.0\] - TBD' CHANGELOG.md    # expected: 0 (stale placeholder gone)
  grep -cE '^## \[1\.0\.0\]' CHANGELOG.md         # expected: 1 (one reconciled block)
  grep -cE '^## \[1\.0\.0\]\(https' CHANGELOG.md  # expected: 1 (compare-URL header survived)
  ```

  **NFR6 immutability activation** is the `npm publish --tag latest` success timestamp for `1.0.0`, recorded verbatim in `release-audits/v1.0.0-launch-audit.md § Story 5.3 v1.0.0 Final Cut § NFR6 v1.0.0 immutability activation`. For Story 5.3's dispatch, that instant was **2026-04-23T18:56:39Z**. From that moment, `v1.0.0` is forever-burned — `npm deprecate` + ship-forward is the only rollback path.

  The `release` environment + bot PR approval-or-admin-bypass-merge pattern is the canonical flow for all main-dispatched cuts since Story 3.4 ([GitHub issue #198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198), [PR #199](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/199)): the release commit is pushed to a temp branch `release/bot/vX.Y.Z-<run_id>`, a bot PR is opened against `main`, the 7 required status checks are force-triggered against the temp branch via `workflow_dispatch`, and the merge is gated behind maintainer approval at both the `release` environment gate and the PR review-decision gate. Non-main dispatches (feature-branch alpha cuts) skip the PR dance entirely and keep the legacy tag-only behavior.

#### Post-publish verification (NFR9)

Cross-platform install verification for any cut is performed by the [`install-smoke.yaml`](../.github/workflows/install-smoke.yaml) workflow, not by `release.yaml` itself. Dispatch it within 1 hour of publish per NFR9:

```bash
gh workflow run install-smoke.yaml -f version=latest --ref main
```

The workflow fans a `workflow_dispatch` input over `ubuntu-latest`, `windows-latest`, and `macos-latest`, running `npx --yes bmad-module-skill-forge@<version> --version` on each runner. A clean three-leg run is the canonical post-publish evidence — its run URL + matrix table belong in the release audit artifact's `## Story <N> Post-Publish Verification` section. Any failing leg routes through the `Rollback Playbook § Scenario B` (deprecate + ship `vX.Y.Z+1`).
