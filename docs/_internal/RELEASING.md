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
| `required_status_checks` | Merge blocked until every `quality.yaml` check passes (names below).                                                    |

**Required status checks (10):** sourced from `.github/workflows/quality.yaml` job keys. Matrix jobs expand to `jobname (matrix-value)`:

- `prettier`
- `eslint`
- `markdownlint`
- `lintlang`
- `em-dash`
- `validate (ubuntu-latest)`
- `validate (windows-latest)`
- `python (ubuntu-latest)`
- `python (windows-latest)`
- `docs-links`

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

Only `alpha`, `beta` and `rc` can be cut from a feature branch: the gate step refuses `patch`, `minor` and `major` from any ref but `main`, because a stable release from another branch would publish to `latest` from a commit `main` never gets, and `main`'s next release would render the same fragments into the same version again. A feature-branch prerelease has no bot PR, so nobody reviews its notes before they are published; the run summary shows the **Review before approving** section afterwards.

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

## Cutting a Release

The dispatch mechanics are worked end-to-end in [§ Cutting v1.0.0 under --tag latest](#cutting-v100-under---tag-latest). That section is a launch-specific record, but its dispatch command, two-gate sequence, and verification block are the same for every cut. The sections below are general and apply to every cut.

### Pre-dispatch: preview the notes and the version bump

Release notes come from the change fragments in `changes/` (one YAML file per user-visible change; the format and the type rule are in [`changes/README.md`](../../changes/README.md)), not from commit subjects. Before dispatching, on an up-to-date `main` with its tags:

```bash
git checkout main && git pull --tags
npm run changes:preview -- --bump <alpha|beta|rc|patch|minor|major>
```

The preview prints the fragments added since the last stable tag (`git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*'`), any file in `changes/` to fix, the covered-surface changes against that tag from `tools/covered-surfaces.js` (hard, additive and review groups), the minimum bump with each reason for it, the version the dispatch will produce, the release gate's verdict for that bump, and the exact block the release will write. Fix a missing or mistyped fragment by pull request, then preview again. Read the review group as well. It lists first any flag that left every flag row while its workflow's Markdown still names it: if the workflow no longer accepts that flag, add a `breaking` fragment that names it. A new halt reason, an exit code given another meaning or changed flag text listed there can also be a breaking change that a fragment calls `fixed`.

Each pull request brings its own fragments, so the preview normally finds nothing missing: the required `em-dash` check runs `npm run changes:pr` on every pull request (see [CONTRIBUTING.md](../../CONTRIBUTING.md#the-pull-request-check)). It fails a pull request that changes the code the package ships (`src/`, `tools/cli/`, `tools/skf-npx-wrapper.js`) or `.npmignore` with no fragment of its own and no `Changelog: none (<reason>)` line in a commit message, one that removes a covered item no `breaking` fragment on it names, one that adds a covered item no `added` or `breaking` fragment on it covers, and one whose fragments are invalid or edit, rename or copy a released one. A pending fragment a pull request only edits counts only for the covered items it names in backticks. It compares each branch with its own merge base, not with the last stable tag, so the preview and the gate stay the check of the release as a whole: a pull request merged before the check existed, a `Changelog: none` line that was wrong (one line covers a whole branch), a user-visible change in what the check does not read (`package.json`, such as a raised `engines.node` floor or a new runtime dependency, `README.md` or the shipped `docs/`), and a change that a halt reason or a changed flag text reveals only in the review group are theirs to catch. The bot PR is exempt: its branch is `release/bot/*` of this repository, and its checks run through `workflow_dispatch`, where the step does not run, so a dispatch run's `em-dash` success does not include this check.

Keep `## [Unreleased]` in `CHANGELOG.md` empty. The release inserts the new block directly under it. The gate refuses a stable release that finds text there, before the tests run, and `npm run validate:changes` fails on a pull request that adds some; a note that belongs in the release goes in a fragment.

### The release gate

`release.yaml` runs `node tools/changes.js gate --bump <version_bump>` right after `npm ci`, before the tests and before anything is committed. It refuses the dispatch when:

- the version the `Bump version` step would produce is below the minimum bump, measured with `semver.diff` from the last stable tag (so a `patch` after a burned, untagged `3.0.0` gives `3.0.1` and still counts as a major step from `v2.2.0`);
- that version is below the current one: `npm version` moves a prerelease to a lower id without complaint (`alpha` on `3.0.0-rc.1` gives `3.0.0-alpha.0`);
- a covered item was removed (a schema enum value or property, a Ferris menu code, a pipeline alias or a workflow flag; see STABILITY.md) and no `breaking` fragment names it in backticks. A flag counts as removed when its workflow's Markdown no longer names it, or when it leaves every flag row as a flag the workflow never named before enters them (a possible rename); one that leaves every flag row while the Markdown still names it is not refused, and comes first in the review group instead;
- a file in `changes/` is not a valid fragment, or a fragment released in the last stable tag was edited, renamed or copied (a released fragment is never read again, so a new change goes in a new file);
- a stable release finds text under `## [Unreleased]` in `CHANGELOG.md`;
- a stable bump (`patch`, `minor` or `major`) is dispatched from a ref other than `main` (the gate step checks this before the tool runs);
- the release is a major and no fragment is `breaking`;
- a stable release has no fragment;
- a prerelease cannot reach the minimum (see the next section).

A refused run has committed and pushed nothing: fix the fragments by pull request and dispatch again. There is no override. If the surface diff is wrong, fix `tools/covered-surfaces.js` and its tests.

After the tests, the `Write release notes and CHANGELOG.md` step renders the same fragments. A stable release adds the block under `## [Unreleased]` in `CHANGELOG.md`, leaving every older release byte-identical, and every release writes `release_notes.md` (the GitHub Release body) and `release_review.md` (the **Review before approving** section of the bot PR: a checklist, why the minimum is what it is, the covered-surface changes and the notes). At gate 2, read that section and the `CHANGELOG.md` diff before approving. The same section is added to the run summary: a prerelease cut from a feature branch has no bot PR and so no gate 2, and the summary is the only place its review is shown, after the release is published.

### Prereleases and the RC hand bump

A prerelease writes only `release_notes.md` and leaves `CHANGELOG.md` alone, so its fragments are rendered again, in full, in the stable release's block.

`npm version prerelease` moves only the patch number of a stable version (`2.2.0` with `rc` gives `2.2.1-rc.0`), so a prerelease dispatched from a stable version cannot reach a minor or major minimum. The gate then refuses and names the version to set by hand, such as `3.0.0-rc.0`. Set it in `package.json`, `package-lock.json`, `.claude-plugin/marketplace.json` and `docs/_data/pinned.yaml` (its `skf_version` must match `package.json`) in a pull request, as the v1.0.0 RCs did (`3fc1f009`), then dispatch `rc`: the first RC published is `3.0.0-rc.1`. Dispatch `major` to go from the last RC to `3.0.0`. A release that needs no RC dispatches `major` or `minor` directly.

### The docs site

The docs site (GitHub Pages, built and deployed by [`docs.yaml`](../../.github/workflows/docs.yaml)) shows the latest stable release, not `main`. A merge to `main` does not deploy it: `docs.yaml` has no push trigger. At the end of a stable release (`patch`, `minor` or `major`), once the GitHub Release is created, `release.yaml` dispatches `docs.yaml` with `ref` set to the new tag, so the site changes when the package does. A prerelease leaves the site alone.

The release dispatches the deploy itself because it publishes the GitHub Release with `GITHUB_TOKEN`, and an event made with that token starts no other workflow (`workflow_dispatch` is an exception). The deploy runs on `main`, and `docs.yaml` checks out and builds the tag given in `ref`: by default the `github-pages` environment admits deployments from the default branch only, so a run on the tag itself would be refused at the deploy job.

A failed dispatch does not fail the release, which is already on npm: the run shows a warning with the command to run, and its summary says the site was not deployed. To deploy or redeploy by hand:

```bash
gh workflow run docs.yaml                   # the latest stable tag
gh workflow run docs.yaml -f ref=vX.Y.Z     # a given tag
gh run list --workflow=docs.yaml --limit 1  # find the run to follow
```

With `ref` empty, `docs.yaml` builds the latest stable tag reachable from `main` (`git describe --tags --abbrev=0 --exclude '*-*' --match 'v[0-9]*'`). `ref` also takes a branch or a commit, with a warning: the site then shows docs that no stable release has, until the next stable release deploys over them.

**An urgent docs fix** normally ships as a patch release: merge the fix with a `docs` fragment (see [`changes/README.md`](../../changes/README.md)), preview with `npm run changes:preview -- --bump patch`, then dispatch `version_bump=patch`. The release deploys the site at the new tag.

### The bot temp branch after a merge or a failed run

On a `main` dispatch, the release commit goes to the temp branch `release/bot/vX.Y.Z-<run_id>-<run_attempt>` and a bot PR from it. The name carries the run attempt because **Re-run failed jobs** keeps the run id and builds the release commit again with a new SHA: a branch named after the run id alone refused the re-run's push as a non-fast-forward.

**After a merge.** `Auto-merge bot PR` runs `gh pr merge --auto --merge --delete-branch`. When the PR can merge at once, gh merges it and deletes the temp branch. When it cannot merge yet, gh queues an auto-merge and skips the delete, and `delete_branch_on_merge` is off on this repository, so the branch stays on origin after the queued merge. Clearing gate 2 with the PR merge button instead (admin bypass, the observed pattern for most cuts) merges the PR before that step, which is then skipped, and the branch stays on origin too.

**After a failed run.** A run that fails or is cancelled once its temp branch is pushed ends with the step `Close the bot PR and delete its branch after a failed run`:

- an open bot PR is closed with a comment that links the run, and its branch is deleted;
- the branch of a PR that is already closed, or of a run that stopped before it opened its PR, is deleted;
- a merged bot PR and its branch are left alone: `main` then carries the release commit, and the [Rollback Playbook](#rollback-playbook) covers a run that stopped after the merge.

A closed PR keeps the release commit reachable (`refs/pull/<n>/head`), so closing it loses nothing to inspect. To retry, use **Re-run failed jobs** on the run (a flaky check, an approval that timed out) or dispatch `release.yaml` again once the defect is fixed on `main`: either opens a new bot PR, and no second `release: bump to` PR sits next to the old one. If that step itself fails, its error names the command that finishes the job by hand (`gh pr close <n> --delete-branch` or `git push origin --delete <branch>`).

Either way, check that nothing is left:

```bash
# Expect zero once a cut is fully closed out, published or failed.
git ls-remote --heads origin 'release/bot/*'
gh pr list --state open --search '"release: bump to" in:title'

# Delete a leftover only after confirming its commit is reachable from main.
git fetch origin --quiet
git merge-base --is-ancestor <temp-branch-sha> origin/main \
  && git push origin --delete release/bot/vX.Y.Z-<run_id>-<run_attempt>
```

The tag anchors on the bot PR's merge commit on `main`, not on the temp branch (see the `Create and push tag` step's main-dispatch path), so deleting the branch after the merge orphans nothing. The exception is a pull request that merged into `main` while the release waited for checks and approval (`strict_required_status_checks_policy` is `false`, so the bot PR is not rebased first): the merge commit's tree then holds that pull request, which the published package does not, so the tag goes on the release commit itself, which `main` reaches through the merge commit. The next release then renders that pull request's fragment and checks its surfaces. If the bot PR was squash- or rebase-merged in that case, the release commit is not on `main`, and the run stops before tagging or publishing: re-dispatch as in [§ Scenario D](#scenario-d--tag-exists-but-npm-publish-failed), with no tag to delete. The reachability check is what distinguishes this from the tag-orphan case in [§ Scenario D](#scenario-d--tag-exists-but-npm-publish-failed); if the commit is _not_ reachable, the merge did not land: the branch belongs to a run still in progress, or to a failed run whose last step could not finish, and `gh pr list --head <branch> --state all` tells which.

<!-- Rollback Playbook — added in Story 4.1 -->

## Rollback Playbook

> **NEVER `npm unpublish` v1.0.0.** Once `bmad-module-skill-forge` is published under `--tag latest` at v1.0.0, the version is immutable by policy (NFR6). The default rollback is `npm deprecate` + ship forward. See Scenario C for the narrow 72h / zero-dependents exception — which applies to **pre-v1.0.0 versions only**.

Scenarios A–F are recovery paths for a bad publish; Scenario G is a meta-recovery path for the release workflow itself. Each scenario follows a five-element shape: **Trigger** → **CLI** → **Expected outcome** → **Constraints** → **Verification**. A compact [cross-reference matrix](#cross-reference-matrix) sits at the end of this section for under-pressure triage. All `gh api` examples in this section use name-based lookups (ruleset by `name=="Default"`, environment by literal `release`) so they survive ruleset or environment re-creation.

Placeholder substitutions used throughout:

- `<bad>` — the broken version just published (e.g. `0.10.1`).
- `<previous_good>` — the last known-good version immediately before `<bad>` (e.g. `0.10.0`).
- `<next_version>` — the fix version produced by the next `release.yaml` dispatch (e.g. `0.10.2`).
- `<run-id>` — a GitHub Actions run id visible in the Actions UI and via `gh run list --workflow=release.yaml`.

**A ship-forward cut needs a change fragment.** Every `version_bump=patch` below is a stable release, and the release gate refuses a stable release with no fragment added since the last stable tag. The pull request with the fix adds a `fixed` fragment (see [`changes/README.md`](../../changes/README.md)); preview the cut with `npm run changes:preview -- --bump patch` before dispatching.

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
- **Re-dispatching a stable cut.** The gate, the notes and their compare link all start at the last stable tag, and fragments stay in `changes/` after a release, so once the tag of a failed stable cut is deleted, a `patch` re-dispatch is enough even for a major: a burned `3.0.0` gives `3.0.1` with the same notes, and the gate still counts it a major step from `v2.2.0`. If the bot PR had merged, `CHANGELOG.md` then holds both the unshipped `3.0.0` block and the `3.0.1` one; delete the unshipped block by pull request.
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

- **CLI: GitHub Release recovery.** The workflow's `Write release notes and CHANGELOG.md` step writes `release_notes.md` inside the runner; that file is **not** uploaded as an artifact, so it does not exist outside the run. Rebuild the same text from the change fragments on the release commit, or let GitHub regenerate notes from commit subjects.

  ```bash
  # Option A: rebuild the notes from the change fragments (after npm ci).
  # --base is the stable tag before <version>: the new tag now exists, so it
  # is no longer the last one. --date is the date in the CHANGELOG.md heading.
  # --notes-only leaves CHANGELOG.md alone.
  git checkout v<version>
  node tools/changes.js release --base v<previous_stable> --version <version> \
    --date <YYYY-MM-DD> --notes-only --notes release_notes.md
  gh release create v<version> \
    --notes-file release_notes.md \
    --title "Skill Forge (SKF) v<version>"

  # Option B: let GitHub regenerate from commit subjects (loses the curated
  # notes but always works).
  gh release create v<version> \
    --generate-notes \
    --title "Skill Forge (SKF) v<version>"
  ```

- **CLI: docs site recovery (stable `<version>` only).** The `Deploy the docs site at the new tag` step runs after `Create GitHub Release`, so it did not run either. Once the tag is on origin, deploy the site as in [§ The docs site](#the-docs-site): `gh workflow run docs.yaml -f ref=v<version>`. Check the tag first: the site's version badge is read from `package.json` at build time, and the tag recovery above points the tag at the run's `head_sha`, the commit the release was dispatched from, which is before the version bump. `git show v<version>:package.json` must show `<version>`; if it does not, recreate the tag on the commit on `main` that bumped `package.json` to `<version>`, then deploy.
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

  **Known-benign row.** A full listing (without the `select(.name=="Release")` filter) also returns `.github/workflows/env-gate-test.yaml`, a Story 1.2 throwaway whose file exists on no branch and which has no commit in `git log --all`. It was registered through the API rather than a merged file, so deleting the file never pruned it. It read `active` until it was set to `disabled_manually` (issue #485); either way it cannot fire, because a workflow with no file on any ref has nothing to run. Ignore it — it is not a dispatch hole, and it is not evidence that Scenario G applies.

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
  #   - docs.yaml (GitHub Pages; release.yaml dispatches it after a stable release)
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
  2. The bot PR review-decision gate (after the required status checks pass). EITHER approve the bot PR via the review UI, OR admin-bypass-merge via the PR merge button — both paths are accepted by `release.yaml`'s `Wait for PR approval or admin-bypass merge` step. Admin-bypass-merge is the observed pattern for prior cuts (PRs #209 and #213).

  Expected wall-clock: ~5–8 minutes end-to-end when both gates are approved promptly.

- **Expected outcome.** `main` tip advances by 2 commits (the `release: bump to v1.0.0` commit on the bot temp branch `release/bot/v1.0.0-<run_id>-<run_attempt>`, plus the merge commit from the auto-merged or admin-bypass-merged bot PR); `jq -r .version package.json` → `1.0.0`; `jq -r '.plugins[0].version' .claude-plugin/marketplace.json` → `1.0.0`; `npm view bmad-module-skill-forge dist-tags.latest` → `1.0.0` (flipped from the prior stable, e.g. `0.10.0`); `rc` dist-tag UNCHANGED at the prior RC; SLSA L2 provenance attached (NFR4); GitHub Release `v1.0.0` with `prerelease: false` (NFR6 threshold: `1.0.0` contains no `alpha|beta|rc` substring); tag `v1.0.0` anchors on the bot PR's merge commit per Story 3.4 P9 (the tag is annotated, so `git rev-parse 'v1.0.0^{}'` gives the commit SHA to compare against `main` tip).

- **Constraints.**
  - Execute ONLY after the RC audit `§ Sign-off` is populated AND the smoke-test `Decision` is `PASS`.
  - The cut is IRREVERSIBLE — once `npm publish --tag latest` succeeds for `1.0.0`, NFR6 forbids unpublish regardless of eligibility window. Rollback is `npm deprecate` + ship-forward (Scenarios A / B).
  - `CHANGELOG.md` is written by the workflow from the change fragments (see [§ Pre-dispatch: preview the notes and the version bump](#pre-dispatch-preview-the-notes-and-the-version-bump)): do not hand-edit it before dispatch. At the v1.0.0 launch the block was generated from commit subjects instead, and the hand-written `## [1.0.0] - TBD` prose was merged into it by a sign-off commit on `feat/v1-final-signoff` after publish.
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

  The `release` environment + bot PR approval-or-admin-bypass-merge pattern is the canonical flow for all main-dispatched cuts since Story 3.4 ([GitHub issue #198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198), [PR #199](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/199)): the release commit is pushed to a temp branch `release/bot/vX.Y.Z-<run_id>-<run_attempt>`, a bot PR is opened against `main`, the required status checks are force-triggered against the temp branch via `workflow_dispatch`, and the merge is gated behind maintainer approval at both the `release` environment gate and the PR review-decision gate. A run that stops before the merge closes its bot PR and deletes the branch (see [§ The bot temp branch after a merge or a failed run](#the-bot-temp-branch-after-a-merge-or-a-failed-run)). Non-main dispatches (feature-branch alpha cuts) skip the PR dance entirely and keep the legacy tag-only behavior.

#### Post-publish verification (NFR9)

Cross-platform install verification for any cut is performed by the [`install-smoke.yaml`](/.github/workflows/install-smoke.yaml) workflow, not by `release.yaml` itself. Dispatch it within 1 hour of publish per NFR9:

```bash
gh workflow run install-smoke.yaml -f version=latest --ref main
```

The workflow fans a `workflow_dispatch` input over `ubuntu-latest`, `windows-latest`, and `macos-latest`, running `npx --yes bmad-module-skill-forge@<version> --version` on each runner. A clean three-leg run is the canonical post-publish evidence. Any failing leg routes through the `Rollback Playbook § Scenario B` (deprecate + ship `vX.Y.Z+1`).

**Where the evidence lives.** For a routine release the workflow run **is** the record — the dispatch satisfies NFR9 on its own and no audit artifact is written. Launch cuts additionally transcribe the run URL and matrix table into a per-launch audit artifact under `release-audits/`; `v1.0.0-launch-audit.md § Story 5.4 Post-Publish Verification` is the worked example and remains the only such artifact. Do not append routine releases to it — each audit file is a forensic record scoped to the launch that produced it.
