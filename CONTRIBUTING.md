# Contributing to Skill Forge

SKF turns code and docs into verified agent skills. Every instruction traces back to a real line of source. See [README.md](README.md) for the pitch; this file covers how to land changes without setting the test suite on fire.

SKF is a [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module. For BMAD philosophy, framework conventions, and module-authoring patterns in general, start at [docs.bmad-method.org](https://docs.bmad-method.org). This doc stays scoped to what's SKF-specific.

## What You Can Contribute

- **Workflows** (`src/skf-*/`) — new skill-compilation or lifecycle flows. Example: a `skf-diff-skill` that compares two versions of the same skill and emits a migration note.
- **Knowledge fragments** (`src/knowledge/`) — cross-workflow principles Ferris loads just-in-time. Example: a new `security-review.md` that captures rules reused by CS, QS, and AS.
- **Forger assets** (`src/forger/`, `src/shared/`) — shared agent memory, preferences, or helpers (e.g. tier detection, health-check templates).
- **Validators** (`tools/validate-*.js`) — deterministic checks that run in `npm run quality`. Example: a new validator that flags `{installed_path}` leaks in step files.
- **Docs** (`docs/`, `website/`): tutorial / reference / explanation content surfaced at [armelhbobdad.github.io/bmad-module-skill-forge](https://armelhbobdad.github.io/bmad-module-skill-forge/). The site is deployed from the latest stable release, not from `main`, so a merged docs change goes live with the next stable release.
- **Ecosystem integrations** — new tool bridges (ast-grep, cocoindex, QMD, tessl, Snyk, graphify-style indexers) wired through the tier-aware discovery path.
- **Bug reports** — always useful, especially if they come in via the workflow health-check loop (see below).

If you're not sure where a change belongs, open an issue and ask before writing code.

## Local Setup

**Platforms:** Linux, Windows, and macOS. Linux and Windows are exercised in CI on every PR (`ubuntu-latest` + `windows-latest` matrix); macOS works in practice (POSIX-equivalent to Linux) but isn't CI-gated. On Windows, SKF transparently falls back to NTFS junctions when symlink privilege isn't held — no Developer Mode or admin rights required. Git Bash (bundled with [Git for Windows](https://git-scm.com/download/win)), PowerShell, and WSL2 all work.

**Prerequisites** (the [prerequisites table](docs/getting-started.md#prerequisites-full-reference) lists every tool with its minimum and tested versions):

- [Node.js](https://nodejs.org/) >= 22, the supported floor (`engines.node`); development and CI run the version in `.nvmrc`
- [Python](https://www.python.org/) >= 3.11, the version CI runs the Python tests on (`UV_PYTHON=3.11 npm run test:python` does the same locally, where a plain `npm run test:python` uses uv's default Python)
- [uv](https://docs.astral.sh/uv/), which runs the Python test suite
- `git` and `gh`, used by several workflows and by the health-check loop

```bash
git clone https://github.com/armelhbobdad/bmad-module-skill-forge.git
cd bmad-module-skill-forge
npm install           # also wires husky pre-commit hooks via "prepare"
npm run quality       # run the full local pre-flight
```

The `npm run quality` script is your contract with CI. It runs:

- `format:check` (Prettier), `lint` (ESLint), `lint:md` (markdownlint), `lint:instructions` (LintLang on the agent instructions under `src/`)
- `test:schemas`, `test:install`, `test:cli`, `test:workflow`, `test:python`, `test:rehype`, `test:docs-links-tool`, `test:em-dash-tool`, `test:file-refs-tool`, `test:changes-tool`, `test:tool-requirements-tool`, `test:knowledge`
- `validate:schemas`, `validate:skills`, `validate:refs`, `validate:docs-links`, `validate:em-dash`, `validate:changes` (the change fragments in `changes/`, see [Change Fragments](#change-fragments)), `validate:tool-requirements` (the tool versions, see [Tool Versions](#tool-versions))
- `docs:validate-drift` — SKF docs vs. the canonical [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills) output

`test:python` runs every `test/test-*.py` file with pytest under `uv`, so a new Python test file runs as soon as it exists: there is no list to add it to.

If `npm run quality` passes locally, CI should too. The same steps run in [`.github/workflows/quality.yaml`](.github/workflows/quality.yaml) on every pull request. A pull request also runs `npm run changes:pr`, which compares your branch with its base branch and so is not part of `npm run quality`: see [The pull request check](#the-pull-request-check).

Write no em dashes (U+2014) in anything you add, including commit messages: use a colon, a comma, parentheses or a new sentence. `validate:em-dash` fails on any em dash in the published docs (`README.md`, `docs/` outside `docs/_internal/`, `website/`) and on any em dash in the lines or commit messages your branch adds. The one exception is the context-snippet lines SKF generates (`|IMPORTANT:`, `|key-types:` and the like, a pipe followed directly by a key and a colon), which docs may quote as they are.

### Tool Versions

[`src/shared/tool-requirements.yaml`](src/shared/tool-requirements.yaml) is the one list of the tools SKF uses (Node.js, Python, uv, git, gh, ast-grep, ccc, qmd, tessl, skill-check), with each tool's minimum and tested versions. Its header says how those numbers are set: `tested` names versions a run actually used, and a minimum starts at a tested version and comes down only after a run on an older one passes. The prerequisites table in `docs/getting-started.md` is generated from it, so to change a version:

1. Edit `src/shared/tool-requirements.yaml`, not the table.
2. Run `node tools/tool-requirements.js --write` to regenerate the table.
3. Run `npm run validate:tool-requirements` (`node tools/tool-requirements.js --check`). It names the file and line of every copy that no longer agrees with the list: the Node.js and Python minimums in `README.md` (its install line and Python badge), `docs/` and this file, `engines.node` in `package.json`, `.nvmrc`, the `node-version` and `python-version` values in `.github/workflows/`, the `ast-grep-cli==` pin in `test:python`, and the README Acknowledgements rows. Fix those copies by hand.

## Workflow for Changes

1. **Branch from `main`.** Name it like the commit scope: `fix/skf-test-skill-...`, `feat/health-check-...`, `docs/...`.
2. **Match the commit-message convention from the git log.** SKF uses conventional-commit prefixes with a scoped subsystem:
   - `feat(skf-create-skill): ...`
   - `fix(health-check): ...`
   - `docs(readme): ...`
   - `ci(health-check): ...`
   - `refactor(skf-create-skill): ...`
   - `chore: ...` (no scope needed)

   `git log --oneline -20` is the authoritative style guide. Match what you see. The prefix is for the history only: release notes and the version bump come from change fragments (step 7), so the commit type and the merge style do not change what a release says.

3. **Reference issues with `Fixes #NNN`** in the PR body (and optionally in the commit trailer). Use **same-repo GitHub issue numbers only** — do not reference internal IDs under `_bmad-output/todo/` or elsewhere; those are author notes, not public contracts.
4. **The pre-commit hook runs automatically** via husky, in this order:
   - lint-staged. Staged JS runs `npm run lint:fix` and `npm run format:fix`, staged YAML runs `eslint --fix` on those files and `format:fix`, and staged JSON runs `format:fix`. Those two scripts cover the whole repository, not only what you staged. Staged `.md` files are linted with markdownlint, and staged `.astro` files are formatted with Prettier.
   - It clears git's repository variables (such as `GIT_DIR` and `GIT_INDEX_FILE`), so the git repositories the tests create never touch the commit being made.
   - The full `npm test` suite, so a commit takes as long as a test run.
5. **PR description:** explain _why_. What was broken, what does this change, and how did you verify it? Keep it honest and short. The template in [.github/](.github/) is a starting point; ignore the sections that don't apply.
6. **If you used Claude (or any AI assistant)** to help write a non-trivial chunk of the change, add a `Co-Authored-By:` trailer to the commit — SKF's recent history uses the format:

   ```
   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
   ```

   Not mandatory, but we prefer accurate attribution over silent ghostwriting.

7. **Add a change fragment** in the same pull request for each change a user or a pipeline can notice, and run `npm run changes:pr` before you push: see [Change Fragments](#change-fragments).

## Change Fragments

Release notes are written from change fragments, not from commit subjects. A pull request that changes something a user or a pipeline can notice adds one short YAML file per change to [`changes/`](changes/README.md), named after the change: `changes/<topic>.yaml`. At release, the workflow renders every fragment added since the last stable release into the new `CHANGELOG.md` block and the GitHub Release, and refuses a `version_bump` smaller than the fragments call for. Fragments are never deleted: a release takes only the ones added since the last stable tag. A released fragment is never read again, so a new change always goes in a new file: the release refuses a released fragment that was edited, renamed or copied.

**When.** Add a fragment when a workflow behaves differently, when a flag, status, exit code, halt reason or preference appears or goes, when the install changes, or when the user docs gain something worth announcing. Refactors, tests, CI and maintainer-only docs need none; a refactor of the code the package ships says so in a commit message instead (see [The pull request check](#the-pull-request-check)).

**Which type.** Type the change by what a user sees, not by the commit prefix, and pick the higher type when unsure:

- `breaking`: the change removes or renames a covered item (a schema enum value or property, a Ferris menu code, a pipeline alias or a flag), tightens an input schema, raises a requirement, or makes an input that used to succeed on SKF-generated skills halt or exit non-zero. A refusal that only protects folders SKF did not generate is `fixed`. A `breaking` fragment needs a `migration`: the exact action a user takes.
- `added`: a new flag, menu code, alias, preference key, exit code, status, halt reason or capability.
- `changed`: the output or a default is different, and nothing was removed.
- `fixed`: the behaviour now matches the docs.
- `docs`: a change to the user docs worth announcing.

`lead` is a sixth type for the paragraph that opens a release's notes, usually added when the release is prepared.

```yaml
type: added
scope: skf-update-skill
summary: |
  New `--target-ref <ref>` flag: update a skill built from a remote repository against a tag, branch, `HEAD` or full commit instead of the ref it recorded.
prs: [517]
issues: [511]
```

Write flags, statuses, codes and file names in backticks: a release that removes a covered item needs a `breaking` fragment that names it, and only a name in backticks counts. Add `prs:` once the pull request has a number. Before pushing, run `npm run changes:preview`: it lists the fragments added since the last stable tag, the covered-surface changes against it (`tools/covered-surfaces.js`), the minimum bump and why, and the rendered block. It also prints the release gate's verdict for the whole next release, not for your pull request alone: a refusal about an item or a fragment your pull request touches is yours to fix; any other refusal is for the maintainer who cuts the release, and your pull request only needs its own fragments to pass `npm run validate:changes` and `npm run changes:pr`. For each new halt reason or exit code it lists, ask again whether an input that used to succeed now stops. `npm run validate:changes` checks the format, which [`changes/README.md`](changes/README.md) describes in full.

### The pull request check

The required `em-dash` check runs `npm run changes:pr` on every pull request. It compares your branch, from its merge base with the base branch to `HEAD`, and fails when:

- the branch changes the code the npm package ships (anything under `src/` or `tools/cli/`, and `tools/skf-npx-wrapper.js`) or `.npmignore`, which decides what ships, and has no change fragment of its own;
- a covered item the branch removes (a schema enum value or property, a Ferris menu code, a pipeline alias or a flag) is not named in backticks by a `breaking` fragment on the branch;
- a covered item the branch adds (one of those, a preference key or an exit code) has no `added` or `breaking` fragment on the branch;
- a fragment the branch adds or edits is not valid, or the branch edits, renames or copies a fragment an earlier release shipped.

A fragment on the branch is one it adds. A fragment it edits that no release has shipped yet, such as another pull request's pending one, counts only for the covered items it names in backticks: a follow-up that removes a flag can name it in the pending `breaking` fragment it extends, and then needs no other fragment, but an edit that names none of the branch's covered items never stands in for a fragment of its own.

The check reads only the code the package ships. The package also ships `package.json`, `README.md` and part of `docs/`, and the check asks nothing of a branch that changes only those or other files (the other `tools/*.js` scripts, `test/`, `.github/`). A change a user notices there still takes a fragment, as **When** says above: a user docs change worth announcing takes a `docs` fragment, and a raised `engines.node` floor or a new runtime requirement in `package.json` is `breaking`.

When no user or pipeline can notice any change the branch makes to the code the package ships, such as a refactor with the same output or a reworded comment, give the reason in one of the branch's commit messages instead of a fragment, on a line of its own (with the other trailers is best). A merge commit on the branch counts too. To add the line to a branch you already pushed, push an empty commit that carries it (`git commit --allow-empty`):

```text
Changelog: none (refactor, the output is unchanged)
```

The reason inside the parentheses is required: `Changelog: none` alone covers nothing, and neither does `Changelog: none (<reason>)` pasted as it is. One such line covers the whole branch, so use it only when nothing the branch changes in the code the package ships is noticeable: a branch that mixes a refactor and a fix still needs a fragment for the fix. The line only stands in for a fragment the first rule asks for. It never covers a covered item the branch removes or adds: those always need their fragment, because the release notes and the version bump come from it.

Run the check before you push. It reads commits, not the working tree, so commit first, and fetch the base branch so the merge base is current:

```bash
git fetch origin
npm run changes:pr
```

It compares with `origin/main` by default (on a pull request, with `origin/<base branch>`); pass `-- --base <ref>` for another base. In a fork, `origin` is your fork, so compare with the upstream repository instead:

```bash
git fetch upstream
npm run changes:pr -- --base upstream/main
```

The released-fragment rule takes the last stable tag reachable from the base, as CI does, so a branch forked before the latest release is still checked against it. On a failure the check prints what is missing and a fragment to fill in, with the type and scope worked out from what the branch changes, and exits `1`; in CI the same text is in the job summary. The fragment it prints fails `npm run validate:changes` until you rewrite each sentence that starts with "Rewrite this paragraph". It exits `2` when it cannot run, for example when the base branch has not been fetched, or when a shallow clone does not hold the merge base (`git fetch --unshallow origin`). The release workflow's own pull request, from a `release/bot/*` branch of this repository, is exempt: its one commit bumps the version and renders the notes from fragments already merged. A `release/bot/*` branch from a fork, or from a repository the check cannot confirm, is checked like any other.

## The Quality Gate

`npm run quality` must pass before you push. If it fails:

- **Fix the root cause.** Do not `git commit --no-verify`. Do not disable a rule to make the linter shut up. If a hook is wrong, fix the hook in a separate PR.
- **If a Python test gives a different result on your machine than in CI,** run the tests on the Python CI uses (see [Local Setup](#local-setup)), check your `uv` version, and re-run `npm run test:python` from a clean shell.
- **If `docs:validate-drift` fails,** you either touched a pinned version/commit SHA that no longer resolves in [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills), or you added a library reference the whitelist doesn't cover. Fix the reference; don't relax the validator unless the fix is clearly out of scope.

CI re-runs everything on the PR. A green local run and a red CI run means (a) you have uncommitted files, (b) your Node/uv/Python versions drift from `.nvmrc` / `test:python` / the Python minimum, or (c) the pull request check failed: `npm run changes:pr` is not part of `npm run quality`, so run it after committing. Check all three before filing a CI bug.

## Releasing

Maintainers only — if you're not cutting a release, skip this section.

- **Canonical path:** `.github/workflows/release.yaml`, triggered via GitHub Actions → Run workflow → choose `version_bump` (`alpha` / `beta` / `rc` / `patch` / `minor` / `major`). That is the only supported route — OIDC-backed publish, required-reviewer gate on the `release` environment, auto-provenance on the npm tarball.
- **Before dispatch:** run `npm run changes:preview -- --bump <type>` on an up-to-date `main`. The workflow's release gate refuses a `version_bump` below the minimum the preview prints, before anything is committed.

See [docs/\_internal/RELEASING.md](docs/_internal/RELEASING.md) for the full procedure — branch-protection rules, the `release` environment with its required-reviewer gate, npm Trusted Publisher registration, and the seven-scenario [rollback playbook](docs/_internal/RELEASING.md#rollback-playbook).

## Adding a New Workflow Skill

The `src/skf-*/` directories each follow the same shape:

```
src/skf-<name>/
  SKILL.md            # frontmatter (name, description, "Use when ..."), stages table
  references/            # one file per step, loaded one-at-a-time by Ferris
  references/         # step-scoped rules, protocols, decision tables
  assets/             # step-scoped templates, schemas, output formats
```

- **Start from an existing skill** with similar shape — `skf-quick-skill` is the simplest, `skf-create-skill` is the reference for the full pipeline.
- **Or scaffold with BMAD tooling** — the `bmad-workflow-builder` skill builds / edits / converts workflows interactively; `@Ferris CS` (skf-create-skill) is the content-extraction pattern SKF uses for its own skills in the wild.
- **Frontmatter matters.** `validate:skills` enforces SKILL-01 through STEP-07 (see [`tools/validate-skills.js`](tools/validate-skills.js)): SKILL.md must have `name` + `description` with a "Use when" / "Use if" trigger; step files must not have `name`/`description`; step count must be 2–10; step filenames must match `step-NN-<slug>.md`.
- **Manifest.** Agent-facing skills (e.g. `skf-forger`) require a `bmad-skill-manifest.yaml`. Copy the one from `src/skf-forger/` and adapt.
- **Knowledge JiT.** If your workflow shares a principle with others, factor it into `src/knowledge/` and load it from the step rather than inlining the rule.
- **Quality review.** Before shipping, run the [BMad Builder](https://github.com/bmad-code-org/bmad-builder/) `quality-analysis` workflow on the changed skill; SKF validates its own workflows with it. With a [Tessl](https://tessl.io) account, `tessl review run <skill-folder>` adds an AI-judge review of the whole skill folder (each fresh review spends Tessl credits); `src/shared/references/tessl-review.md` lists the suggestions SKF does not follow.
- **Register the workflow** in `src/module-help.csv` (ordering / preceded-by / followed-by fields) and in the `docs/workflows.md` reference table.

## Adding Knowledge Fragments

Knowledge lives in [`src/knowledge/`](src/knowledge/) and is loaded just-in-time by workflow steps — never preloaded.

- Keep each file single-concern: zero-hallucination, confidence-tiers, provenance-tracking, version-paths, etc.
- Add the new file to the **Knowledge Map** table in [`src/knowledge/overview.md`](src/knowledge/overview.md) with its purpose and the workflow codes (CS, QS, US, ...) that consume it.
- Reference it from the step that needs it with a `Load:` directive (see any `references/step-*.md` for the pattern).
- If the principle cuts across ≥2 workflows, it belongs in `knowledge/`. If it's step-scoped, it belongs in the workflow's `references/` instead.

Forger-sidecar (`src/forger/`) is Ferris's own memory: `preferences.yaml` and `forge-tier.yaml`. Changes here should be rare and tied to a real behavioural change in a workflow.

## Reporting Bugs

- **Normal bugs:** open a GitHub issue with a reproducer — input (URL / package / brief), SKF version (`npm ls bmad-module-skill-forge`), capability tier Ferris reported at setup, the error or wrong output, and what you expected. The bug-report template in [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/) prompts you for the rest.
- **Workflow friction:** every SKF workflow ends with a health-check reflection step that can file a GitHub issue on your behalf. Reports are **auto-deduped by fingerprint** — the [`.github/workflows/health-check-dedup.yaml`](.github/workflows/health-check-dedup.yaml) Action extracts the `fp-XXXXXXX` label on a new issue, finds any earlier open issue with the same fingerprint, comments "duplicate of #N", upvotes the canonical issue to preserve the signal count, and closes the duplicate. Re-reporting is safe. If you skipped the terminal step in-session, ask Ferris: `@Ferris please run the workflow health check for this session`.
- **Closing out a health-check finding.** The reporter's machine keeps a global seen-cache at `$HOME/.skf/health-check-seen.json` that stops the same fingerprint being re-reported. Once a finding is fixed, that entry must stop suppressing, or a later **regression** of the same defect is silently swallowed — the one report the loop most needs to surface. Two mechanisms, in the order they actually fire:
  - **Close the issue as completed, and nothing else is required.** The health check reads the issue's own `state` and `stateReason`, and treats `CLOSED/COMPLETED` (or a `MERGED` PR link) as a regression trigger on the next sighting. Issue state is shared, so this works for every reporter, on every machine, with no action on their part. Closing as *not planned* deliberately does not count: that is how the dedup Action closes duplicates and how a wontfix is closed, neither of which is a fix.
  - **Only when there is no issue to close** — a finding that was only ever queued locally — hand-edit your own cache entry to `"action": "resolved"`, keeping `issue_url` and setting `date` to the fix date. This is machine-local, so it clears the suppression for you and nobody else. Prefer deleting nothing: `resolved` keeps the record that the defect was once seen, which is what lets the next sighting be reported as a regression rather than as a first sighting.

- **Provenance failures are always bugs.** If an AST citation in a SKF-compiled skill doesn't resolve to the claimed line at the claimed commit, that's the whole deal breaking — please file it.

## What We Don't Accept

- **Features that fork core BMAD conventions.** SKF is a module; it follows the framework. If your idea needs BMAD to behave differently, take it upstream to [bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) first.
- **Tests that mock the database / the real extraction pipeline.** SKF's validation is meaningful because it runs against real extraction output and real oh-my-skills skills. Mocks that hide that contract don't buy us anything.
- **Changes that bypass `npm run quality`** — skipping hooks, excluding files from linters, loosening a validator to make a PR green. Fix the underlying issue instead.
- **Documentation that duplicates external canonical sources.** Link out to [docs.bmad-method.org](https://docs.bmad-method.org), [agentskills.io](https://agentskills.io), tool docs, etc., rather than restating them. SKF docs are for what's unique to SKF.
- **Emoji in source files and docs.** Project standard. (Badges and contributor avatars in the README are the exceptions.)
- **Drive-by reformats.** Please don't reflow whole files or rename things you didn't touch.

## Code of Conduct and License

By participating, you agree to the [Code of Conduct](.github/CODE_OF_CONDUCT.md). Be decent; assume good faith; disagree with the argument, not the person.

Contributions are licensed under the project's [MIT License](LICENSE).

## Acknowledgement

SKF is maintained in spare hours. Good issues, small focused PRs, and willingness to iterate on review are the most useful things you can send. If SKF saved you an afternoon, a ⭐ or a [coffee](https://buymeacoffee.com/armelhbobdad) keeps the forge lit.
