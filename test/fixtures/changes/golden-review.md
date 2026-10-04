## Review before approving

v3.0.0 is a major step from v2.2.0; the change fragments and covered surfaces need at least major.

Approve only when:

- [ ] each breaking change says what stopped working and gives a migration a user can follow;
- [ ] each surface change below is described by a fragment of the right type, or needs no note;
- [ ] the notes below read well as the GitHub Release page (it adds Installation and the compare link).

### Why the minimum is major

- major: breaking fragment changes/setup-retire-write-failure.yaml (skf-setup)
- major: breaking fragment changes/update-read-only-flat-layout.yaml (skf-update-skill)
- major: hard surface change: skf-setup: schema enum value `write_failure` removed
- minor: added fragment changes/forger-campaign-code.yaml (skf-forger)
- minor: changed fragment changes/shared-folder-ownership.yaml (all workflows)
- minor: added fragment changes/update-target-ref.yaml (skf-update-skill)
- minor: added fragment changes/writers-ownership-exit-codes.yaml (skf-quick-skill, skf-create-stack-skill)
- minor: additive surface change: skf-update-skill: flag `--target-ref` added
- patch: docs fragment changes/docs-claim-by-claim.yaml
- patch: fixed fragment changes/packaging-maintainer-files.yaml (packaging)
- patch: fixed fragment changes/setup-quiet-envelope-only.yaml (skf-setup)

### Surface changes since v2.2.0

Hard (a breaking fragment names each one):

- skf-setup: schema enum value `write_failure` removed

Additive:

- skf-update-skill: flag `--target-ref` added

Review (never fails; decide whether each one needs a note):

- skf-setup: flag `--quiet` text changed

### [3.0.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v2.2.0...v3.0.0) (2026-10-01)

SKF 3.0.0 runs safely in a skills folder shared with other skills, reads a remote skill's source at the commit it tracks, and labels every provenance entry by the tool that read it. Three behaviours a pipeline can depend on changed: read Breaking changes before you upgrade one.

#### Breaking changes

- **skf-setup:** The `SKF_SETUP_RESULT_JSON` envelope no longer lists `write_failure` as a `status`. No run ever produced it: a failed write of `forge-tier.yaml`, `preferences.yaml` or the forge data folder has always ended with `status: "blocked"`. The schema now matches, and `status` is `blocked` exactly when `error` is not null. ([#509](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/509); issue [#502](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/502))

  **Migration:** If a pipeline tests for `write_failure`, test for `blocked` and read `error.phase` instead: `step 2:write-tools`, `step 2:init-prefs` and `step 2:forge-data-dir` name the three write failures. The other fields of a blocked envelope are placeholders.

- **skf-update-skill:** `--detect-only` and `--dry-run` now stop when the skill still uses the old flat layout (`<skills folder>/<name>/SKILL.md` with no version folder). Before, they first moved the skill into the versioned layout, a write in a mode that promises to write nothing. The run ends `blocked` with `error.phase` `init:read-only-flat-layout`, and nothing is moved. ([#499](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/499); issue [#497](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/497))

  **Migration:** Run `@Ferris US <skill>` once without the flag (or run `AS`, `TS` or `EX` on the skill) to move it into the versioned layout, then re-run with `--detect-only` or `--dry-run`. Skills already in the versioned layout are not affected.

#### Added

- **skf-forger:** Typing `CA` to Ferris now starts Campaign, matching the `[CA] Campaign` entry bmad-help already showed. Campaign still cannot be chained with other codes in a pipeline. ([#523](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/523))
- **skf-quick-skill, skf-create-stack-skill:** New exit codes for pipelines: Quick Skill exits `9` and create-stack-skill exits `5` (state-conflict) when they refuse to write into a skill folder SKF did not generate (`not-skf-output`) or into an SKF skill still in the old flat layout (`flat-layout`). create-skill stops with the same two reasons, and a create-skill batch moves on to the next brief. Nothing is written into the refused folder. ([#509](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/509); issues [#500](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/500), [#501](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/501))
- **skf-update-skill:** New `--target-ref <ref>` flag for a skill built from a remote repository: update it against a tag, branch, `HEAD` or full commit instead of the ref it recorded, for example the newer tag an audit checked out. When the update writes, the skill records that ref and the commit it read, and the audit report now suggests the flag after it checked out a newer ref. ([#517](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/517); issue [#511](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/511))

#### Changed

- **all workflows:** SKF now moves, updates, renames or deletes only the skills it generated (their `metadata.json` carries the SKF marker), in both `skills_output_folder` and `forge_data_folder`. A shared skills folder is supported: for a skill SKF did not make, update, export, audit and test stop with `not-skf-output` instead of migrating it, and drop and rename refuse it. Rename also stops with `flat-layout` on an SKF skill still in the old flat layout and says to run `TS` on it once. create-skill now stages its work in `_bmad-output/.skf-stage/<name>/`. ([#499](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/499), [#509](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/509); issues [#495](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/495), [#497](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/497), [#500](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/500), [#501](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/501))

#### Fixed

- **packaging:** The npm package no longer ships maintainer-only files (the v1.0.0 release audit, the release runbook and two docs validators), about 150 KB less. ([#489](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/489); issue [#487](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/487))
- **skf-setup:** Under `--quiet` or `--headless`, the `SKF_SETUP_RESULT_JSON` envelope is now the only line setup prints, halts included, as the docs promised. `--quiet` no longer stops at the orphan-collection question: it keeps the collections and records `quiet-default` in the envelope warnings. ([#499](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/499); issue [#494](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/494))

#### Documentation

- The published docs were checked claim by claim against the code. Corrections include: Python 3.11 is the minimum, not 3.10; `gh` is needed for Campaign and `forge-auto --pin`, not only for the Deep tier; Ferris starts with `/skf-forger` (`$skf-forger` in Codex, `/skill:skf-forger` in Pi); and bmad-help and `_bmad/custom/` overrides need the BMAD Method in the project. ([#522](https://github.com/armelhbobdad/bmad-module-skill-forge/pull/522))
