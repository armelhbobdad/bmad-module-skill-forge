# Change fragments

Each change a user or a pipeline can notice gets one short YAML file in this folder, `changes/<topic>.yaml`, added by the pull request that makes the change. At release, `tools/changes.js` renders the fragments added since the last stable release into the new CHANGELOG.md block and the GitHub Release notes, and their types set the smallest version bump the release may take.

Fragments stay here after a release. A release takes only the fragments that did not exist at the last stable tag, so nothing is deleted when a version ships. A released fragment is never read again, so every new change, and each release's lead, needs a file with a new name (for a lead, for example `lead-3-1-0.yaml`). A released fragment that was edited, renamed or copied is refused, and the check names the file.

## When to add one

Add a fragment when a user or a pipeline can notice the change: a workflow behaves differently, a flag, status, exit code, halt reason or preference appears or goes, the install changes, or the user docs gain something worth announcing. Refactors, tests, CI and maintainer-only docs need none. Write one fragment per change: a pull request with two user-visible changes adds two.

Every pull request is checked for its fragments (`npm run changes:pr`, run by the required `em-dash` check). A pull request that changes the code the npm package ships (`src/`, `tools/cli/`, `tools/skf-npx-wrapper.js`) or `.npmignore` needs a fragment of its own, or, when no user or pipeline can notice any of its changes, a `Changelog: none (<reason>)` line in one of its commit messages, with the reason written out. One such line covers the whole pull request, so a pull request that mixes a refactor and a fix still needs a fragment for the fix. The line never covers a covered item the pull request removes or adds (see the end of [Which type](#which-type)): a removal needs a `breaking` fragment that names it, an addition an `added` or `breaking` fragment. Editing another pull request's pending fragment counts only for the covered items the edit names in backticks. The check does not read `package.json`, `README.md` or `docs/`, which the package also ships: a change a user notices there still takes a fragment. [CONTRIBUTING.md](../CONTRIBUTING.md#the-pull-request-check) has the details.

## Format

```yaml
type: breaking
scope: skf-update-skill
summary: |
  `--detect-only` and `--dry-run` now stop on an SKF skill still in the flat layout (`blocked`, `init:read-only-flat-layout`) instead of moving it into the versioned layout.
migration: |
  Run `@Ferris US <name>` once without the flag, then re-run with it.
prs: [499]
issues: [497]
```

| Key | Required | What it holds |
| --- | --- | --- |
| `type` | always | `breaking`, `added`, `changed`, `fixed`, `docs` or `lead` (see below) |
| `scope` | for every type except `docs` and `lead` | the workflow or area that changed, in lower case: `skf-setup`, `skf-create-skill, skf-test-skill`, `all workflows`, `packaging` |
| `summary` | always | one paragraph a user understands: what changed, with flags, statuses, codes and file names in backticks |
| `migration` | for `breaking` only | the exact action a user takes, in one paragraph |
| `issues` | no | issue numbers, as a list: `[502]` |
| `prs` | no | pull request numbers, as a list: `[509]` |

Name the file after the change, in lower case with hyphens, such as `setup-retire-write-failure.yaml`. No other key is accepted. A summary or migration holds no em dash and cites no step-file section (§): describe the behaviour instead. A `lead` holds only a `summary`, the paragraph that opens the release notes, and a release takes at most one.

## Which type

Pick the type by what a user sees, not by the commit type. When unsure, pick the higher one.

- **breaking**: the change removes or renames a covered item (a schema enum value or property, a Ferris menu code, a pipeline alias or a flag), tightens an input schema, raises a requirement, or makes an input that used to succeed on skills SKF generated now halt or exit non-zero. A refusal that only protects folders SKF did not generate is `fixed`, not `breaking`.
- **added**: a new flag, menu code, alias, preference key, exit code, status, halt reason or capability.
- **changed**: the output or a default is different, and nothing was removed.
- **fixed**: the behaviour now matches the docs.
- **docs**: a change to the user docs worth announcing.
- **lead**: the opening paragraph of the release notes, usually written for the release itself.

The minimum version bump is major for a `breaking` fragment, minor for `added` or `changed`, and patch for `fixed` or `docs`. The covered-surface check (`tools/covered-surfaces.js`) can raise it: removing a schema enum value or property, a menu code, a pipeline alias or a flag needs a major bump and a `breaking` fragment that names the item, in backticks (the plain word does not count); adding one of those, a preference key or an exit code needs at least a minor bump. A tool minimum in `src/shared/tool-requirements.yaml` works the other way round: raising one, or giving a tool its first one, needs a major bump and a `breaking` fragment that names the tool by its `name` in backticks, such as `ast-grep`, while lowering or removing one needs at least a minor bump.

## Commands

- `npm run validate:changes` checks every file in this folder, refuses a released fragment that changed, and checks that `## [Unreleased]` in `CHANGELOG.md` is empty.
- `npm run changes:pr` checks the fragments your branch needs, from its merge base with `origin/main` to `HEAD`: commit first, then run it before you push. On a failure it prints what is missing and a fragment to fill in, which `npm run validate:changes` refuses until you rewrite each sentence that starts with "Rewrite this paragraph".
- `npm run changes:preview` shows the fragments added since the last stable tag, any file here to fix, the covered-surface changes, the minimum bump and why, the next version, the release gate's verdict for the minimum bump and the rendered block. The verdict covers the whole next release, not only your pull request. Pass a bump to check another one: `npm run changes:preview -- --bump minor`.
