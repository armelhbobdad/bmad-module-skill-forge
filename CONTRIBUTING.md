# Contributing to Skill Forge

SKF turns code and docs into verified agent skills. Every instruction traces back to a real line of source. See [README.md](README.md) for the pitch; this file covers how to land changes without setting the test suite on fire.

SKF is a [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module. For BMAD philosophy, framework conventions, and module-authoring patterns in general, start at [docs.bmad-method.org](https://docs.bmad-method.org). This doc stays scoped to what's SKF-specific.

## What You Can Contribute

- **Workflows** (`src/skf-*/`) — new skill-compilation or lifecycle flows. Example: a `skf-diff-skill` that compares two versions of the same skill and emits a migration note.
- **Knowledge fragments** (`src/knowledge/`) — cross-workflow principles Ferris loads just-in-time. Example: a new `security-review.md` that captures rules reused by CS, QS, and AS.
- **Forger assets** (`src/forger/`, `src/shared/`) — shared agent memory, preferences, or helpers (e.g. tier detection, health-check templates).
- **Validators** (`tools/validate-*.js`) — deterministic checks that run in `npm run quality`. Example: a new validator that flags `{installed_path}` leaks in step files.
- **Docs** (`docs/`, `website/`) — tutorial / reference / explanation content surfaced at [armelhbobdad.github.io/bmad-module-skill-forge](https://armelhbobdad.github.io/bmad-module-skill-forge/).
- **Ecosystem integrations** — new tool bridges (ast-grep, cocoindex, QMD, tessl, Snyk, graphify-style indexers) wired through the tier-aware discovery path.
- **Bug reports** — always useful, especially if they come in via the workflow health-check loop (see below).

If you're not sure where a change belongs, open an issue and ask before writing code.

## Local Setup

**Platforms:** Linux, Windows, and macOS. Linux and Windows are exercised in CI on every PR (`ubuntu-latest` + `windows-latest` matrix); macOS works in practice (POSIX-equivalent to Linux) but isn't CI-gated. On Windows, SKF transparently falls back to NTFS junctions when symlink privilege isn't held — no Developer Mode or admin rights required. Git Bash (bundled with [Git for Windows](https://git-scm.com/download/win)), PowerShell, and WSL2 all work.

**Prerequisites:**

- [Node.js](https://nodejs.org/) >= 22 (see `.nvmrc`)
- [Python](https://www.python.org/) >= 3.10
- [uv](https://docs.astral.sh/uv/) — runs the Python test suite
- `git`, `gh` — used by several workflows and by the health-check loop

```bash
git clone https://github.com/armelhbobdad/bmad-module-skill-forge.git
cd bmad-module-skill-forge
npm install           # also wires husky pre-commit hooks via "prepare"
npm run quality       # run the full local pre-flight
```

The `npm run quality` script is your contract with CI. It runs:

- `format:check` (Prettier), `lint` (ESLint), `lint:md` (markdownlint)
- `test:schemas`, `test:install`, `test:cli`, `test:workflow`, `test:python`, `test:knowledge`
- `validate:schemas`, `validate:skills`, `validate:refs`
- `docs:validate-drift` — SKF docs vs. the canonical [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills) output

If `npm run quality` passes locally, CI should too. The same steps run in [`.github/workflows/quality.yaml`](.github/workflows/quality.yaml) on every pull request.

## Workflow for Changes

1. **Branch from `main`.** Name it like the commit scope: `fix/skf-test-skill-...`, `feat/health-check-...`, `docs/...`.
2. **Match the commit-message convention from the git log.** SKF uses conventional-commit prefixes with a scoped subsystem:
   - `feat(skf-create-skill): ...`
   - `fix(health-check): ...`
   - `docs(readme): ...`
   - `ci(health-check): ...`
   - `refactor(skf-create-skill): ...`
   - `chore: ...` (no scope needed)

   `git log --oneline -20` is the authoritative style guide. Match what you see.

3. **Reference issues with `Fixes #NNN`** in the PR body (and optionally in the commit trailer). Use **same-repo GitHub issue numbers only** — do not reference internal IDs under `_bmad-output/todo/` or elsewhere; those are author notes, not public contracts.
4. **Pre-commit hooks run automatically** via husky + lint-staged: `eslint --fix`, `prettier --write`, and `markdownlint-cli2` on `.md` files. They run on staged files only.
5. **PR description:** explain _why_. What was broken, what does this change, and how did you verify it? Keep it honest and short. The template in [.github/](.github/) is a starting point; ignore the sections that don't apply.
6. **If you used Claude (or any AI assistant)** to help write a non-trivial chunk of the change, add a `Co-Authored-By:` trailer to the commit — SKF's recent history uses the format:

   ```
   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
   ```

   Not mandatory, but we prefer accurate attribution over silent ghostwriting.

## The Quality Gate

`npm run quality` must pass before you push. If it fails:

- **Fix the root cause.** Do not `git commit --no-verify`. Do not disable a rule to make the linter shut up. If a hook is wrong, fix the hook in a separate PR.
- **If a Python test fails on your machine but not in CI,** check your `uv` version and re-run `npm run test:python` from a clean shell.
- **If `docs:validate-drift` fails,** you either touched a pinned version/commit SHA that no longer resolves in [oh-my-skills](https://github.com/armelhbobdad/oh-my-skills), or you added a library reference the whitelist doesn't cover. Fix the reference; don't relax the validator unless the fix is clearly out of scope.

CI re-runs everything on the PR. A green local run and a red CI run means either (a) you have uncommitted files, or (b) your Node/uv versions drift from `.nvmrc` / `test:python`. Check both before filing a CI bug.

## Releasing

Maintainers only — if you're not cutting a release, skip this section.

- **Canonical path:** `.github/workflows/release.yaml`, triggered via GitHub Actions → Run workflow → choose `version_bump` (`alpha` / `beta` / `rc` / `patch` / `minor` / `major`). That is the only supported route — OIDC-backed publish, required-reviewer gate on the `release` environment, auto-provenance on the npm tarball.

See [docs/_internal/RELEASING.md](docs/_internal/RELEASING.md) for the full procedure — branch-protection rules, the `release` environment with its required-reviewer gate, npm Trusted Publisher registration, and the seven-scenario [rollback playbook](docs/_internal/RELEASING.md#rollback-playbook).

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
- **Quality review.** Before shipping, run a [tessl](https://tessl.io) skill review pass on the SKILL.md content — SKF uses tessl for actionability scoring and AI-judge evaluation (see the references under `src/skf-create-skill/assets/`).
- **Register the workflow** in `src/module-help.csv` (ordering / after / before fields) and in the `docs/workflows.md` reference table.

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
