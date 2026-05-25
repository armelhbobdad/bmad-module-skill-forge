# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.8.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.7.0...v1.8.0) (2026-05-25)

### Features

* **skf-analyze-source:** support composite sources and composite unit merges ([3158b14](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3158b14aacd42895dc4d05737e4c6292f022407c)), closes [#405](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/405) [#406](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/406)

### Bug Fixes

* **shared/scripts:** close three health-check gaps (CCC registry, token gate, specific-modules) ([5470ba9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5470ba951e7b1147e7021dd0789243e1731ac527))
## [1.7.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.6.0...v1.7.0) (2026-05-25)

### Features

* **skf-brief-skill:** add from_brief headless arg to ratify a pre-authored brief ([f6cfebf](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f6cfebfa8a0bb8b2291772a540ef6932f3b3f8df)), closes [#383](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/383)

### Bug Fixes

* **installer:** write output_folder to generated SKF config ([77f18c3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/77f18c3f82693cbb53d336798937c75f32004955))
* **shared-scripts:** parse current qmd collection list output in classifier ([5395e16](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5395e16d689a5c2bfec21dcd92a75e266560ef3f))
* **shared-scripts:** write atomic temp files in binary mode on Windows ([f007a26](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f007a268d91d8cc76e2c19dc82212d437ff6a349))
* **skf-analyze-source:** recognize reference-app scope type in briefs ([9dbc1f7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9dbc1f717aa778d93123425798af29df4459f996))
* **skf-analyze-source:** validate generated briefs with the deterministic schema check ([6cc495b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6cc495bdfb6bfea7b8da7ef67544832138b5f956))
* **skf-brief-skill:** analyze pinned target_version at its git tag, not HEAD ([9f357f7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9f357f75fe0fd13da3547736bf8b19478e3ce5fc))
* **skf-brief-skill:** capture tier_a_include for coarse-glob monorepo subsets ([a8ebd2f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a8ebd2f2221c9a6b0b0f40bd1dafd5d35550c3d8))
* **skf-brief-skill:** document monorepo subpackage scope convention ([b0fcdd8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b0fcdd80e3c8644492636092bde262e1a402cd83))
* **skf-brief-skill:** give workspace manifest_kind precedence in language detection ([1d19385](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1d19385c68dfb276925933afe67f3f2500c8d9e3))
* **skf-brief-skill:** harden portfolio-similarity check for qmd output and scale ([5895c79](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5895c79d04fb38e473f81ebe9d97001d3acf7aaf))
* **skf-brief-skill:** round-trip target_ref/tier_a_include/amendments on brief re-write ([831fcd6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/831fcd6756a9ff30d624671b1844a53b700135ff)), closes [#385](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/385)
* **skf-brief-skill:** warn when a cross-ecosystem workspace manifest is dropped ([619ec92](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/619ec92e684a780d0df898080b16bbe42f9486f2))
* **skf-create-skill,skf-test-skill:** persist scope_type so reference-app scoring fires ([bad5423](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bad5423a4f9df9a495fab91a83b806e54e16e82d))
* **skf-create-skill:** correct ast-grep 0.42.x TypeScript export recipes ([b42308c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b42308cf361e95590c38bf8278bb36f45270411c)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9)
* **skf-create-skill:** define named-export counting unit and ccc init prerequisite ([8b5e531](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8b5e531b5cf96729f8e5e8382558adb876d0c8e0))
* **skf-create-skill:** dismiss tessl "remove provenance annotations" suggestion ([ce02b72](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ce02b72c84738587aed1ae7f01b4df99f60e6c97))
* **skf-create-skill:** gate description recovery on deterministic validator, not judge score ([86bc1be](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/86bc1be5874bc7dc34de8c40d3d59e3237d7a7c0))
* **skf-create-skill:** omit effective_denominator for reference-app scope ([2edcf00](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2edcf00d20641658312a7c68cb77dc899c6ce456))
* **skf-create-skill:** resolve monorepo crate tags in source resolution ([95a48d0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/95a48d06ef13a210dfdfff723aa782fc510497e1))
* **skf-create-skill:** resolve package exports map for entry points outside src/ ([4f21275](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4f21275647f9380bd7c046e11564899d2eb796ce))
* **skf-create-skill:** verify ccc index has source-language chunks ([8737d88](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8737d88ebccbb9f860e21431e23f4ec7cc8cbd93))
* **skf-create-stack-skill:** align compose-mode provenance confidence and stack version ([62376f5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/62376f592ab80f8fe925ff4b174572a157d69cd9))
* **skf-create-stack-skill:** extract library catalog for large stacks ([bdf845f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bdf845f5eefddac7fdf564af5540c0697bb1a147))
* **skf-create-stack-skill:** gate frontmatter before publishing the package ([4c6f024](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4c6f024044dffcb6341be6323e83e95374570f90))
* **skf-create-stack-skill:** pre-check SKILL.md body size before commit ([e6f5390](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e6f5390300e22f212f8bd8bc0bcd965ced6b9c27))
* **skf-create-stack-skill:** version re-composed stacks from prior release line ([edbe84a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/edbe84a3c603d917c462ca809eb5b5b63132dbe6))
* **skf-enumerate-stack-skills:** resolve version-nested skill layout ([62a94a1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/62a94a185b11fe378f83c1242bdb7f34c35c491a))
* **skf-export-skill:** correct helper-contract docs in update-context ([b219ee8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b219ee8ce2d7d110aa5112166b4f65e4b1dc91ca))
* **skf-export-skill:** exclude shared managed section from package total ([3b578c3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3b578c322fea9bb65d66fcf75cf20f8a73aca106))
* **skf-export-skill:** make managed-section writes atomic and verified ([7b7ba77](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7b7ba77f9e39591ad9d65db26f47235b4f689dde))
* **skf-export-skill:** open atomic-write temp file in binary mode ([b597a72](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b597a72680387ca51ed675031198bbe44037e88a))
* **skf-export-skill:** pass managed-section content via stdin to avoid shell expansion ([41240b8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/41240b85119d01d23de66c047004afc365dbfacf))
* **skf-export-skill:** prevent managed-section wipe and marker duplication ([635d164](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/635d164fa2f36e8e22534d19e7c4ff85117f1acb))
* **skf-manifest-ops:** archive all stale active versions on set ([7327187](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/732718749db2dae9bb098e49810e8475616bf482))
* **skf-quick-skill:** invoke frontmatter validator via uv run ([3e6f0b6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3e6f0b6a100127c7252419d226764b4740c71e2c))
* **skf-quick-skill:** point context-snippet anchors at real QS headings ([3f15203](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3f1520367b0eeb6015a7d8b3a450d3af1054b3fb))
* **skf-refine-architecture:** scope gap/issue analysis to the document's surface ([621be1b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/621be1b02e5ef763b852be3e9214b0bd5d46a416))
* **skf-skills:** read skill-check score/counts from correct JSON paths ([ecee0a3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ecee0a339e073eb8aceff09b18371bee9cdb105e))
* **skf-test-skill,skf-export-skill:** prefer active symlink when manifest lags ([e7ee0e9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e7ee0e953605b5017f91ee6135ee5f491b52c674))
* **skf-test-skill:** accept quick-skill headings in structural-scan gate ([79b9208](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/79b9208a1248c3f84df2e3aa1f5a8904448a4858))
* **skf-test-skill:** accept stack/Rust export kinds and stack cross-refs ([753bb38](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/753bb38644fabe704a1af55ede54ac7e10ea9238))
* **skf-test-skill:** add Rust grep fallback for deflation-guard barrel re-derivation ([441a788](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/441a7882d360d3b9c41189a10e50ecd5cbc41113))
* **skf-test-skill:** add stack-skill branches to coverage scoring ([d411e88](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d411e881d9f4d47075f48fd57afeb09407be59c0))
* **skf-test-skill:** guard non-git auto-reuse against date-only timestamp collision ([ff88b2b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ff88b2bb00084d94aa4632518ba597535e93c116))
* **skf-test-skill:** handle scalar denominator and normalize method entries in coverage check ([3b0ac63](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3b0ac63f35cd9310bbd1713a7aa7fa7fbf324f13))
* **skf-test-skill:** harden coverage check against gaming, spot-check, and split-body gaps ([6aef61d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6aef61d80c61396414cc935d874cf69ec33fce08))
* **skf-test-skill:** match Pattern Surface / Adoption Steps in structure scanner ([b074435](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b074435bd1960a3a35ebfdaaff43bb6061b78545))
* **skf-test-skill:** re-derive TS barrels across multi-line export blocks ([829c58d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/829c58d890e901775a7feab108825c15e8a571f3))
* **skf-test-skill:** wire reference-app skip flag in scoring ([4c5c23d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4c5c23d9c1358194369d8b6972551eefe423d620))
* **skf-update-skill:** add gap-driven change categories for structural, metadata, provenance-completeness, and rescope gaps ([9b19475](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9b19475778a90a7435e7337e2ab048ff00899b88))
* **skf-update-skill:** gate gap-derived exports on public reachability ([8cd60ce](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8cd60ce0f2884974b37737232d26fd061455904a))
* **skf-verify-stack:** distinguish deliberately-removed tech from skill gaps ([5983fba](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5983fba4ee918e48f74344d60ce9380e47d19f31))
* **skf-verify-stack:** resolve feasibility schema ref via probe order ([935e03c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/935e03c742d8c222adcdcb5a78b5e1342ff5bac9))
* **skf:** write health-check local queue to forge_data_folder ([206bbb9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/206bbb9b2fbd3079ff0c5bdf3a4dc4a3b6762a73))
## [1.6.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.5.1...v1.6.0) (2026-05-21)

### Features

* **skf:** ratify existing skill-brief.yaml in brief-skill ([bac2072](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bac207201aa7ba522d85030904a96cd35b98915e))

### Bug Fixes

* **shared:** YAML round-trip in description-guard restore ([a56fc3b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a56fc3bebad085ffb29948b9eeb84a069776b01a))
* **skf:** resolve test report by glob in update-skill --from-test-report ([150fbbd](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/150fbbdc14eecae95c065bebd4ba7514216cb1bc)), closes [#299](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/299)
* **skf:** route resume after generate-briefs to health-check ([402e0ca](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/402e0ca3c51d993713169acb432d34d8c357d52a))
## [1.5.1](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.5.0...v1.5.1) (2026-05-20)

### Bug Fixes

* **skf:** bound detect-tools probes so a hung daemon can't stall it ([f6c4960](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f6c4960da190cfac597e9115237a087b4b7b002c))
* **skf:** correct analyze-source roots and manifest IDE recording ([facde71](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/facde7110aeee4f0e9835c56e9587416635a8cbc))
* **skf:** correct step-file instructions surfaced by health checks ([fc4fbfc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/fc4fbfc877703ecce704e07b468e2719872b4582))
* **skf:** prevent npx install hint from being parsed as github org/repo ([b5b4d86](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b5b4d86226f84eaecd294b37c174eeb62df2e0ad))
* **skf:** restrict detect-tools timeout wrapper to POSIX ([a2415e8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a2415e8b2caa2b544f2468c53f8198ea8792ddf7))
## [1.5.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.4.1...v1.5.0) (2026-05-18)

### Features

* **shared:** extract §1c discovery/parse/reconcile pipeline ([cdaaebc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cdaaebcd71cab515e58f66f90108316423459f63)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract §2a Authoritative Files Protocol (last of 9 extractions) ([68b039e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/68b039eb1c44d5f13f61ee4d5b7f96447a7ae746)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract atomic active-symlink flip for update-skill §5b + §6 ([17378a8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/17378a8111cb2bc863279f6efeb12b357ef7d540)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract brief schema validation + wire 4 latent test files into CI ([602a35e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/602a35e5e3f52c31616219636365396e240ff8da)), closes [#308](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/308) [#309](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/309) [#310](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/310) [#308](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/308) [#309](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/309) [#310](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/310) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract change-manifest aggregation + §2.2 deletion-ratio trigger ([95c55d7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/95c55d73fc6886f846d1c76648ce6714f39d42df)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract Description Guard into shared script + protocol doc ([033a55a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/033a55a24f5ebf2e85a87966bddd761de6bf9d1c)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract scripts/assets detection from create-skill step 3 §4c ([ccf803c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ccf803cd8a79b6ace1fb1bb91c362450596eb00a)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract SHA-256 hashing helpers from update-skill detect-changes ([b0d2f7f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b0d2f7f81a0bc014003f3b93754fbf7eee413631)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **shared:** extract workspace-drift guard from update-skill §0.a ([25cf006](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/25cf006f71811f49f2a677a1eaef76c0cab52df2)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **skf-brief-skill:** capture authoring-time scope.rationale ([a912044](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a9120446bd27e99beeded0c0fdad03fea4d8b863))
* **skf-brief-skill:** wire customize.toml path scalars (closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) D1) ([f21b8fe](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f21b8fe3f27e5cdb3530c68b5b997b585604cd5c)), closes [#306](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/306)
* **skf-drop-skill:** blast-radius summary line in §10 confirmation gate ([b634682](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b634682c6e4b3672680fd3aa2e0d9d0428b74b91)), closes [#331](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/331)
* **skf-feature:** extract 7 deterministic operations to shared scripts + modernize compute-score CLI ([883d348](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/883d348daf0cf13fe236d5395ed1dfaa5965e353)), closes [#325](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/325) [#325](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/325)
* **skf-feature:** surface extensions, structural carves, resume protocols + polish ([81992cd](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/81992cd96afb85ea64489fc683a9835b07216379)), closes [#325](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/325) [#324](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/324) [#326](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/326) [#327](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/327) [#325](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/325) [#326](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/326)
* **skf-setup:** tighten headless contract, add CLI knobs, ship customize.toml ([3dd864c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3dd864cd8807b4dd975d563bde50056e9f85957a))
* **skf-update-skill:** add --dry-run and --detect-only inspection modes ([56dd717](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/56dd717fc3d8eb3e1ca3866caab8025152292f77)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **skf-update-skill:** add PID-file concurrency guard against double-invoke ([a8d8147](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a8d81478743ac4054b708640aebc2946437f651c)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
* **skf-update-skill:** add SKF_UPDATE_RESULT_JSON envelope + headless_decisions[] ([f1b19be](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f1b19be6aa2876335bc62477d1f508a615546485)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)

### Bug Fixes

* **shared:** normalize path separators in JSON output for cross-platform CI ([d6b4de5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d6b4de5d2d1a18958cf8fc364e9dcaa66336dbcf)), closes [#309](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/309) [pre-#311](https://github.com/armelhbobdad/pre-/issues/311)
* **skf-export-skill:** iterate orphan-row probe across all target context files ([35b0b2e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/35b0b2ea795696530f343a1b24e930d544f21096)), closes [#331](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/331)
* **test:** assert path.as_posix() in --include-path tests for Windows CI ([21e9470](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/21e9470f45d136548ab5f5cf3aee1d74ec2b2fb0))
* **test:** use as_posix() for cross-platform path assertion in pruning test ([2c06c71](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2c06c7162d8b45599ff6fa8f2e371a4094d21c76)), closes [#311](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/311)

### Performance Improvements

* **skf-create-skill:** parallelize fetch-temporal + fetch-docs network ops ([4d31c4b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4d31c4b93a4e021efa42dc2dc53089cf30f4b0c7)), closes [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#307](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/307)
## [1.4.1](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.4.0...v1.4.1) (2026-05-07)

### Bug Fixes

* **skf-audit-skill:** gate manifest-vs-symlink drift in step-01 §1 ([41854df](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/41854dfe96beb10655480696f043583b1a960ca7)), closes [#296](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/296)
* **skf-audit-skill:** handle dirty worktree in step-01 §5b checkout handler ([1f4529e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1f4529e84a24333b8d38f8d412ea6c984df30d92)), closes [#295](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/295)
* **skf-audit-skill:** normalize sha256: prefix in step-03 §4b hash comparison ([cbae8aa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cbae8aa2a98a376f44d5b360fd22aaab93e67f8f)), closes [#294](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/294)
* **skf-create-skill:** allow empty references/ when Tier-2 is inline ([b503f5e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b503f5e5e8f9916b7c38e644bc138ac9bbf04b7b)), closes [#292](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/292)
* **skf-export-skill:** document deviations[] on result contract for §4c.1 ([3a37829](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3a378299ab3c85928fd2a988dc7edbac1d747d5e))
* **skf-export-skill:** glob timestamped test reports in step-01 §4b ([f218522](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f2185222f46cff345a7c051d0b23209cf4d234f9)), closes [#299](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/299)
* **skf-export-skill:** handle manifest-orphan managed rows in step-04 §4c ([c6666c3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c6666c387ff18b039457ee0531793ecd849e20a9)), closes [#297](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/297)
* **skf-export-skill:** treat first-export gotchas as fresh in step-03 §3.5 ([c804264](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c80426426a8231fba1829b3da00337ac3fb5c3a6)), closes [#298](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/298)
* **skf-setup:** reject {project-root} placeholders in ccc-exclusions merge ([b418dca](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b418dca8c61bd8c45772c4e3881acd4169d23fef)), closes [#293](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/293)
## [1.4.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.3.0...v1.4.0) (2026-05-02)

### Features

* **extract-public-api:** detect release-time placeholder versions and surface as warning ([50d9c5c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/50d9c5c3e62d1bd9ffcdfcffcf5e9c24707eafc5))
* **shared/scripts:** add register-qmd-collection subcommand to skf-forge-tier-rw ([83b7d94](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/83b7d9488b48c3648895cb91c95c3f43fae48c1b))
* **shared/scripts:** add skf-detect-language.py — deterministic primary-language detection ([dae7b10](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dae7b102f649d07800f7e99304d76a0763ecfe4e))
* **shared/scripts:** add skf-detect-workspaces.py with JSON Schema and 35 tests ([014c135](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/014c1359da8b19f5170121d72aa21a6ddb5aa2ac))
* **shared/scripts:** add skf-emit-brief-result-envelope.py with JSON Schema ([3bcbc0d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3bcbc0dbf275ac43b723cea26ee1513ba6c16122))
* **shared/scripts:** add skf-recommend-scope-type.py — single source of truth for the 5-rule heuristic ladder ([13e0996](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/13e0996cd9e05319eee18d7e08b32c3361361766))
* **shared/scripts:** add skf-validate-brief-inputs.py with full test coverage ([377ebb0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/377ebb0e58b41027280f5b26bf8766072b5010e3))
* **shared/scripts:** add skf-write-skill-brief.py with JSON Schema and 63 tests ([6142327](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6142327a577de1754e1c55c1390cdaf5173715b5))
* **skf-brief-skill:** accept cancel/exit at §3.1 target prompt ([121adfb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/121adfb76a1cfff9400286e9173f5b10039c82b7))
* **skf-brief-skill:** add --preset headless arg for repeated-pattern briefs ([30ed499](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/30ed4997a711703efd79bf5487c5c959bde0765c))
* **skf-brief-skill:** add 'looks like' concrete examples to each scope-type entry ([62b5a0c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/62b5a0c96005133e55904dcf68f1693041245074))
* **skf-brief-skill:** add 'wanted something different?' disambiguation rail to welcome banner ([2bc6d3b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2bc6d3b243fa53ece7986f550f6e1ec19b87d5b2))
* **skf-brief-skill:** add [X] Cancel and exit affordance with stable exit code 6 ([c44cc55](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c44cc55d461a194699e4512a3cc74b520f22eeea))
* **skf-brief-skill:** add 50ms pre-flight write probe at step-01 §1 ([caaab46](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/caaab468196d59b986633ae2f086f52fc6facd21))
* **skf-brief-skill:** add explicit description synthesis with confirmation ([0d49598](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0d495986e3821582c6c30988449cba4e1ccce523)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1)
* **skf-brief-skill:** add gh api repos access probe to §3.3 parallel pre-flight batch ([d1dd5de](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d1dd5de9cb4746618c44c2fe9622902edd9df042))
* **skf-brief-skill:** add QMD portfolio-similarity check at step-01 §6 (Forge+/Deep) ([a081037](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a0810378939c4ffbfe230257309c31f607f7027d))
* **skf-brief-skill:** add routing-purpose microcopy at description synthesis and review sites ([d1941bf](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d1941bf80ea077456b78c7840971528f15108559))
* **skf-brief-skill:** add soft sentence-count check on synthesized description in §7b ([145caaa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/145caaa066f348af056406c577b0f757ee55f6b6))
* **skf-brief-skill:** always show scripts/assets/forge-tier with one-line glosses in step-04 ([a7f67f9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a7f67f930c44c3ff9e7629178ee13f81062eac1d))
* **skf-brief-skill:** auto-suggest alternates on brief-name collision in step-01 §6 ([7b44c19](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7b44c19ba7fd63ad56aeabfbb81d8ed567c8eed2))
* **skf-brief-skill:** detect headless source_authority from gh api user vs repo owner ([530162e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/530162e98112d8a0d648048684906c1ca14217d8))
* **skf-brief-skill:** diagnostic-on-failure at HITL gates ([45797cc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/45797cc69e8203f2261a32895a7ea9701f149431))
* **skf-brief-skill:** expand headless contract — args, JSON result, overwrite policy ([840ee8b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/840ee8bd73bc678c8d1f8f58a5cbf2f0b81061e6))
* **skf-brief-skill:** gloss the forge tier in step-01 welcome banner ([0478acb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0478acb8850729e910363363fce3590734a55694))
* **skf-brief-skill:** offer 'show me an example brief?' rail before §4 intent prompt for first-timers ([f130da9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f130da96c593572abc24b83bda1c0a57df14ac4b))
* **skf-brief-skill:** persist .brief-draft.json checkpoint and offer Resume? on re-entry ([942eba5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/942eba5134fcd0f9aafb5ca243b19293ae33da91))
* **skf-brief-skill:** pin language directive in every step's Rules block ([4068ba3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4068ba39fd81a33e80de1b6d11ebfb52a7d8e0b4))
* **skf-brief-skill:** pre-validate repo URLs and gh auth at point of capture ([0b0e6c5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0b0e6c597a9f2c7492d7972106d14fa242d4a72c))
* **skf-brief-skill:** recommend a scope-type instead of presenting five equal options ([29071d3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/29071d3fe568594941d9dae1acb0608aacdd1a31))
* **skf-brief-skill:** regex-validate target_version semver at point of capture ([7ea24f0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7ea24f04ee131b4380ef83c6ce6fe2a11c472f8c))
* **skf-brief-skill:** replace step-01 §7b description template with voice-varied examples ([abe459d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/abe459d97058201a76be9304b17d17e96417213e))
* **skf-brief-skill:** run scope-type recommendation in headless instead of stamping full-library ([9d54230](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9d54230e8222b1c7429f32f905f1df182604659e))
* **skf-brief-skill:** seed headless §7b description from GitHub repo description when intent is missing ([0b5397f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0b5397f38607bdb3d9f98859a342d6df5422604f))
* **write-skill-brief:** add --from-flat input mode for prose-driven callers ([bddd035](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bddd03587369f2a622deee368c60edd5a672d977))

### Bug Fixes

* **skf-brief-skill:** add explicit Completion criteria to terminal step-06 ([d56586e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d56586efac94db358429badadcaeec2a183c19ed))
* **skf-brief-skill:** address in-PR code review findings ([bfa9495](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bfa9495e71536aaf04d472259b0a0aa9963b7f86)), closes [#275](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/275)
* **skf-brief-skill:** close contract gaps for [X] cancel and write probe ([6fb5df2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6fb5df2018e0851ff26ca305f27a949b84085fe2))
* **skf-brief-skill:** correct QMD CLI surface, tier guard, resume-jump skip, preset KNOWN_FIELDS ([df788e9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/df788e9c045bcf248f13a35912b692bc1448dd9b))
* **skf-brief-skill:** first-timer rail — concrete find command + match prompt to actual content ([a638b98](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a638b988a7efebdfe6f560c5435731d86e96d144))
* **skf-brief-skill:** mark step-06 as terminal with completion sentinel ([60846c2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/60846c2909c12704de951f44ad54194073072fa2))
* **skf-brief-skill:** prefix bare _bmad/ path with {project-root} ([e9ea448](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e9ea448f3fff3c6d84ccd7fe74e5ce8c7333dfaf))
* **skf-brief-skill:** propagate input-invalid halt_reason and add priority test ([f36eea3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f36eea35f8722b495c928a5b1f4d8919537dc829))
* **skf-brief-skill:** remove parent-dir frontmatter paths and home-dir reference ([753a748](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/753a748444fec7c30839768d20fe8ab0cdda1119))
* **skf-brief-skill:** unblock headless heuristics — validator default, GATE placement, contract docs ([e931d05](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e931d054b433c278e633ea3a6dda1afc0a9e08e4))
* **skf-brief-skill:** wire new test file into test:python + instruct LLM to fetch registry contents at §2c ([771e3d0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/771e3d0d5b4958a36d95accb2b999a27782cdbc8))
* **skf-detect-workspaces:** correct lerna default, generic-folder accumulation, python libs layout ([7d1d23c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7d1d23c7511992dad061301720decb602a0aa53a))

### Performance Improvements

* **skf-brief-skill:** batch doc_urls HEAD checks in parallel with timeout ([cb57d16](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cb57d162ef75a3ea46f838c95257dfc26c1351d1))
* **skf-brief-skill:** batch gh api calls in parallel in step-02 ([1f38474](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1f3847421fe28123e0c6639ea02f6a8c6a5d168a))
* **skf-brief-skill:** codify lazy reference loading and tighten version-resolution load ([f9c88a2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f9c88a2bb168fbb6afa4c8957ad1acfdfd59498e))
## [1.3.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.2.0...v1.3.0) (2026-05-01)

### Features

* **shared:** add --skip-frontmatter flag and Description section to skf-validate-output.py ([6154a40](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6154a40ab22d2bd0ffe4197d044555cb373fef3c))
* **shared:** add skf-extract-public-api.py — pure-parser extraction across 6 languages ([fcdd2c0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/fcdd2c03247020592fbc94626fe428d1acdec2e4))
* **shared:** add skf-render-quick-metadata.py — pure metadata.json renderer ([3515901](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/35159019c2271214a2d9cbc1ff5d5ee0cbc9b2ca))
* **shared:** add skf-resolve-package.py for npm/PyPI/crates GitHub URL resolution ([f2800fa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f2800fa98955171d30fc30c2b5387639a7859417))
* **skf-quick-skill:** add --batch and --fail-fast flags to On Activation overrides ([d3f719b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d3f719ba9f6cfaf0dcdafb75e0acc4a1e9852f88)), closes [#263](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/263)
* **skf-quick-skill:** add --description / --exports / --skip-snippet / --no-active-pointer overrides ([1a08559](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1a08559c1a286fd79c4579da531ba2fb4df89865))
* **skf-quick-skill:** add [E] edit, [S] re-scope, [Q] quit options to step-04 review gate ([cb2929e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cb2929ee818ef44aa7e99e680e81fad3f08ed513))
* **skf-quick-skill:** add repo-shape sniff between step-03 README read and manifest parse ([3cc0ca6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3cc0ca67913dcb9da140dd5618c20d806f764456))
* **skf-quick-skill:** add zero-exports soft-gate in step-03 §4.5 (rescue mode) ([0b66cde](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0b66cde90f6e1cadb91899fb2cb71e549b2b95e5))
* **skf-quick-skill:** document Batch Mode semantics, summary contract, and events ([a2e01a3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a2e01a345b48f138236c734df38e9a9c25aa03c9)), closes [#263](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/263)
* **skf-quick-skill:** emit step.start/step.done JSON events to stderr in headless mode ([d84d2bb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d84d2bb4734966b4966afff1fb5d6b833a7ad4b5))
* **skf-quick-skill:** redirect free-form prose input to sibling skills before registry lookup ([62cdd8b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/62cdd8b64156d1577ea1dcd88142d2ef2d69b9ec)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5)
* **skf-quick-skill:** surface ambiguous-language choice in step-01 §4 instead of silently picking ([77a549e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/77a549ee4b82c8012904c0723dc80ede25758f57))
* **skf-quick-skill:** verify [@version](https://github.com/version) tag exists before extraction in step-01 §3a ([a4daf1c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a4daf1c0dad679e4ada350521e8d81c9b6efb2b4))
* **skf-quick-skill:** wire batch context into step-01 §1 input handling ([1cb645c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1cb645c8905879856350b899e7846197c0f44d1c)), closes [#263](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/263)
* **skf-quick-skill:** write error-variant result contract on every HARD HALT ([ce836c3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ce836c3761082c8073f4794a25921dfa9c21b1ba))

### Bug Fixes

* **skf-quick-skill:** prefix bare _bmad/src refs with {project-root}/ ([e01db9f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e01db9f2843d474b0e6cd4cbc56319cd7dc6f68e))
* **skf-quick-skill:** resolve atomic-flip helper via probe order, not hardcoded src/ path ([ff6929a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ff6929a4624eb87b04f21ccbd1c7c8e98151cf57)), closes [#257](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/257)

### Performance Improvements

* **skf-quick-skill:** collapse sequential network reads into batched parallel fetches ([9f5a3d6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9f5a3d64fc03153ea696f87633b6b974c1b362fb))
* **skf-quick-skill:** replace step-04 §5 inline preview with one-line summary in headless mode ([e3e143e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e3e143ebe118287db8687155d3bd5c279d90a030))
## [1.2.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.1.0...v1.2.0) (2026-04-27)

### Features

* **shared/scripts:** add skf-detect-tools.py for parallel tool probing ([1dfbe6c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1dfbe6c3aa7c8ddbc5fc10705e2a767710d381f1)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#243](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/243) [post-PR-#248](https://github.com/armelhbobdad/post-PR-/issues/248) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1)
* **shared/scripts:** add skf-forge-tier-rw.py for sidecar YAML rw ([29856cb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/29856cb5b3cd9f5cd10019d55e6101766c42da51)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1)
* **shared/scripts:** add skf-merge-ccc-exclusions.py for SKF exclusion merge ([7a50308](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7a50308ee8d7bd0ef3a86b100d8a79b806e08103)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#248](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/248) [#248](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/248) [#248](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/248) [#248](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/248) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1)
* **shared/scripts:** add skf-qmd-classify-collections.py for forge-namespace classification ([f473e2e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f473e2e9696af0d2122d59a3a97de9dab5ba4e56)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#244](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/244) [#244](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/244) [#244](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/244) [#244](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/244) [#244](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/244) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1)
* **shared/scripts:** lock SKF_SETUP_RESULT_JSON envelope behind a script + JSON Schema ([e4b2bda](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e4b2bdae3c1192b0c5446d26530ae05c73364e90)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#247](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/247) [#248](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/248) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1)
* **skf-setup:** add headless JSON envelope and --require-tier enforcement ([b0fa247](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b0fa24796a539a5af04456e88a9e2d16abe85be9)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5)
* **skf-setup:** close human-experience completion gaps ([fef1c65](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/fef1c653663aa00643398b015f519e048ab56dd7)), closes [post-#247](https://github.com/armelhbobdad/post-/issues/247) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2)
* **skf-setup:** close human-experience polish themes (uv probe + tier defuser + headless banner suppression) ([3b802f2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3b802f2bb9e77786df31ee1a89ae29adea6f9aae)), closes [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [post-Theme-#1](https://github.com/armelhbobdad/post-Theme-/issues/1) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [251/#252](https://github.com/251/bmad-module-skill-forge/issues/252) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3)
* **skf-setup:** close low-severity edges (missing-config diagnostic + tier-override fuzzy match + ccc-doctor climb hint) ([d717cc6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d717cc64787d249ef82b18bf624a51d4d6292cfe)), closes [#248](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/248)
* **skf-setup:** close tier communication gaps in status report ([cd03165](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cd0316593e47256d62cab51605842711dd83bb24)), closes [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#10](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/10) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12)
* **skf-setup:** extend headless envelope and document exit-code contract ([856aa31](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/856aa31a404b0f10293372dfc1f4a6f9bc3f6ca5)), closes [#247](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/247) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4)
* **skf-setup:** harden edge-cases around config values ([7066f92](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7066f92bcd8cc733dc79da081cfafcf03088ff18)), closes [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3)

### Bug Fixes

* **shared-scripts:** invoke pyyaml-dependent helpers via uv run ([cf8f0f6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cf8f0f646b135e176880060efe268f91f5663bd1)), closes [#251](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/251) [#251](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/251) [#251](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/251)
* **skf-setup:** invoke shared scripts via uv run so PEP 723 deps resolve ([ec23ac7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ec23ac7c80276fcb85d3ceb197d2c05505096c84)), closes [#251](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/251) [post-PR-#251](https://github.com/armelhbobdad/post-PR-/issues/251)
* **skf-setup:** reconcile autonomy claim with step-03 orphan prompt ([a777b04](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a777b048222d5be33ec6f3882c592921b7a83480)), closes [#245](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/245)
* **skf-setup:** scope orphan detection to forge-managed collections ([547f1b5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/547f1b56d7966f85a4a4cdf2e890900c464f60af)), closes [#244](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/244)
* **skf-setup:** verify ccc binary identity to reject foreign tools ([38c44b7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/38c44b7abd569e497d9b8f14376539db40ba4665)), closes [#243](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/243)
## [1.1.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.0.0...v1.1.0) (2026-04-25)

### Features

* **release:** add post-publish install smoke workflow (Story 5.4) ([5b17847](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5b1784781fa259f5c698d274d580c9a08b9f33ae))
* **update-skill:** add major-version scope reconciliation ([#233](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/233)) ([48cdfc9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/48cdfc9d72d13c646ae65d9ccf080ba4c18ee2dd))

### Bug Fixes

* **audit-skill:** add rollup clause for high-volume uniform findings ([070d8b9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/070d8b9170c30c0f6fc79b0c256fa65978481ed2)), closes [#230](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/230)
* **audit-skill:** align step-05 rollup row to the 6-column severity table ([22dcc0c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/22dcc0c2baa4e6c37db3d800285bb3a0596a75b4)), closes [#230](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/230) [#230](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/230)
* **audit-skill:** close three workflow gaps ([#216](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/216), [#217](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/217), [#218](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/218)) ([#227](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/227)) ([#228](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/228)) ([a967e84](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a967e84c1d3ee93d45a3776411510460e73d559b)), closes [#171](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/171) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#release-environment](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/release-environment) [#npm-trusted-publisher](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/npm-trusted-publisher) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#8](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/8) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#6](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/6) [#10](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/10) [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#10](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/10) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#6](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/6) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#17](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/17)
* **audit-skill:** correct brief-gate framing for new entry points ([8c7aa90](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8c7aa9056b091974912aa12bbd58af4fd92610e6)), closes [#231](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/231) [#231](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/231)
* **audit-skill:** surface version preservation in update-skill recommendation ([0a005f0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0a005f0310566da70bd64839a39fdfb54559c52e)), closes [#231](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/231)
* **export-skill:** treat snippet_skill_root_override as the effective target prefix ([9fbeded](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9fbeded3c5217ebe198983c93bbda878179bc12e)), closes [#237](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/237)
* **release:** lock docs/_data/pinned.yaml.skf_version to package.json.version ([#226](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/226)) ([197c3fc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/197c3fc47f44d0bf011470d2f5e413d0839c23df))
* **release:** remove empty ${expr} literal from release.yaml comment ([3458d6a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3458d6afaf988bbee71110748545d440c6ba825e)), closes [#226](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/226)
* **test-skill:** accept fenced JSON in coverage §1a ([#235](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/235)) ([9efab2b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9efab2b0de0403d1ad27214e26713af4782c256a))
## [1.0.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v1.0.0-rc.3...v1.0.0) (2026-04-23)

### First Major Release

First major release of Skill Forge (SKF). Introduces the `INCONCLUSIVE` test verdict, atomic stack-skill writes, a shared feasibility schema across VS/RA/SS, and formalizes Linux/macOS-only support. Sets the stable contract for subsequent 1.x releases.

### Initial Release

Skill Forge (SKF) — an agent skill compiler that transforms code repositories, documentation, and developer discourse into [agentskills.io](https://agentskills.io)-compliant agent skills with AST-backed provenance.

### Highlights

- **1 agent** — Ferris (Skill Architect & Integrity Guardian) with 5 workflow-driven modes
- **14 workflows** — full lifecycle from source analysis to ecosystem-ready export, with pre-code architecture verification
- **Progressive capability tiers** — Quick (baseline), Forge (+ast-grep), Forge+ (+ccc), Deep (+gh+qmd)
- **Source-traced instructions** — every documented symbol cites an upstream file and line
- **Dual-output strategy** — active skills (SKILL.md) + passive context (context-snippet.md) in ADR-L v2 format
- **CLI installer** — `npx bmad-module-skill-forge install` with skill directory installation for 23 IDEs
- **14 knowledge fragments** — curated cross-cutting principles loaded just-in-time by workflows

### Workflows

| Trigger | Name                | Purpose                                                            |
| ------- | ------------------- | ------------------------------------------------------------------ |
| SF      | Setup Forge         | Initialize forge environment, detect tools, set tier               |
| AN      | Analyze Source      | Discover what to skill in a large repo                             |
| BS      | Brief Skill         | Design a skill scope through guided discovery                      |
| CS      | Create Skill        | Compile a skill from brief with AST extraction                     |
| QS      | Quick Skill         | Fast skill from package name or GitHub URL                         |
| SS      | Stack Skill         | Consolidated project stack skill with integration patterns         |
| US      | Update Skill        | Regenerate a skill while preserving manual sections                |
| AS      | Audit Skill         | Drift detection between skill and current source                   |
| TS      | Test Skill          | Verify whether a skill covers its target completely and accurately |
| VS      | Verify Stack        | Pre-code stack feasibility verification against architecture       |
| RA      | Refine Architecture | Improve architecture doc using verified skill data                 |
| EX      | Export Skill        | Package for distribution, inject into CLAUDE.md                    |
| RS      | Rename Skill        | Rename a skill and update all references                           |
| DS      | Drop Skill          | Remove a skill and clean up references                             |

### Confidence Tiers

- **T1** — AST-verified signatures (Forge/Forge+/Deep)
- **T1-low** — Source reading without structural verification (Quick)
- **T2** — QMD-enriched temporal context (Deep)
- **T3** — External documentation, quarantined as untrusted

### IDE Support

23 IDEs supported: Claude Code, Cursor, Windsurf, Cline, Roo Code, GitHub Copilot, Codex, Gemini CLI, Junie, Kiro, Trae, Google Antigravity, Auggie, CodeBuddy, Crush, iFlow, KiloCoder, Ona, OpenCode, Pi, Qoder, QwenCoder, Rovo Dev

### Links

- Documentation: <https://armelhbobdad.github.io/bmad-module-skill-forge>
- npm: <https://www.npmjs.com/package/bmad-module-skill-forge>

## [1.0.0-rc.3](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.10.0...v1.0.0-rc.3) (2026-04-23)

### Features

* add deterministic frontmatter validator aligned with agentskills.io spec ([e273b29](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e273b292b8541b0e1a17ee71689fb54d13ccbe35))
* add deterministic scoring script for test-skill completeness scoring ([bb46c6b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bb46c6b030034bc3b6a9dcd60b18abd4b509f4e0))
* add persistent workspace for remote source caching (Layer 0) ([0183cee](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0183ceefc4d0327b0ce896d2f4522bb0be1c4110))
* **brief-skill:** extend scope.type reference-app through authoring path ([a321562](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a3215629ac2cc99c3eed63be6065cc4ed639cb6d)), closes [#179](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/179)
* consolidate SKILL.md, add Python scripts, headless mode, and pipeline support ([352bae5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/352bae535e26bf467ef28f2b114216bcea2e758a))
* **create-skill:** add scope.type "reference-app" ([722844a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/722844aba845aaf0b0a477317401e1503b20a552)), closes [#179](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/179)
* **export-skill:** define multi-skill execution semantics for --all ([ffc685a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ffc685a4f8aaa351c2372cbae3532c1187e843b7)), closes [#191](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/191)
* **health-check:** announce arrival on entry for all chaining workflows ([ddb6b9b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ddb6b9bea4e5b94042ecff100f00a7dde7acd96c))
* **health-check:** dedup submissions via deterministic fingerprint ([868d275](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/868d2751f46eacd75c0578e8d81fec820f35e166))
* **module-help:** encode SKF workflow ordering in after/before fields ([6922b7a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6922b7af18f887f7a7df20e8217a844646ada7e3))
* module-wide quality fixes — paths, triggers, provenance v2, output contracts ([3f68b8f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3f68b8f6db0bfe957c8f889b61af882ec90bf335))
* **release:** author canonical release.yaml workflow ([1295bf6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1295bf63b12433905b28a6d427f9c0dde4aa70d1)), closes [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#17](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/17)
* **release:** refactor release.yaml to push main via auto-merge PR ([3e915e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3e915e702e7e468fbe63eb56c9a55bbeb65c845c)), closes [1-#8](https://github.com/armelhbobdad/1-/issues/8) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#6](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/6) [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#8](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/8) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9) [#10](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/10) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12) [#198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198)
* **releasing:** create release GitHub environment with required-reviewer gate ([5f37053](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5f37053492159e73eb1c3fd0033616ec264f8a2f)), closes [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4)
* **releasing:** register npm Trusted Publisher for release.yaml workflow ([bd20cda](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bd20cdae2f81516511c5bb7abb2c95c83c0f0707))
* **shared:** atomic-write helper + feasibility-report schema for v1.0 ([2f60632](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2f6063271174e93311468011ef55c3ac0dfcb65a))
* **skf-create-skill:** discovered authoritative files protocol (§2c) ([e00ab2b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e00ab2bc1a2e81629ae82ad6d140996e1bbc31de)), closes [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116)
* **skf-create-skill:** treat brief.version as implicit target_version ([6e5ecb6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e5ecb62e4d5ae7bf1e9c72cc34f267287274194)), closes [#139](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/139)
* **skf-export-skill:** add snippet_skill_root_override config field ([a75eb32](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a75eb32b3a61a02f9240f8784b1c990830fc7962)), closes [#144](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/144)
* **skf-update-skill:** mirror §2c into change detection (§1b) ([d324af8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d324af82a514e04c3ff7813bf34c1fe7fabe40cb))
* **test-skill:** add stackSkill typeCoverage skip condition ([c1099d6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c1099d65204fc16e0d3ee3dd64a7eb2288879a62)), closes [#176](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/176)
* **test-skill:** pattern-ref branch in source-access-protocol ([c3e03e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c3e03e7dd06fbe9cf8cceeb584d5eaea99fdb2ab)), closes [#186](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/186)
* **test-skill:** skip §4b discovery test when catalog <2 skills ([5e160e5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5e160e55b7d50d9e69951cce0b20cd86e4196997)), closes [#177](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/177)
* **website:** restructure sidebar into Why/Try/Reference buckets ([e0780f8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e0780f8bc773f3cfd41d2b96b26bd78041963b84))

### Bug Fixes

* add full test suite to publish workflow before npm publish ([5c43294](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5c432944884e565503ef51c94b94c6f5d6ad7978))
* add missing feature request template and fix bug report typo ([f1d90a9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f1d90a9459c2f05ceadfa03350bf2941c4988289))
* add missing hasSidecar field to core agent unit test ([d6a5d29](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d6a5d29a649b85ffc3110db1b38f93a499ded071))
* align CSV row ordering with forger capabilities table and populate args ([47c65f8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/47c65f891b541df283393a55ca4557de04539212))
* **changelog:** strip bogus non-numeric closes refs from seed output ([a701efa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a701efa841d46567c71e29c54e5a73db39d572d4)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5)
* correct three-case to four-case in export step-04 and declare zod devDependency ([0680b44](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0680b442f713609d07980520ea900f1221f76f75))
* **create-stack-skill:** file-intersection fast path for pair analysis ([dbc4107](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dbc4107567d9f27e971de19eba0c3db8972f96df)), closes [#174](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/174)
* **docs:** quote remaining clone paths + camelCase fix in feasibility schema ([9170d5d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9170d5d1c3a501dba6e270b9871c0600f36413f0))
* exclude reports, pycache, and dev tools from npm package ([a269e43](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a269e4323b170acc9696f49e1e385a9ac10cc3d4))
* expand bmad-synergy doc to reflect all 23 IDEs with per-IDE skill roots ([8b56e7e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8b56e7ea382476ea4c5680baf7b2fdea0722a33b))
* expand IDE mapping to all 23 IDEs with per-IDE skill root paths ([e9ccde3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e9ccde3154792d82e877c5c90c7fd4e5d755a834))
* **export-skill:** detect snippet root prefix vs IDE skill_root mismatch ([54b059d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/54b059d1c477f2c59f48840a4d7140c09c27f975)), closes [#190](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/190)
* **health-check:** ensure fp-* label exists before gh issue create ([3554a24](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3554a24c026e1ba6df7d70d7387b52cba996dfba))
* quote interpolated paths in shell snippets across resolution protocols ([dcb9304](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dcb9304b3835d47a609622f948cb44a4515d5eff))
* **release:** accept admin-bypass merge as equivalent to approval ([c9ccffc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c9ccffc876cf8db174c16fb5bf3ebfc013793a5a)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [196/#197](https://github.com/196/bmad-module-skill-forge/issues/197) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199)
* **release:** address code-review findings (5 patches) ([34ad130](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/34ad1301c4d8cf11d281cafcc6127ceecc16c181))
* **release:** assert npm >=11.5.1 after $GITHUB_PATH update ([535e38f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/535e38fdfd485e24ccf258053b2f97ca5c8b25fc))
* **release:** force npm self-upgrade to survive arborist rebuild race ([f449c67](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f449c67c880bf5f8992822ea5c86f62d05c9c5da)), closes [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11)
* **release:** harden CHANGELOG preamble-restore guards (Story 3.3 code-review) ([6a6a521](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6a6a521cb6ad57b7bcb5e1993fb5ed35cc8d7d0a))
* **release:** harden Story 3.4 PR-auto-merge flow ([9467b4d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9467b4d7a942e65dc63926bda2dc8409f04a105a)), closes [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#16](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/16) [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11)
* **release:** pass --tag in pre-publish dry-run to match real publish step ([de2334b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/de2334b0d54ec88e7cf168543d4fda72bc4f8f6c))
* **release:** poll commit check-runs API directly in Wait step ([081ddb1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/081ddb102e1d21e1122bd20d330fb5b86c0ee6d0)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [6/#7](https://github.com/6/bmad-module-skill-forge/issues/7) [#14](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/14) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199) [#200](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/200) [#202](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/202)
* **release:** preserve spaces in required-context names (Story 3.5 followup) ([add467d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/add467d59611da21d647c20b0894af7c8cab147f)), closes [#203](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/203)
* **release:** restore CHANGELOG preamble after conventional-changelog -s prepend (Story 3.3 from Story 3.2 HIGH deferred-work) ([10c1134](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/10c113443f9f699fe3571883f767b0d198c5c5f7))
* **release:** set HUSKY=0 job env to skip local git hooks in CI ([cae5861](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cae5861a1b2f10d9d0f274337f9027d4f1adb213)), closes [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12)
* **release:** side-prefix npm install to dodge self-upgrade rebuild race ([cbc7851](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cbc7851b20225e907537269551703965d3f0a525))
* **release:** use gh pr view --json state (merged is not a valid field) ([7ac3bd6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7ac3bd6bf2b97ee3b0cba7909998561992ba9a17)), closes [#206](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/206) [#198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198) [#202](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/202) [#205](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/205)
* remove reserved --update-spec flag from skf-setup ([b625332](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b6253329fd714648dbb00144b9e485b6109788ad))
* rename skf-setup-forge to skf-setup, move module files to assets/, fix CSV alignment ([f670a11](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f670a1170ff4678a515feedd933fd40a491960fb))
* replace stale platform terminology with context-file/IDE model across step files and docs ([5ff42f7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5ff42f7689477c94ae523de1ca5350b5e260e387))
* resolve 10 issues in skf-setup workflow found during release audit ([adaa891](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/adaa891a40e43c6076f279a509eeaf2d2fc499b4))
* resolve 15 issues in skf-create-skill workflow found during release audit ([5b8fa4a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5b8fa4a5cc88527941f3e466d04bb367205039fa))
* resolve 5 issues found during commit review — encoding, regex, parser, docs, orphan ref ([b7f75c2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b7f75c21aba9bdd9afe97b2691e0278320a9d015))
* resolve 5 issues in manual-release and docs workflows ([32559e9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/32559e97b779062477f3674026336c1e9655ce58))
* resolve 8 consistency issues found during commit review ([304b0af](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/304b0af9f079ed2ab55a460dfd5480b700146c3a))
* resolve 9 issues in skf-test-skill workflow found during release audit ([7353b4c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7353b4c19153c7051c059a34813c206742a0d584))
* resolve stale references, validator gaps, and documentation inconsistencies from skill migration ([70854d7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/70854d77752ce67bfc5d244aa25bfe972b358d8f))
* restore module.yaml and module-help.csv to src/ root ([d698194](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d698194a520a2e7d2681b724b2db070cd0355123))
* **shared/scripts:** explicit utf-8 encoding on all text file I/O ([e7815bc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e7815bcf1d45a8cb46c535432dcc772cdc1fa015))
* **shared:** atomic-write cross-platform hardening + Windows junction fallback ([f19a4db](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f19a4dbcb32db34db5c76afe448bfc0424d6fc2a))
* **skf-analyze-source:** mirror JS/TS monorepo version detection rule ([94e3982](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/94e3982642dd5ca32b41bc875f25f57dd357e2a3)), closes [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126) [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126)
* **skf-audit-skill:** bound re-index to provenance-map file universe ([18ed601](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/18ed6013208f823601f4a3d55065d0efed20e7c8))
* **skf-brief-skill:** add JS/TS monorepo + pre-release fallback to version detection ([7edb4f9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7edb4f93175bb1414435f170911393c00c99fd9e)), closes [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126)
* **skf-create-skill,skf-test-skill:** plumb scope.tier_a_include through effective_denominator writer ([ff1dc72](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ff1dc7252d4a2c002b4a672f49470bfcc12ad5fc)), closes [#134](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/134)
* **skf-create-skill:** apply v1.0 ship-review CRIT+HIGH+BLOCK+SERIOUS ([30a7244](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/30a7244493cd4075e4443579df9d27fe909dbd94))
* **skf-create-skill:** drop -skill suffix from staging directory ([786d17d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/786d17da8828c94a56b2826b00a43d7348bf0c7f)), closes [#114](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/114)
* **skf-create-skill:** name the compile staging directory ([6e07634](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e07634d97ce8d8b08e74f6f79ebf3176c3a653d))
* **skf-create-skill:** polish — magic-number rationales + subprocess timeouts ([5f5a6c0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5f5a6c0d92d9000eefc97547a18cb081dd2b55ec))
* **skf-create-skill:** rewrite python-public-classes rule for ast-grep 0.42.x ([431cbf8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/431cbf8f37d40ceb36f69e248e07e61a825dee5b)), closes [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#140](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/140)
* **skf-create-skill:** route promoted authoritative docs to file_entries ([7b9c99c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7b9c99cf87e118bec02e4bba61d52f9de0d7c5a1)), closes [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116) [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116)
* **skf-create-skill:** sanitize angle-bracket placeholders in description ([ee17db5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ee17db535ee66c7179d1febbcd78d737261048c8)), closes [#115](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/115)
* **skf-create-skill:** tighten sanitizer regex against inline generics ([bc078b8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bc078b890f8240f6340905c4d66b0f7abdaa7587))
* **skf-create-skill:** unconditionally sanitize description angle brackets ([3b40e7c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3b40e7c134faaa74254fa2525533b5668c9ce425)), closes [#127](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/127)
* **skf-create-stack-skill:** atomic stack writes + schemaVersion guard ([84f37af](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/84f37af6cf9611ff6172f94a0621c5139534e3d4))
* **skf-create-stack-skill:** close M1-M4 polish ([a5e5d2c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a5e5d2c96bf246df6c09698367f907dbb9f987a4))
* **skf-export-skill:** raise snippet token warning threshold to 300 ([f4d558d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f4d558d317da1b4e26fda43bcb67b9d9a45b52bb)), closes [#146](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/146)
* **skf-export-skill:** rename manifest platforms field to ides ([b1ea4cd](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b1ea4cd2aa386431d024ada004f3cab8df4e5953)), closes [#148](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/148)
* **skf-quick-skill:** add Java/Kotlin coverage to manifest + export scan ([2659b44](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2659b44bd8799fca4b5b440a1ef9a752deb17ab6)), closes [#162](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/162)
* **skf-quick-skill:** make active pointer Windows-safe via shared helper ([7850054](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7850054861423f0f9cff7d435065534a9d0b8a07)), closes [#164](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/164)
* **skf-quick-skill:** write deliverables in step-05 so validation has files ([dc620a2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dc620a26722ffebbdd0057a9a6755ee3f19ceccc)), closes [#163](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/163)
* **skf-test-skill,skf-brief-skill:** honor scope.tier_a_include in stratified-scope denominator ([ad7105b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ad7105b22e19202bfe0a7dd252242556304789bc)), closes [#134](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/134)
* **skf-test-skill,skf-create-skill:** stratified-scope denominator for curated monorepos ([ece7934](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ece7934dd7dc550a0f14b4d02e1f0bee456e76c1)), closes [#128](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/128)
* **skf-test-skill:** bin export-count drift check by semantic cluster ([e3edc91](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e3edc913ef3d63e70958969858c80d3be2386f82)), closes [#143](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/143)
* **skf-test-skill:** close M1-M5 polish + matrix-class fixtures ([8167a34](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8167a343bd772103ac8bec840d2be1c4e9b5f687))
* **skf-test-skill:** cross-check metadata export counts in step-03 §4b ([4404455](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/440445506007d8487fe9b841a7d029ef55262c30)), closes [#135](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/135)
* **skf-test-skill:** detect single-commit update-skill bundle in step-04b staleness check ([e6704fc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e6704fcb9a9cc38d2b328c0b5b3be10279ff5815)), closes [#136](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/136)
* **skf-test-skill:** formalize Section 4b historical-migration exception ([96a937e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/96a937e2a84bfeceb7bd57fb509c1b3930b3a2ec)), closes [#129](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/129)
* **skf-test-skill:** minimum-evidence floor + INCONCLUSIVE verdict ([58da265](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/58da2651fea7000cc135e5be52e56945a7509c46))
* **skf-update-skill:** add gap-driven branch to step-03 re-extraction ([2faf887](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2faf8878f5cf1d9783f7fa452b791313190ec8f3))
* **skf-update-skill:** add targeted re-extraction branch for citation-less Critical/High gap-driven entries ([f94a466](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f94a466357636f8d15818eceb63b374e39541052)), closes [#132](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/132)
* **skf-update-skill:** apply description guard to step-06-write ([44e76fe](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44e76feadee5af7489785ae87d61d22fb8d7b0fe))
* **skf-update-skill:** make step-06 §5 context-snippet regen conditional ([7d72553](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7d72553845bb034c9b419042b2915932d0d17745)), closes [#123](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/123)
* **skf-update-skill:** materialize §2 pre-filter exclusion set mechanically ([897e778](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/897e7786baa1a73cc21f7c22b852bf2a111664b1))
* **skf-update-skill:** preserve test-report citations in gap-driven manifest ([dff3e9b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dff3e9b1c5b5d8c965069335c574cf8a92af2372)), closes [#122](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/122)
* **skf-update-skill:** skip version bump in gap-driven mode (step-06 §2) ([c3c7e53](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c3c7e53c69ea9fdc08017a55eb611a8d05b7fe2a)), closes [#121](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/121)
* **skf-update-skill:** update stale §2c refs missed by renumber in step-02 ([44ca6d5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44ca6d587ae66ebbef2d61e0a97e19d6fd442506))
* **skf-update-skill:** verify active symlink in step-06 §6 ([657f394](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/657f394338c81e20208e7f76bad74b9253cba777)), closes [#158](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/158)
* **skf-update-skill:** write merged files in step-04, verify in step-06 ([97a839c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/97a839cd901cfcce9d9e2e7cf86139f3d1b62554))
* **skf-verify-stack:** close M1-M5 polish ([cac5501](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cac5501a47a0a7d504f61ce2fbd60923fa4f85d9))
* **skf-verify-stack:** require Check 4 citation for Verified verdict ([8c20873](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8c208739e265c79269c61df0e3e05d4aa34a12a9))
* **skf:** align tessl parse label with actual CLI output ([c9bf1de](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c9bf1de4b9f039db065cb6eca5db22a7e4cf2168)), closes [#111](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/111)
* **skf:** pin T2-future detection to evidence-report frontmatter ([ef10c94](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ef10c94a06939ec9881e4707ebcb85bccee3864c)), closes [#182](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/182)
* **skf:** resolve skf-atomic-write.py across src/ and installed layouts ([299d369](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/299d36962e010f29f69886bb6c782deb73b1fe6c)), closes [#178](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/178) [#173](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/173) [#178](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/178) [#173](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/173)
* **test-skill:** §2.3 bare-fence rule ignores closing fences ([755f2cb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/755f2cbdfb8f52b8fb4f885473779db519fa0a1d)), closes [#180](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/180) [#184](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/184)
* **test-skill:** §2.6 table column check handles escaped pipes ([a03ddef](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a03ddef8b2272c1b5c79d4b5e876f20276866b21)), closes [#185](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/185)
* **test-skill:** accept SKF-template section names in §2.1 ([4e1a759](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4e1a759bcb4cfb937d2da1106ace24acd8f7a90d)), closes [#183](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/183)
* **test-skill:** drop skill_name from coverage §1a required keys ([32f8273](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/32f82730dffc99b04f05b86e0b6dbd68f2dca0f7)), closes [#181](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/181)
* **test-skill:** unpin tessl, use probe-verified binary ([d8d4055](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d8d4055a727063f584a2135e4cb50d1589f92cc3)), closes [#175](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/175)
* **test:** explicit utf-8 encoding on all text file I/O ([e06ac5f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e06ac5f0e245ff3d17039905a3208ef5bc2cc2ea)), closes [#165](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/165)
* update 3 stale references to ephemeral-only clone terminology ([eeb0f07](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/eeb0f07721c6b884c7876b77abe7231fea8e80ec))
* **workflows:** document shared/health-check.md path resolution ([d899046](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d8990465a78bfaab878c8baa7442e8a5e7e4d847))
* **workflows:** guard against workspace HEAD drift before spot-checking pinned source ([#154](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/154)) ([7328452](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/73284521a9dcbd853f8a7ed8a418fcaff7c268c8))
* **workflows:** remove premature workflow-complete banner before health check ([9d6fcf5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9d6fcf588ca317befe8bec431279e5e5bdc241ec))
* **workflows:** split health-check into its own terminal step across 14 workflows ([0448046](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0448046af7b0e5fbffd490a05d44dc153ed92785)), closes [#152](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/152)
* **workflows:** timestamped result JSON filenames to preserve audit trail ([#155](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/155)) ([e4f392d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e4f392d3f98fd3b74b44677c2df57be0e39077d2))

### Reverts

* Revert "chore(release): add temporary push trigger for Story 3.2 alpha cut (revert in same story)" ([7208ff4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7208ff48640e97a2175b99b5d21dde192d85fdb3))
## [1.0.0-rc.2](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.10.0...v1.0.0-rc.2) (2026-04-23)

### Features

* add deterministic frontmatter validator aligned with agentskills.io spec ([e273b29](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e273b292b8541b0e1a17ee71689fb54d13ccbe35))
* add deterministic scoring script for test-skill completeness scoring ([bb46c6b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bb46c6b030034bc3b6a9dcd60b18abd4b509f4e0))
* add persistent workspace for remote source caching (Layer 0) ([0183cee](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0183ceefc4d0327b0ce896d2f4522bb0be1c4110))
* **brief-skill:** extend scope.type reference-app through authoring path ([a321562](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a3215629ac2cc99c3eed63be6065cc4ed639cb6d)), closes [#179](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/179)
* consolidate SKILL.md, add Python scripts, headless mode, and pipeline support ([352bae5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/352bae535e26bf467ef28f2b114216bcea2e758a))
* **create-skill:** add scope.type "reference-app" ([722844a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/722844aba845aaf0b0a477317401e1503b20a552)), closes [#179](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/179)
* **export-skill:** define multi-skill execution semantics for --all ([ffc685a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ffc685a4f8aaa351c2372cbae3532c1187e843b7)), closes [#191](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/191)
* **health-check:** announce arrival on entry for all chaining workflows ([ddb6b9b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ddb6b9bea4e5b94042ecff100f00a7dde7acd96c))
* **health-check:** dedup submissions via deterministic fingerprint ([868d275](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/868d2751f46eacd75c0578e8d81fec820f35e166))
* **module-help:** encode SKF workflow ordering in after/before fields ([6922b7a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6922b7af18f887f7a7df20e8217a844646ada7e3))
* module-wide quality fixes — paths, triggers, provenance v2, output contracts ([3f68b8f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3f68b8f6db0bfe957c8f889b61af882ec90bf335))
* **release:** author canonical release.yaml workflow ([1295bf6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1295bf63b12433905b28a6d427f9c0dde4aa70d1)), closes [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#17](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/17)
* **release:** refactor release.yaml to push main via auto-merge PR ([3e915e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3e915e702e7e468fbe63eb56c9a55bbeb65c845c)), closes [1-#8](https://github.com/armelhbobdad/1-/issues/8) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#6](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/6) [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#8](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/8) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9) [#10](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/10) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12) [#198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198)
* **releasing:** create release GitHub environment with required-reviewer gate ([5f37053](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5f37053492159e73eb1c3fd0033616ec264f8a2f)), closes [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4)
* **releasing:** register npm Trusted Publisher for release.yaml workflow ([bd20cda](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bd20cdae2f81516511c5bb7abb2c95c83c0f0707))
* **shared:** atomic-write helper + feasibility-report schema for v1.0 ([2f60632](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2f6063271174e93311468011ef55c3ac0dfcb65a))
* **skf-create-skill:** discovered authoritative files protocol (§2c) ([e00ab2b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e00ab2bc1a2e81629ae82ad6d140996e1bbc31de)), closes [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116)
* **skf-create-skill:** treat brief.version as implicit target_version ([6e5ecb6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e5ecb62e4d5ae7bf1e9c72cc34f267287274194)), closes [#139](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/139)
* **skf-export-skill:** add snippet_skill_root_override config field ([a75eb32](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a75eb32b3a61a02f9240f8784b1c990830fc7962)), closes [#144](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/144)
* **skf-update-skill:** mirror §2c into change detection (§1b) ([d324af8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d324af82a514e04c3ff7813bf34c1fe7fabe40cb))
* **test-skill:** add stackSkill typeCoverage skip condition ([c1099d6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c1099d65204fc16e0d3ee3dd64a7eb2288879a62)), closes [#176](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/176)
* **test-skill:** pattern-ref branch in source-access-protocol ([c3e03e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c3e03e7dd06fbe9cf8cceeb584d5eaea99fdb2ab)), closes [#186](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/186)
* **test-skill:** skip §4b discovery test when catalog <2 skills ([5e160e5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5e160e55b7d50d9e69951cce0b20cd86e4196997)), closes [#177](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/177)
* **website:** restructure sidebar into Why/Try/Reference buckets ([e0780f8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e0780f8bc773f3cfd41d2b96b26bd78041963b84))

### Bug Fixes

* add full test suite to publish workflow before npm publish ([5c43294](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5c432944884e565503ef51c94b94c6f5d6ad7978))
* add missing feature request template and fix bug report typo ([f1d90a9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f1d90a9459c2f05ceadfa03350bf2941c4988289))
* add missing hasSidecar field to core agent unit test ([d6a5d29](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d6a5d29a649b85ffc3110db1b38f93a499ded071))
* align CSV row ordering with forger capabilities table and populate args ([47c65f8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/47c65f891b541df283393a55ca4557de04539212))
* **changelog:** strip bogus non-numeric closes refs from seed output ([a701efa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a701efa841d46567c71e29c54e5a73db39d572d4)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5)
* correct three-case to four-case in export step-04 and declare zod devDependency ([0680b44](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0680b442f713609d07980520ea900f1221f76f75))
* **create-stack-skill:** file-intersection fast path for pair analysis ([dbc4107](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dbc4107567d9f27e971de19eba0c3db8972f96df)), closes [#174](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/174)
* **docs:** quote remaining clone paths + camelCase fix in feasibility schema ([9170d5d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9170d5d1c3a501dba6e270b9871c0600f36413f0))
* exclude reports, pycache, and dev tools from npm package ([a269e43](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a269e4323b170acc9696f49e1e385a9ac10cc3d4))
* expand bmad-synergy doc to reflect all 23 IDEs with per-IDE skill roots ([8b56e7e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8b56e7ea382476ea4c5680baf7b2fdea0722a33b))
* expand IDE mapping to all 23 IDEs with per-IDE skill root paths ([e9ccde3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e9ccde3154792d82e877c5c90c7fd4e5d755a834))
* **export-skill:** detect snippet root prefix vs IDE skill_root mismatch ([54b059d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/54b059d1c477f2c59f48840a4d7140c09c27f975)), closes [#190](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/190)
* **health-check:** ensure fp-* label exists before gh issue create ([3554a24](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3554a24c026e1ba6df7d70d7387b52cba996dfba))
* quote interpolated paths in shell snippets across resolution protocols ([dcb9304](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dcb9304b3835d47a609622f948cb44a4515d5eff))
* **release:** accept admin-bypass merge as equivalent to approval ([c9ccffc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c9ccffc876cf8db174c16fb5bf3ebfc013793a5a)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [196/#197](https://github.com/196/bmad-module-skill-forge/issues/197) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199)
* **release:** address code-review findings (5 patches) ([34ad130](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/34ad1301c4d8cf11d281cafcc6127ceecc16c181))
* **release:** assert npm >=11.5.1 after $GITHUB_PATH update ([535e38f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/535e38fdfd485e24ccf258053b2f97ca5c8b25fc))
* **release:** force npm self-upgrade to survive arborist rebuild race ([f449c67](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f449c67c880bf5f8992822ea5c86f62d05c9c5da)), closes [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11)
* **release:** harden CHANGELOG preamble-restore guards (Story 3.3 code-review) ([6a6a521](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6a6a521cb6ad57b7bcb5e1993fb5ed35cc8d7d0a))
* **release:** harden Story 3.4 PR-auto-merge flow ([9467b4d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9467b4d7a942e65dc63926bda2dc8409f04a105a)), closes [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#16](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/16) [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11)
* **release:** pass --tag in pre-publish dry-run to match real publish step ([de2334b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/de2334b0d54ec88e7cf168543d4fda72bc4f8f6c))
* **release:** poll commit check-runs API directly in Wait step ([081ddb1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/081ddb102e1d21e1122bd20d330fb5b86c0ee6d0)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [6/#7](https://github.com/6/bmad-module-skill-forge/issues/7) [#14](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/14) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199) [#200](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/200) [#202](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/202)
* **release:** preserve spaces in required-context names (Story 3.5 followup) ([add467d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/add467d59611da21d647c20b0894af7c8cab147f)), closes [#203](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/203)
* **release:** restore CHANGELOG preamble after conventional-changelog -s prepend (Story 3.3 from Story 3.2 HIGH deferred-work) ([10c1134](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/10c113443f9f699fe3571883f767b0d198c5c5f7))
* **release:** set HUSKY=0 job env to skip local git hooks in CI ([cae5861](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cae5861a1b2f10d9d0f274337f9027d4f1adb213)), closes [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12)
* **release:** side-prefix npm install to dodge self-upgrade rebuild race ([cbc7851](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cbc7851b20225e907537269551703965d3f0a525))
* **release:** use gh pr view --json state (merged is not a valid field) ([7ac3bd6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7ac3bd6bf2b97ee3b0cba7909998561992ba9a17)), closes [#206](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/206) [#198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198) [#202](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/202) [#205](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/205)
* remove reserved --update-spec flag from skf-setup ([b625332](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b6253329fd714648dbb00144b9e485b6109788ad))
* rename skf-setup-forge to skf-setup, move module files to assets/, fix CSV alignment ([f670a11](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f670a1170ff4678a515feedd933fd40a491960fb))
* replace stale platform terminology with context-file/IDE model across step files and docs ([5ff42f7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5ff42f7689477c94ae523de1ca5350b5e260e387))
* resolve 10 issues in skf-setup workflow found during release audit ([adaa891](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/adaa891a40e43c6076f279a509eeaf2d2fc499b4))
* resolve 15 issues in skf-create-skill workflow found during release audit ([5b8fa4a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5b8fa4a5cc88527941f3e466d04bb367205039fa))
* resolve 5 issues found during commit review — encoding, regex, parser, docs, orphan ref ([b7f75c2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b7f75c21aba9bdd9afe97b2691e0278320a9d015))
* resolve 5 issues in manual-release and docs workflows ([32559e9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/32559e97b779062477f3674026336c1e9655ce58))
* resolve 8 consistency issues found during commit review ([304b0af](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/304b0af9f079ed2ab55a460dfd5480b700146c3a))
* resolve 9 issues in skf-test-skill workflow found during release audit ([7353b4c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7353b4c19153c7051c059a34813c206742a0d584))
* resolve stale references, validator gaps, and documentation inconsistencies from skill migration ([70854d7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/70854d77752ce67bfc5d244aa25bfe972b358d8f))
* restore module.yaml and module-help.csv to src/ root ([d698194](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d698194a520a2e7d2681b724b2db070cd0355123))
* **shared/scripts:** explicit utf-8 encoding on all text file I/O ([e7815bc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e7815bcf1d45a8cb46c535432dcc772cdc1fa015))
* **shared:** atomic-write cross-platform hardening + Windows junction fallback ([f19a4db](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f19a4dbcb32db34db5c76afe448bfc0424d6fc2a))
* **skf-analyze-source:** mirror JS/TS monorepo version detection rule ([94e3982](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/94e3982642dd5ca32b41bc875f25f57dd357e2a3)), closes [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126) [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126)
* **skf-audit-skill:** bound re-index to provenance-map file universe ([18ed601](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/18ed6013208f823601f4a3d55065d0efed20e7c8))
* **skf-brief-skill:** add JS/TS monorepo + pre-release fallback to version detection ([7edb4f9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7edb4f93175bb1414435f170911393c00c99fd9e)), closes [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126)
* **skf-create-skill,skf-test-skill:** plumb scope.tier_a_include through effective_denominator writer ([ff1dc72](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ff1dc7252d4a2c002b4a672f49470bfcc12ad5fc)), closes [#134](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/134)
* **skf-create-skill:** apply v1.0 ship-review CRIT+HIGH+BLOCK+SERIOUS ([30a7244](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/30a7244493cd4075e4443579df9d27fe909dbd94))
* **skf-create-skill:** drop -skill suffix from staging directory ([786d17d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/786d17da8828c94a56b2826b00a43d7348bf0c7f)), closes [#114](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/114)
* **skf-create-skill:** name the compile staging directory ([6e07634](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e07634d97ce8d8b08e74f6f79ebf3176c3a653d))
* **skf-create-skill:** polish — magic-number rationales + subprocess timeouts ([5f5a6c0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5f5a6c0d92d9000eefc97547a18cb081dd2b55ec))
* **skf-create-skill:** rewrite python-public-classes rule for ast-grep 0.42.x ([431cbf8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/431cbf8f37d40ceb36f69e248e07e61a825dee5b)), closes [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#140](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/140)
* **skf-create-skill:** route promoted authoritative docs to file_entries ([7b9c99c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7b9c99cf87e118bec02e4bba61d52f9de0d7c5a1)), closes [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116) [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116)
* **skf-create-skill:** sanitize angle-bracket placeholders in description ([ee17db5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ee17db535ee66c7179d1febbcd78d737261048c8)), closes [#115](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/115)
* **skf-create-skill:** tighten sanitizer regex against inline generics ([bc078b8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bc078b890f8240f6340905c4d66b0f7abdaa7587))
* **skf-create-skill:** unconditionally sanitize description angle brackets ([3b40e7c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3b40e7c134faaa74254fa2525533b5668c9ce425)), closes [#127](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/127)
* **skf-create-stack-skill:** atomic stack writes + schemaVersion guard ([84f37af](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/84f37af6cf9611ff6172f94a0621c5139534e3d4))
* **skf-create-stack-skill:** close M1-M4 polish ([a5e5d2c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a5e5d2c96bf246df6c09698367f907dbb9f987a4))
* **skf-export-skill:** raise snippet token warning threshold to 300 ([f4d558d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f4d558d317da1b4e26fda43bcb67b9d9a45b52bb)), closes [#146](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/146)
* **skf-export-skill:** rename manifest platforms field to ides ([b1ea4cd](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b1ea4cd2aa386431d024ada004f3cab8df4e5953)), closes [#148](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/148)
* **skf-quick-skill:** add Java/Kotlin coverage to manifest + export scan ([2659b44](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2659b44bd8799fca4b5b440a1ef9a752deb17ab6)), closes [#162](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/162)
* **skf-quick-skill:** make active pointer Windows-safe via shared helper ([7850054](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7850054861423f0f9cff7d435065534a9d0b8a07)), closes [#164](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/164)
* **skf-quick-skill:** write deliverables in step-05 so validation has files ([dc620a2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dc620a26722ffebbdd0057a9a6755ee3f19ceccc)), closes [#163](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/163)
* **skf-test-skill,skf-brief-skill:** honor scope.tier_a_include in stratified-scope denominator ([ad7105b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ad7105b22e19202bfe0a7dd252242556304789bc)), closes [#134](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/134)
* **skf-test-skill,skf-create-skill:** stratified-scope denominator for curated monorepos ([ece7934](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ece7934dd7dc550a0f14b4d02e1f0bee456e76c1)), closes [#128](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/128)
* **skf-test-skill:** bin export-count drift check by semantic cluster ([e3edc91](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e3edc913ef3d63e70958969858c80d3be2386f82)), closes [#143](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/143)
* **skf-test-skill:** close M1-M5 polish + matrix-class fixtures ([8167a34](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8167a343bd772103ac8bec840d2be1c4e9b5f687))
* **skf-test-skill:** cross-check metadata export counts in step-03 §4b ([4404455](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/440445506007d8487fe9b841a7d029ef55262c30)), closes [#135](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/135)
* **skf-test-skill:** detect single-commit update-skill bundle in step-04b staleness check ([e6704fc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e6704fcb9a9cc38d2b328c0b5b3be10279ff5815)), closes [#136](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/136)
* **skf-test-skill:** formalize Section 4b historical-migration exception ([96a937e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/96a937e2a84bfeceb7bd57fb509c1b3930b3a2ec)), closes [#129](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/129)
* **skf-test-skill:** minimum-evidence floor + INCONCLUSIVE verdict ([58da265](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/58da2651fea7000cc135e5be52e56945a7509c46))
* **skf-update-skill:** add gap-driven branch to step-03 re-extraction ([2faf887](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2faf8878f5cf1d9783f7fa452b791313190ec8f3))
* **skf-update-skill:** add targeted re-extraction branch for citation-less Critical/High gap-driven entries ([f94a466](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f94a466357636f8d15818eceb63b374e39541052)), closes [#132](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/132)
* **skf-update-skill:** apply description guard to step-06-write ([44e76fe](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44e76feadee5af7489785ae87d61d22fb8d7b0fe))
* **skf-update-skill:** make step-06 §5 context-snippet regen conditional ([7d72553](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7d72553845bb034c9b419042b2915932d0d17745)), closes [#123](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/123)
* **skf-update-skill:** materialize §2 pre-filter exclusion set mechanically ([897e778](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/897e7786baa1a73cc21f7c22b852bf2a111664b1))
* **skf-update-skill:** preserve test-report citations in gap-driven manifest ([dff3e9b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dff3e9b1c5b5d8c965069335c574cf8a92af2372)), closes [#122](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/122)
* **skf-update-skill:** skip version bump in gap-driven mode (step-06 §2) ([c3c7e53](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c3c7e53c69ea9fdc08017a55eb611a8d05b7fe2a)), closes [#121](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/121)
* **skf-update-skill:** update stale §2c refs missed by renumber in step-02 ([44ca6d5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44ca6d587ae66ebbef2d61e0a97e19d6fd442506))
* **skf-update-skill:** verify active symlink in step-06 §6 ([657f394](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/657f394338c81e20208e7f76bad74b9253cba777)), closes [#158](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/158)
* **skf-update-skill:** write merged files in step-04, verify in step-06 ([97a839c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/97a839cd901cfcce9d9e2e7cf86139f3d1b62554))
* **skf-verify-stack:** close M1-M5 polish ([cac5501](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cac5501a47a0a7d504f61ce2fbd60923fa4f85d9))
* **skf-verify-stack:** require Check 4 citation for Verified verdict ([8c20873](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8c208739e265c79269c61df0e3e05d4aa34a12a9))
* **skf:** align tessl parse label with actual CLI output ([c9bf1de](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c9bf1de4b9f039db065cb6eca5db22a7e4cf2168)), closes [#111](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/111)
* **skf:** pin T2-future detection to evidence-report frontmatter ([ef10c94](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ef10c94a06939ec9881e4707ebcb85bccee3864c)), closes [#182](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/182)
* **skf:** resolve skf-atomic-write.py across src/ and installed layouts ([299d369](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/299d36962e010f29f69886bb6c782deb73b1fe6c)), closes [#178](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/178) [#173](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/173) [#178](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/178) [#173](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/173)
* **test-skill:** §2.3 bare-fence rule ignores closing fences ([755f2cb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/755f2cbdfb8f52b8fb4f885473779db519fa0a1d)), closes [#180](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/180) [#184](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/184)
* **test-skill:** §2.6 table column check handles escaped pipes ([a03ddef](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a03ddef8b2272c1b5c79d4b5e876f20276866b21)), closes [#185](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/185)
* **test-skill:** accept SKF-template section names in §2.1 ([4e1a759](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4e1a759bcb4cfb937d2da1106ace24acd8f7a90d)), closes [#183](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/183)
* **test-skill:** drop skill_name from coverage §1a required keys ([32f8273](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/32f82730dffc99b04f05b86e0b6dbd68f2dca0f7)), closes [#181](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/181)
* **test-skill:** unpin tessl, use probe-verified binary ([d8d4055](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d8d4055a727063f584a2135e4cb50d1589f92cc3)), closes [#175](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/175)
* **test:** explicit utf-8 encoding on all text file I/O ([e06ac5f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e06ac5f0e245ff3d17039905a3208ef5bc2cc2ea)), closes [#165](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/165)
* update 3 stale references to ephemeral-only clone terminology ([eeb0f07](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/eeb0f07721c6b884c7876b77abe7231fea8e80ec))
* **workflows:** document shared/health-check.md path resolution ([d899046](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d8990465a78bfaab878c8baa7442e8a5e7e4d847))
* **workflows:** guard against workspace HEAD drift before spot-checking pinned source ([#154](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/154)) ([7328452](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/73284521a9dcbd853f8a7ed8a418fcaff7c268c8))
* **workflows:** remove premature workflow-complete banner before health check ([9d6fcf5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9d6fcf588ca317befe8bec431279e5e5bdc241ec))
* **workflows:** split health-check into its own terminal step across 14 workflows ([0448046](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0448046af7b0e5fbffd490a05d44dc153ed92785)), closes [#152](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/152)
* **workflows:** timestamped result JSON filenames to preserve audit trail ([#155](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/155)) ([e4f392d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e4f392d3f98fd3b74b44677c2df57be0e39077d2))

### Reverts

* Revert "chore(release): add temporary push trigger for Story 3.2 alpha cut (revert in same story)" ([7208ff4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7208ff48640e97a2175b99b5d21dde192d85fdb3))
## [1.0.0-rc.1](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.10.0...v1.0.0-rc.1) (2026-04-23)

### Features

* add deterministic frontmatter validator aligned with agentskills.io spec ([e273b29](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e273b292b8541b0e1a17ee71689fb54d13ccbe35))
* add deterministic scoring script for test-skill completeness scoring ([bb46c6b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bb46c6b030034bc3b6a9dcd60b18abd4b509f4e0))
* add persistent workspace for remote source caching (Layer 0) ([0183cee](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0183ceefc4d0327b0ce896d2f4522bb0be1c4110))
* **brief-skill:** extend scope.type reference-app through authoring path ([a321562](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a3215629ac2cc99c3eed63be6065cc4ed639cb6d)), closes [#179](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/179)
* consolidate SKILL.md, add Python scripts, headless mode, and pipeline support ([352bae5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/352bae535e26bf467ef28f2b114216bcea2e758a))
* **create-skill:** add scope.type "reference-app" ([722844a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/722844aba845aaf0b0a477317401e1503b20a552)), closes [#179](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/179)
* **export-skill:** define multi-skill execution semantics for --all ([ffc685a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ffc685a4f8aaa351c2372cbae3532c1187e843b7)), closes [#191](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/191)
* **health-check:** announce arrival on entry for all chaining workflows ([ddb6b9b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ddb6b9bea4e5b94042ecff100f00a7dde7acd96c))
* **health-check:** dedup submissions via deterministic fingerprint ([868d275](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/868d2751f46eacd75c0578e8d81fec820f35e166))
* **module-help:** encode SKF workflow ordering in after/before fields ([6922b7a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6922b7af18f887f7a7df20e8217a844646ada7e3))
* module-wide quality fixes — paths, triggers, provenance v2, output contracts ([3f68b8f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3f68b8f6db0bfe957c8f889b61af882ec90bf335))
* **release:** author canonical release.yaml workflow ([1295bf6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1295bf63b12433905b28a6d427f9c0dde4aa70d1)), closes [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#17](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/17)
* **release:** refactor release.yaml to push main via auto-merge PR ([3e915e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3e915e702e7e468fbe63eb56c9a55bbeb65c845c)), closes [1-#8](https://github.com/armelhbobdad/1-/issues/8) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9) [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#6](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/6) [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#8](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/8) [#9](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/9) [#10](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/10) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12) [#198](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/198)
* **releasing:** create release GitHub environment with required-reviewer gate ([5f37053](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5f37053492159e73eb1c3fd0033616ec264f8a2f)), closes [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4)
* **releasing:** register npm Trusted Publisher for release.yaml workflow ([bd20cda](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bd20cdae2f81516511c5bb7abb2c95c83c0f0707))
* **shared:** atomic-write helper + feasibility-report schema for v1.0 ([2f60632](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2f6063271174e93311468011ef55c3ac0dfcb65a))
* **skf-create-skill:** discovered authoritative files protocol (§2c) ([e00ab2b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e00ab2bc1a2e81629ae82ad6d140996e1bbc31de)), closes [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116)
* **skf-create-skill:** treat brief.version as implicit target_version ([6e5ecb6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e5ecb62e4d5ae7bf1e9c72cc34f267287274194)), closes [#139](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/139)
* **skf-export-skill:** add snippet_skill_root_override config field ([a75eb32](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a75eb32b3a61a02f9240f8784b1c990830fc7962)), closes [#144](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/144)
* **skf-update-skill:** mirror §2c into change detection (§1b) ([d324af8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d324af82a514e04c3ff7813bf34c1fe7fabe40cb))
* **test-skill:** add stackSkill typeCoverage skip condition ([c1099d6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c1099d65204fc16e0d3ee3dd64a7eb2288879a62)), closes [#176](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/176)
* **test-skill:** pattern-ref branch in source-access-protocol ([c3e03e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c3e03e7dd06fbe9cf8cceeb584d5eaea99fdb2ab)), closes [#186](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/186)
* **test-skill:** skip §4b discovery test when catalog <2 skills ([5e160e5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5e160e55b7d50d9e69951cce0b20cd86e4196997)), closes [#177](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/177)
* **website:** restructure sidebar into Why/Try/Reference buckets ([e0780f8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e0780f8bc773f3cfd41d2b96b26bd78041963b84))

### Bug Fixes

* add full test suite to publish workflow before npm publish ([5c43294](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5c432944884e565503ef51c94b94c6f5d6ad7978))
* add missing feature request template and fix bug report typo ([f1d90a9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f1d90a9459c2f05ceadfa03350bf2941c4988289))
* add missing hasSidecar field to core agent unit test ([d6a5d29](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d6a5d29a649b85ffc3110db1b38f93a499ded071))
* align CSV row ordering with forger capabilities table and populate args ([47c65f8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/47c65f891b541df283393a55ca4557de04539212))
* **changelog:** strip bogus non-numeric closes refs from seed output ([a701efa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a701efa841d46567c71e29c54e5a73db39d572d4)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5)
* correct three-case to four-case in export step-04 and declare zod devDependency ([0680b44](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0680b442f713609d07980520ea900f1221f76f75))
* **create-stack-skill:** file-intersection fast path for pair analysis ([dbc4107](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dbc4107567d9f27e971de19eba0c3db8972f96df)), closes [#174](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/174)
* **docs:** quote remaining clone paths + camelCase fix in feasibility schema ([9170d5d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9170d5d1c3a501dba6e270b9871c0600f36413f0))
* exclude reports, pycache, and dev tools from npm package ([a269e43](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a269e4323b170acc9696f49e1e385a9ac10cc3d4))
* expand bmad-synergy doc to reflect all 23 IDEs with per-IDE skill roots ([8b56e7e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8b56e7ea382476ea4c5680baf7b2fdea0722a33b))
* expand IDE mapping to all 23 IDEs with per-IDE skill root paths ([e9ccde3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e9ccde3154792d82e877c5c90c7fd4e5d755a834))
* **export-skill:** detect snippet root prefix vs IDE skill_root mismatch ([54b059d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/54b059d1c477f2c59f48840a4d7140c09c27f975)), closes [#190](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/190)
* **health-check:** ensure fp-* label exists before gh issue create ([3554a24](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3554a24c026e1ba6df7d70d7387b52cba996dfba))
* quote interpolated paths in shell snippets across resolution protocols ([dcb9304](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dcb9304b3835d47a609622f948cb44a4515d5eff))
* **release:** accept admin-bypass merge as equivalent to approval ([c9ccffc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c9ccffc876cf8db174c16fb5bf3ebfc013793a5a)), closes [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [196/#197](https://github.com/196/bmad-module-skill-forge/issues/197) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199)
* **release:** address code-review findings (5 patches) ([34ad130](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/34ad1301c4d8cf11d281cafcc6127ceecc16c181))
* **release:** assert npm >=11.5.1 after $GITHUB_PATH update ([535e38f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/535e38fdfd485e24ccf258053b2f97ca5c8b25fc))
* **release:** force npm self-upgrade to survive arborist rebuild race ([f449c67](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f449c67c880bf5f8992822ea5c86f62d05c9c5da)), closes [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11)
* **release:** harden CHANGELOG preamble-restore guards (Story 3.3 code-review) ([6a6a521](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6a6a521cb6ad57b7bcb5e1993fb5ed35cc8d7d0a))
* **release:** harden Story 3.4 PR-auto-merge flow ([9467b4d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9467b4d7a942e65dc63926bda2dc8409f04a105a)), closes [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [#16](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/16) [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11)
* **release:** pass --tag in pre-publish dry-run to match real publish step ([de2334b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/de2334b0d54ec88e7cf168543d4fda72bc4f8f6c))
* **release:** poll commit check-runs API directly in Wait step ([081ddb1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/081ddb102e1d21e1122bd20d330fb5b86c0ee6d0)), closes [#1](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/1) [#2](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/2) [#3](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/3) [#4](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/4) [#5](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/5) [6/#7](https://github.com/6/bmad-module-skill-forge/issues/7) [#14](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/14) [#15](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/15) [#199](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/199) [#200](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/200) [#202](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/202)
* **release:** preserve spaces in required-context names (Story 3.5 followup) ([add467d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/add467d59611da21d647c20b0894af7c8cab147f)), closes [#203](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/203)
* **release:** restore CHANGELOG preamble after conventional-changelog -s prepend (Story 3.3 from Story 3.2 HIGH deferred-work) ([10c1134](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/10c113443f9f699fe3571883f767b0d198c5c5f7))
* **release:** set HUSKY=0 job env to skip local git hooks in CI ([cae5861](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cae5861a1b2f10d9d0f274337f9027d4f1adb213)), closes [#11](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/11) [#12](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/12)
* **release:** side-prefix npm install to dodge self-upgrade rebuild race ([cbc7851](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cbc7851b20225e907537269551703965d3f0a525))
* remove reserved --update-spec flag from skf-setup ([b625332](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b6253329fd714648dbb00144b9e485b6109788ad))
* rename skf-setup-forge to skf-setup, move module files to assets/, fix CSV alignment ([f670a11](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f670a1170ff4678a515feedd933fd40a491960fb))
* replace stale platform terminology with context-file/IDE model across step files and docs ([5ff42f7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5ff42f7689477c94ae523de1ca5350b5e260e387))
* resolve 10 issues in skf-setup workflow found during release audit ([adaa891](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/adaa891a40e43c6076f279a509eeaf2d2fc499b4))
* resolve 15 issues in skf-create-skill workflow found during release audit ([5b8fa4a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5b8fa4a5cc88527941f3e466d04bb367205039fa))
* resolve 5 issues found during commit review — encoding, regex, parser, docs, orphan ref ([b7f75c2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b7f75c21aba9bdd9afe97b2691e0278320a9d015))
* resolve 5 issues in manual-release and docs workflows ([32559e9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/32559e97b779062477f3674026336c1e9655ce58))
* resolve 8 consistency issues found during commit review ([304b0af](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/304b0af9f079ed2ab55a460dfd5480b700146c3a))
* resolve 9 issues in skf-test-skill workflow found during release audit ([7353b4c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7353b4c19153c7051c059a34813c206742a0d584))
* resolve stale references, validator gaps, and documentation inconsistencies from skill migration ([70854d7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/70854d77752ce67bfc5d244aa25bfe972b358d8f))
* restore module.yaml and module-help.csv to src/ root ([d698194](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d698194a520a2e7d2681b724b2db070cd0355123))
* **shared/scripts:** explicit utf-8 encoding on all text file I/O ([e7815bc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e7815bcf1d45a8cb46c535432dcc772cdc1fa015))
* **shared:** atomic-write cross-platform hardening + Windows junction fallback ([f19a4db](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f19a4dbcb32db34db5c76afe448bfc0424d6fc2a))
* **skf-analyze-source:** mirror JS/TS monorepo version detection rule ([94e3982](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/94e3982642dd5ca32b41bc875f25f57dd357e2a3)), closes [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126) [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126)
* **skf-audit-skill:** bound re-index to provenance-map file universe ([18ed601](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/18ed6013208f823601f4a3d55065d0efed20e7c8))
* **skf-brief-skill:** add JS/TS monorepo + pre-release fallback to version detection ([7edb4f9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7edb4f93175bb1414435f170911393c00c99fd9e)), closes [#126](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/126)
* **skf-create-skill,skf-test-skill:** plumb scope.tier_a_include through effective_denominator writer ([ff1dc72](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ff1dc7252d4a2c002b4a672f49470bfcc12ad5fc)), closes [#134](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/134)
* **skf-create-skill:** apply v1.0 ship-review CRIT+HIGH+BLOCK+SERIOUS ([30a7244](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/30a7244493cd4075e4443579df9d27fe909dbd94))
* **skf-create-skill:** drop -skill suffix from staging directory ([786d17d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/786d17da8828c94a56b2826b00a43d7348bf0c7f)), closes [#114](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/114)
* **skf-create-skill:** name the compile staging directory ([6e07634](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e07634d97ce8d8b08e74f6f79ebf3176c3a653d))
* **skf-create-skill:** polish — magic-number rationales + subprocess timeouts ([5f5a6c0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5f5a6c0d92d9000eefc97547a18cb081dd2b55ec))
* **skf-create-skill:** rewrite python-public-classes rule for ast-grep 0.42.x ([431cbf8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/431cbf8f37d40ceb36f69e248e07e61a825dee5b)), closes [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7) [#140](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/140)
* **skf-create-skill:** route promoted authoritative docs to file_entries ([7b9c99c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7b9c99cf87e118bec02e4bba61d52f9de0d7c5a1)), closes [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116) [#116](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/116)
* **skf-create-skill:** sanitize angle-bracket placeholders in description ([ee17db5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ee17db535ee66c7179d1febbcd78d737261048c8)), closes [#115](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/115)
* **skf-create-skill:** tighten sanitizer regex against inline generics ([bc078b8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/bc078b890f8240f6340905c4d66b0f7abdaa7587))
* **skf-create-skill:** unconditionally sanitize description angle brackets ([3b40e7c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3b40e7c134faaa74254fa2525533b5668c9ce425)), closes [#127](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/127)
* **skf-create-stack-skill:** atomic stack writes + schemaVersion guard ([84f37af](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/84f37af6cf9611ff6172f94a0621c5139534e3d4))
* **skf-create-stack-skill:** close M1-M4 polish ([a5e5d2c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a5e5d2c96bf246df6c09698367f907dbb9f987a4))
* **skf-export-skill:** raise snippet token warning threshold to 300 ([f4d558d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f4d558d317da1b4e26fda43bcb67b9d9a45b52bb)), closes [#146](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/146)
* **skf-export-skill:** rename manifest platforms field to ides ([b1ea4cd](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b1ea4cd2aa386431d024ada004f3cab8df4e5953)), closes [#148](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/148)
* **skf-quick-skill:** add Java/Kotlin coverage to manifest + export scan ([2659b44](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2659b44bd8799fca4b5b440a1ef9a752deb17ab6)), closes [#162](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/162)
* **skf-quick-skill:** make active pointer Windows-safe via shared helper ([7850054](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7850054861423f0f9cff7d435065534a9d0b8a07)), closes [#164](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/164)
* **skf-quick-skill:** write deliverables in step-05 so validation has files ([dc620a2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dc620a26722ffebbdd0057a9a6755ee3f19ceccc)), closes [#163](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/163)
* **skf-test-skill,skf-brief-skill:** honor scope.tier_a_include in stratified-scope denominator ([ad7105b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ad7105b22e19202bfe0a7dd252242556304789bc)), closes [#134](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/134)
* **skf-test-skill,skf-create-skill:** stratified-scope denominator for curated monorepos ([ece7934](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ece7934dd7dc550a0f14b4d02e1f0bee456e76c1)), closes [#128](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/128)
* **skf-test-skill:** bin export-count drift check by semantic cluster ([e3edc91](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e3edc913ef3d63e70958969858c80d3be2386f82)), closes [#143](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/143)
* **skf-test-skill:** close M1-M5 polish + matrix-class fixtures ([8167a34](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8167a343bd772103ac8bec840d2be1c4e9b5f687))
* **skf-test-skill:** cross-check metadata export counts in step-03 §4b ([4404455](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/440445506007d8487fe9b841a7d029ef55262c30)), closes [#135](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/135)
* **skf-test-skill:** detect single-commit update-skill bundle in step-04b staleness check ([e6704fc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e6704fcb9a9cc38d2b328c0b5b3be10279ff5815)), closes [#136](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/136)
* **skf-test-skill:** formalize Section 4b historical-migration exception ([96a937e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/96a937e2a84bfeceb7bd57fb509c1b3930b3a2ec)), closes [#129](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/129)
* **skf-test-skill:** minimum-evidence floor + INCONCLUSIVE verdict ([58da265](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/58da2651fea7000cc135e5be52e56945a7509c46))
* **skf-update-skill:** add gap-driven branch to step-03 re-extraction ([2faf887](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2faf8878f5cf1d9783f7fa452b791313190ec8f3))
* **skf-update-skill:** add targeted re-extraction branch for citation-less Critical/High gap-driven entries ([f94a466](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f94a466357636f8d15818eceb63b374e39541052)), closes [#132](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/132)
* **skf-update-skill:** apply description guard to step-06-write ([44e76fe](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44e76feadee5af7489785ae87d61d22fb8d7b0fe))
* **skf-update-skill:** make step-06 §5 context-snippet regen conditional ([7d72553](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7d72553845bb034c9b419042b2915932d0d17745)), closes [#123](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/123)
* **skf-update-skill:** materialize §2 pre-filter exclusion set mechanically ([897e778](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/897e7786baa1a73cc21f7c22b852bf2a111664b1))
* **skf-update-skill:** preserve test-report citations in gap-driven manifest ([dff3e9b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/dff3e9b1c5b5d8c965069335c574cf8a92af2372)), closes [#122](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/122)
* **skf-update-skill:** skip version bump in gap-driven mode (step-06 §2) ([c3c7e53](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c3c7e53c69ea9fdc08017a55eb611a8d05b7fe2a)), closes [#121](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/121)
* **skf-update-skill:** update stale §2c refs missed by renumber in step-02 ([44ca6d5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44ca6d587ae66ebbef2d61e0a97e19d6fd442506))
* **skf-update-skill:** verify active symlink in step-06 §6 ([657f394](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/657f394338c81e20208e7f76bad74b9253cba777)), closes [#158](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/158)
* **skf-update-skill:** write merged files in step-04, verify in step-06 ([97a839c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/97a839cd901cfcce9d9e2e7cf86139f3d1b62554))
* **skf-verify-stack:** close M1-M5 polish ([cac5501](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/cac5501a47a0a7d504f61ce2fbd60923fa4f85d9))
* **skf-verify-stack:** require Check 4 citation for Verified verdict ([8c20873](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8c208739e265c79269c61df0e3e05d4aa34a12a9))
* **skf:** align tessl parse label with actual CLI output ([c9bf1de](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c9bf1de4b9f039db065cb6eca5db22a7e4cf2168)), closes [#111](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/111)
* **skf:** pin T2-future detection to evidence-report frontmatter ([ef10c94](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ef10c94a06939ec9881e4707ebcb85bccee3864c)), closes [#182](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/182)
* **skf:** resolve skf-atomic-write.py across src/ and installed layouts ([299d369](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/299d36962e010f29f69886bb6c782deb73b1fe6c)), closes [#178](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/178) [#173](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/173) [#178](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/178) [#173](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/173)
* **test-skill:** §2.3 bare-fence rule ignores closing fences ([755f2cb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/755f2cbdfb8f52b8fb4f885473779db519fa0a1d)), closes [#180](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/180) [#184](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/184)
* **test-skill:** §2.6 table column check handles escaped pipes ([a03ddef](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a03ddef8b2272c1b5c79d4b5e876f20276866b21)), closes [#185](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/185)
* **test-skill:** accept SKF-template section names in §2.1 ([4e1a759](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4e1a759bcb4cfb937d2da1106ace24acd8f7a90d)), closes [#183](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/183)
* **test-skill:** drop skill_name from coverage §1a required keys ([32f8273](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/32f82730dffc99b04f05b86e0b6dbd68f2dca0f7)), closes [#181](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/181)
* **test-skill:** unpin tessl, use probe-verified binary ([d8d4055](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d8d4055a727063f584a2135e4cb50d1589f92cc3)), closes [#175](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/175)
* **test:** explicit utf-8 encoding on all text file I/O ([e06ac5f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e06ac5f0e245ff3d17039905a3208ef5bc2cc2ea)), closes [#165](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/165)
* update 3 stale references to ephemeral-only clone terminology ([eeb0f07](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/eeb0f07721c6b884c7876b77abe7231fea8e80ec))
* **workflows:** document shared/health-check.md path resolution ([d899046](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d8990465a78bfaab878c8baa7442e8a5e7e4d847))
* **workflows:** guard against workspace HEAD drift before spot-checking pinned source ([#154](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/154)) ([7328452](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/73284521a9dcbd853f8a7ed8a418fcaff7c268c8))
* **workflows:** remove premature workflow-complete banner before health check ([9d6fcf5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9d6fcf588ca317befe8bec431279e5e5bdc241ec))
* **workflows:** split health-check into its own terminal step across 14 workflows ([0448046](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0448046af7b0e5fbffd490a05d44dc153ed92785)), closes [#152](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/152)
* **workflows:** timestamped result JSON filenames to preserve audit trail ([#155](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/155)) ([e4f392d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e4f392d3f98fd3b74b44677c2df57be0e39077d2))

### Reverts

* Revert "chore(release): add temporary push trigger for Story 3.2 alpha cut (revert in same story)" ([7208ff4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7208ff48640e97a2175b99b5d21dde192d85fdb3))
## [0.10.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.9.0...v0.10.0) (2026-04-06)

### Features

- add plugin reload hint to export-skill summary ([4a55109](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4a55109813616e3cdd677a80627218ba590a0cee))
- add workflow health check for self-improvement feedback loop ([9a9bf8a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9a9bf8ac678076beb106973511643732ee337e3a))
- show fresh-context reminder with every menu display ([3085fb7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3085fb7c7b0b8525e36e1b6f4bc6b96db6306bc9))

### Bug Fixes

- resolve health-check wiring contradictions and missing coverage ([1a171d1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1a171d1a5a6c135c9e147a7e6f24d091d9131235))

## [0.9.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.8.4...v0.9.0) (2026-04-06)

### Features

- add rename-skill (RS) and drop-skill (DS) management workflows ([65ac73e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/65ac73ed269f11f1c375f6b91c6a99bb91660c88))
- add version-aware skill directory structure across all workflows ([f9dff2e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f9dff2e257f1d118acedadf48dc90763434592da))
- add version-specific briefing with tag-based source cloning ([6470934](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6470934157c202904a58c1dc15a5acd9c0ef1b92))
- consume config.yaml ides list for multi-platform export ([1d20d90](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1d20d904392028274774fd56f8aefad0d19d741b))
- show installed and incoming versions in installer prompt ([09cfa99](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/09cfa99fb6351e3a2fd7b50ea8a8bea0fa33c66b))
- show npm version badge in docs header ([f63c75b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f63c75ba976abe84b5cd2f82ed78ae7aeb67e092))
- surface local install command in export-skill summary ([9e98128](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9e9812848db1a84cfde61d1c764a0e441f225523))

### Bug Fixes

- address multi-platform export regressions and cross-workflow consistency ([681a890](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/681a8909dccd216f40585b64ae271dbe61602b2e))
- default platform fallback to copilot (.agents/skills/) when no IDE detected ([06bf95b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/06bf95b9fff1341155f9b4e46d7d0d4eae36434a))
- gate managed section rebuild to exported skills only via manifest ([482b984](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/482b98456475e4545bbf37565ab58e4bca6177fc))
- map config.yaml ides values in drop/rename and allow draft purge ([e8406e4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e8406e41ef86fd8cfc46985e6d972467404baa34))
- preserve prior gotchas on re-export when new derivation yields none ([4a7ada1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4a7ada174c7d5b2849bbbbbf7852b10c77c65097))
- resolve cross-workflow consistency regressions from recent feature work ([0952c49](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0952c493ec1b30fa8bc96d83a4545f9f246fe412))
- use platform-specific root paths in context snippets per ecosystem spec ([4af5744](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4af5744877b79605a5f20972eb388ebbf07baf70))

## [0.8.4](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.8.3...v0.8.4) (2026-04-03)

### Bug Fixes

- replace silent Quick tier fallback with HARD HALT in test-skill and brief-skill ([3fb7152](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3fb7152421d7c85bf8e8803391f94ca1e9a43bd0))
- write sidecar_path to config.yaml during installation ([ba0d081](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ba0d08150054a745965ce90846e3dffa1e8ecdf9))

## [0.8.3](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.8.2...v0.8.3) (2026-03-29)

### Bug Fixes

- clarify scripts/assets detection defaults when brief fields are absent ([528b4e1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/528b4e1b48538f2d0f9fbb37cece1616a42fcae8))

## [0.8.2](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.8.1...v0.8.2) (2026-03-29)

### Bug Fixes

- apply brief exclude_patterns to CCC settings before indexing ephemeral clones ([36e1a86](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/36e1a8683a5dd3e52eaf00c731d068a0a62a33ee))

## [0.8.1](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.8.0...v0.8.1) (2026-03-29)

### Bug Fixes

- resolve workflow documentation bugs across test-skill, create-skill, and update-skill ([5a584ca](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5a584caeb67b23682e826e0775c17f4937cd42e4))

## [0.8.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.7.4...v0.8.0) (2026-03-29)

### Features

- add component-library extraction strategy and compilation overrides ([ea73305](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ea73305b111d386aeb6605d21657645ce1d6f925))
- add component-library scope type for UI component library extraction ([85766eb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/85766ebcf15d8b5955dc1d90429ea66e3326940a))

### Bug Fixes

- add sidecar_path to module config for installer resolution ([e099cb4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e099cb4f9569b48d01c5bac5645cdfbf084e3fa8))
- correct CCC CLI flags, ast-grep templates, ephemeral cleanup, and version detection ([4e14439](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4e144398160fa6d688320e0a5b75dc8eb4c04975))
- resolve source access before component-library delegation and no-cone file pattern bug ([72c29e7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/72c29e7401c78a814a3333ad6c5dfcff21799034))

## [0.7.4](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.7.3...v0.7.4) (2026-03-28)

### Bug Fixes

- add CCC index exclusions and deferred discovery for remote repos ([80254ef](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/80254ef51904bc9985a493fc1eba49eec1cac630))
- replace 60s hard timeout with extended timeout pattern for CCC indexing ([26279a6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/26279a618b9b1bfea751640a40118d008770409b))

## [0.7.3](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.7.2...v0.7.3) (2026-03-28)

### Bug Fixes

- resolve 14 workflow issues and 3 undocumented bugs across brief-skill, create-skill, and test-skill ([22c8301](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/22c8301066fd9f21c866dca064caf26632ecf4d2))

## [0.7.2](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.7.1...v0.7.2) (2026-03-28)

### Bug Fixes

- resolve 30 workflow issues across brief-skill, create-skill, and test-skill ([0ab7b58](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0ab7b5834c515390fa3588d0ebd1c56a4f9a34d3))

## [0.7.1](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.7.0...v0.7.1) (2026-03-27)

### Bug Fixes

- correct ccc init syntax and add ccc index timeout guidance ([694f8fa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/694f8fa1e80647cedaf35a3cbe60741ec5f6907e))
- resolve 5 bridge/subprocess/manifest/T2 issues across all workflows ([f1aa547](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f1aa547d721db92036f1fcf52744879cdda9db50))

## [0.7.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.6.0...v0.7.0) (2026-03-27)

### Features

- add [RA] Refine Architecture workflow for evidence-backed architecture improvement ([153b451](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/153b4514ee698947b88e0b33b69db0a961fee029))
- add [VS] Verify Stack workflow for pre-code architecture verification ([3275418](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/327541892ea497562105ce21e964e407ef5d09ad))
- add compose-mode to create-stack-skill for synthesizing from existing skills ([76d5890](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/76d5890e1b996346c84392cf4a9e2529d4e9dd83))

### Bug Fixes

- comprehensive quality and review fixes across VS, RA, compose-mode, and docs ([47c5276](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/47c5276a03557eee45a899bd65452683a14b6dd9))

## [0.6.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.5.0...v0.6.0) (2026-03-25)

### Features

- add CCC semantic discovery phase to create-skill workflow ([b0c17b7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b0c17b7ec918caba94b705acb7a14322c4c840af))
- add Forge+ tier with cocoindex-code (ccc) semantic discovery integration ([56085f9](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/56085f9b55addb684a2989da3efedab1ee715a8d))
- complete Forge+ horizontal integration across all SKF workflows ([7cfb686](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7cfb686c039c1237d88c6e3610b29a42b8137539))

### Bug Fixes

- address all 15 review findings for Forge+ tier integration ([6e7b94b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6e7b94be9d0b56d33dfc0d280b2a5950e098085c))
- comprehensive review fixes across all 10 SKF workflows ([44733a6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44733a6fea40d54ca675fd6fd4a1d7c678df5e45))

## [0.5.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.4.0...v0.5.0) (2026-03-21)

### Features

- add click-to-expand lightbox for Mermaid diagrams ([16c114a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/16c114a421168bf413b676647664d8bc283bfbc3))
- add scripts/ and assets/ generation support across all SKF workflows ([7de1eb1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7de1eb1efd94f6084bcce75174cb456d2993e727))
- add split-body strategy knowledge and selective split guidance ([b79a5ca](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b79a5cae26ed40a894c7b44c2b76ffb51825d3f3))
- enable Mermaid diagram rendering in docs website ([437af74](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/437af74c3addb68adb4f243a4069c4a9e4405999))
- integrate skill authoring best practices and fix pre-existing workflow bugs ([073db2e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/073db2e7ed4b6c022a456b10e0d9bbb2f016d771))

### Bug Fixes

- adapt lightbox background to current theme ([2a1fdb6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2a1fdb6598edeb47f15ef1acf834b47eceb83fea))
- add staleness detection to external validator auto-reuse logic ([6078d08](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6078d085c7e73d3cc1c2979ffff6ad97279b8c21))
- address review findings across all split-body-affected workflows ([a51f0d1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a51f0d1010994f5340399af8daa2935b3fd4c681))
- extend coverage check to traverse references/ for split-body skills ([d5b6ad4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d5b6ad43bf957e731390ab27ca2a75e3978d66b1))
- install website dependencies in docs CI workflow ([b17caf3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b17caf34675d3c2450f41ab23a6de746ce96ccb9))
- populate metadata.json description, language, ast_node_count at compile time ([10203f4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/10203f43b46e242c122f047106cadc9cdbed2104))
- verify snippet anchors against SKILL.md headings for split-body skills ([8496430](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8496430473e43448be4551b51eef8e62494634b3))

## [0.4.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/v0.3.0...v0.4.0) (2026-03-19)

### Bug Fixes

- add reuse check for recent validation in test-skill ([52f572c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/52f572cd426edac49577290611daccdc4b2b9a8b))
- auto-include root version files in sparse checkout ([3d79918](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3d79918d85e9745fd3bb30afb83a14968b0d896d))
- extend re-export tracing to handle import aliases ([0d1bc03](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0d1bc03462cbe065ee3410942c1c4c1f0378939e))
- make provenance-map degradation notice confidence-aware ([282f692](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/282f692a01026d46fad839197075959b8f52572e))
- re-read SKILL.md after skill-check --fix modifies files ([17eb65c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/17eb65c21c5727150c927804e6ac04dbdc1eb243))
- replace hardcoded SKF version 1.0.0 with dynamic placeholder ([535ca61](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/535ca6116ef7513283a95c534cb68e4cb6eedb4d))
- resolve all HIGH and targeted MEDIUM validation findings ([6775fe8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6775fe830b6ebb805a54db6bff48be456fa643d6))
- resolve deep review findings across docs and tooling ([e6178d7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e6178d7f73dfa1686b75a6f4859bf233117e8bd1))
- resolve deep review findings across issue fixes ([490ea00](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/490ea006550eea06d7b0c110cc6e275d6cc6ef64))
- suppress BrokenPipeError in CLI streaming template ([8917330](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8917330ae34c202754568392c87550e0a757aac1))

## [0.3.0](https://github.com/armelhbobdad/bmad-module-skill-forge/compare/88b8f51878fd2d2c8564cfe5650c6e1ce220dd30...v0.3.0) (2026-03-19)

### Features

- add `status` command to show installation state and configuration ([41ebc96](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/41ebc96b952d4905050808d3c17ac878f443b90c))
- add `uninstall` command for manifest-based clean removal ([55337fe](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/55337fe2974666767935c312c440cf942e228792))
- add `update` command for non-interactive SKF file refresh ([40a73c3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/40a73c34b19da2979a8c15e1f2d06a0d9f05335f))
- add AST Extraction Protocol with streaming, MCP-first decision tree ([c251801](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c2518017eda21c89c7d6f9836bde6fd8602d1014))
- add ephemeral cloning for AST extraction of remote repos ([559b73f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/559b73f0bb8aae5026991dc8e8a936dfa0482c12))
- add npx CLI installer for standalone SKF installation ([a4e12e8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a4e12e837c689b8f5aa3a4f80131ebb21e4fa99f))
- add QMD brief collection registration to brief-skill workflow ([9266240](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9266240ba112fa9cde4c1afcbea978de5c7ba03e))
- add temporal context fetching for Deep tier T2 enrichment ([24a0747](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/24a07476941b00c0941d7b671e1dcb426c4df523))
- add user decision gate after tessl content quality review ([#37](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/37)) ([5c2ea62](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5c2ea624c45a5f510b5ad9e8517a2c6c58348d38))
- async version check against npm registry on CLI launch ([df112ce](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/df112ce84ea56ea951c169f1818bed1fa255571d))
- auto-add `_bmad/_memory/` to .gitignore during install ([366c961](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/366c961deb205597b2fa6d6a6e0132bd16bd6a8a))
- auto-detect IDEs from project directories during install ([385e9c8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/385e9c8fc7e728eaf9e4dc22cfdd1fc8debaa8de))
- connect doc_fetcher to QMD pipeline for Deep tier enrichment ([a3105a1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a3105a1268189ef7462d17df2ebe83b6b96433cd))
- contextual post-install notes for fresh install vs update ([06917a7](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/06917a76e20a774727fd3cad109b741576ba3fe6))
- **docs:** add documentation site infrastructure with Astro + Starlight ([51562e1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/51562e1b472424b08ca571c290bb91ef9f1b2499))
- **docs:** align website infrastructure, update messaging, add logo ([02c1059](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/02c10593ec47df7ea7a7395dc491449be313bfb8))
- enhance context-snippet format with description and refs index (ADR-L v2) ([469c696](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/469c69624c8a91605704da4b8e20b6ed5714113a))
- generate IDE command files during standalone installation ([f4a1f73](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f4a1f738ef7492ab87c2d4eeda051828498e6cde))
- implement doc_fetcher for T3 external documentation support ([a8ed919](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/a8ed919cbbbea316ba64b5c5a113c7531684fd87))
- improve Deep tier extraction-enrichment pipeline coherence ([ba3c179](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ba3c179306aaf472ae5f779fa77e4170ba3fa10d))
- integrate external skill-check CLI across all validation workflows ([44d66f1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/44d66f1f8c35ce1d0bfee78999a21fc63f8cabf4))
- integrate skill-check and tessl as external validators ([#20](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/20)) ([9bda903](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/9bda9034fefd7b4f0d062cc5096cc35f6da7eb7b))
- pre-populate install prompts from saved config on reinstall ([18a293e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/18a293ecbaa771bde62a5ebd7302555154fcc970))
- redesign CLI with brand colors and ANSI Shadow banner for v1.0.0 ([146189e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/146189ec4d58928c041fa84d807e78a70383a9cb))
- redesign context-snippet format with Vercel-aligned indexed structure ([#38](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/38)) ([0e6bf0f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0e6bf0f56d14a8df8fdc58c4becf47e08afe0e3b))
- **skf:** add complete SKF module with agent, workflows, knowledge base, and docs ([88b8f51](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/88b8f51878fd2d2c8564cfe5650c6e1ce220dd30))
- two-tier SKILL.md assembly to survive split-body extraction ([#21](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/21)) ([ceb2f49](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ceb2f49c57fdc6feec3f707dd054c4f6b3a048a6))
- write installation manifest for uninstall and smart updates ([efd4dbc](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/efd4dbc3ca9ca3fd6d44583a420504710fd4597f))

### Bug Fixes

- add empirical skill-check verification across all validation steps ([c154109](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c15410919b09c4310d571f778e2083a5953ff0db))
- add qmd embed after every qmd collection add for vector search ([#33](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/33)) ([5d9b6d6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5d9b6d6f61c8f6e4362ec01dca6bbf17312b6698))
- add re-export tracing protocol for module-level imports ([#46](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/46)) ([2cd2a88](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2cd2a88736361edf721045223b48d2c1eda0ccf0))
- add subpage discovery for documentation root URLs in doc fetcher ([#34](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/34)) ([d2960d0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d2960d0656be6ae5f620260457b834fe63aabcf6))
- add test-report-driven update path to update-skill ([#55](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/55)) ([31b7d03](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/31b7d03d82502f0c8d79071fa17970b613ce87b7))
- add version reconciliation to prevent brief/source version mismatch ([#32](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/32)) ([880e82c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/880e82c176656aaa1cad6a2de4d88e6912d6473d))
- address 4 workflow bugs found during Deep tier create-skill test ([8c3512a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8c3512adf3e0b31b1716f2520857085a3f75ddd4))
- align all snippet references to ADR-L v2 format (~50-80 tokens) ([399ba4d](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/399ba4d66de663c7ef98ddb3c42ca6892b2b8104))
- align CI workflows to Node 22, fix release script, add changelog ([369f250](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/369f2502f948fe61196086b169f81a6e851861f3))
- align MCP tool names and confidence labels across workflows ([8344562](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/83445627a0651fbc8fc9eb4517e9bbfb81f3da37))
- align merge/validate/write steps with Claude Code editing model ([#56](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/56)) ([5b4c0c5](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5b4c0c581820d9f1ce2c88a3ebd06bee8ae5e521))
- align metadata.json field names to export-skill authoritative schema ([b9d2816](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/b9d2816482001f262ea548cd0e2a002efbb67362)), closes [#13](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/13)
- align update-skill write step with actual metadata.json stats structure ([3861c2a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/3861c2ac6d251ef3d9d76ca00ec190e662a82a89))
- analyze-source enhancements for issues [#60](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/60), [#61](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/61), [#64](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/64) ([5d5ae24](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5d5ae248413fdd9e8226b9250af97c7c402afa94))
- apply exclude patterns via sparse-checkout --no-cone mode ([#45](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/45)) ([7a7f6b6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7a7f6b60546725833dfcf4b6a8ce612a500b1a04))
- artifact-aware source resolution for coverage checks ([#53](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/53)) ([09520b1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/09520b1854ab578194b7f2a13e76379cb56dfbfe))
- batch fixes for issues [#59](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/59), [#62](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/62), [#65](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/65), [#66](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/66), [#67](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/67) ([2c68c60](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2c68c603d0ede3e315afdee75f52092b91474cd6))
- clarify 'files in scope' means filtered count, not total repo ([#36](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/36)) ([5587e42](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/5587e420fa1dd11e70e4723b131f582dca377d81))
- clean stale IDE command files and empty directories on reinstall ([60d7019](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/60d701986474ddd4f4c36738f81a84dd0ec44ba9))
- complete docs-only pipeline support across all lifecycle workflows ([42da9f2](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/42da9f24957d7b6dff94a148e10eba54e979ceca))
- convert glob include_patterns to directory roots for sparse-checkout ([#30](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/30)) ([2fa80ee](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2fa80ee4b67159034b3bbdb811b8dd0512b99664))
- correct Snyk Agent Scan repository URL ([ae0f255](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ae0f2554bb49d217299c52cf41810059cf870ada))
- correct sponsor link to point to armelhbobdad ([e74c47b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e74c47b9460bb536d943fa3c58cb32e8ff23df37))
- correct Vercel research link in architecture.md Dual-Output Strategy ([23133eb](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/23133eb12bedd55a88489d70208b2b3f98a2a671))
- defer threshold field to step-05 where scoring rules are loaded ([#51](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/51)) ([f26774a](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f26774a47d142ae5fd4e6bbd27e4d9b299214c6c))
- define source API surface for coverage denominator ([#52](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/52)) ([1c809ae](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/1c809aeeb0cebc35d8c199ccda8f4c719f94b2f5))
- differentiate Tier 2 content from Tier 1 to avoid tessl redundancy penalty ([#35](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/35)) ([abcb0b3](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/abcb0b34d6f40da754f6265807c52dda99ad3b83))
- display version number in install banner ([e1934aa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e1934aa560f51c8442c8ac94b8d982124f5e5ad3))
- distinguish public API vs internal exports in metadata.json coverage ([#44](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/44)) ([428c5a4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/428c5a4de10aca46fc576ed0ebe626394d1f95ab))
- enforce agentskills.io frontmatter compliance in create-skill and create-stack-skill workflows ([0ffcfb0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/0ffcfb0a1ce8d5698c9ec498f705e0921da5bdce))
- enforce agentskills.io frontmatter compliance in quick-skill and test-skill workflows ([d9bd9d1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d9bd9d129eb81a337e9cdf02dd7ab0e49f1655ae))
- pre-filter exclude patterns in CLI streaming AST extraction ([#42](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/42)) ([2b3b323](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2b3b3232b6e0694ce333db9cf1c69f2848e9e527))
- pre-release audit — correct 11 documentation inconsistencies ([8761089](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/876108967e75c7e0f09f3d3023a5ce89cef70016))
- propagate Vercel-aligned snippet format and tessl gate to all workflows ([8ab948f](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8ab948f404ae8fe0198b5098d3b275ab33f40e82))
- quote YAML frontmatter description containing colons in audit-skill workflow ([8b9970c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8b9970c8b65832e36f89792c16a3918d980ede2f))
- recognize MCP tools as first-class source access in update-skill ([#57](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/57)) ([1570092](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/15700923ceeaffc74cdf2a88ce8e65c2ff1d020a))
- remove stale version/author frontmatter reference and fix broken anchor ([03bbb37](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/03bbb37150d19d8932377b2239bb8b8e906b6975)), closes [#7](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/7)
- remove undefined cross-workflow subprocess pattern references ([#54](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/54)) ([4e1a809](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/4e1a809360f959f791e6e04d29a303b2eebfc832))
- replace free-text provenance claims with structured export entries ([#58](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/58)) ([e22da52](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/e22da52e707ea750dcbd7be252693151d130b072)), closes [#53](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/53) [#56](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/56)
- replace npx skill-forge with npx bmad-module-skill-forge ([46c5730](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/46c57301a35c8a2ba7523c36e7d873894e0e0359))
- replace silent AST degradation with explicit warnings for remote repos ([#18](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/18)) ([7c491e8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/7c491e8edbce9f077210905b5ca788001d9712c6))
- replace subjective root page threshold with concrete heuristic ([#47](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/47)) ([f3aa88b](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f3aa88bdae1701399a069fc064b9d4df0f4710f9))
- resolve 12 BMAD compliance issues across 6 workflows ([f87ae7e](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/f87ae7ee8e82974dcb23466706572b1584e022d1))
- resolve 23 cross-workflow data contract and pipeline issues ([6f204d0](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/6f204d071a8d5269bdff4470deaa7c86dc243bca))
- resolve broken runtime path in update-skill extraction protocol reference ([8802be1](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/8802be1cdaf970ad4b161d4329941edc2da20d69))
- resolve cross-cutting consistency issues from deep review ([c318a6c](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c318a6cc08bb2b12b063b1d64364d773af941a05))
- resolve test-skill file size violations from validation ([78626bf](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/78626bfda38f3cab8553fbabb3dd63774988f899))
- resolve undefined {output_folder} in test-skill workflow ([#50](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/50)) ([d7fceaf](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/d7fceaf3e7beab8f503c57af4a8d4c8d2024de70))
- respect tier_override from preferences.yaml across all workflows ([79149da](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/79149dabecce96377ac7f41bdbe6102010d51521))
- smart auto-index excludes module internals and indexes all file types ([27fdd69](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/27fdd69f0bb7afba4b6583694e37bf90688a2fb7))
- standardize staging directory convention in step-03c ([#43](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/43)) ([05179fa](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/05179fa939f2b7a8061cd10bd710a3f39b6d1891))
- use BM25 search as primary for migration/deprecation queries ([#49](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/49)) ([2f08803](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2f08803e5611428214220c53042c14fdcb4ae19f))
- use cognee docs URL as sample doc link instead of stripe ([2fd29f4](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2fd29f499659e184d834185b07c8df107b5677c3))
- use relative paths for doc links to support base path deployment ([c8eb7ed](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c8eb7ed8535a3e3e096e915f03e2f17d2104b9c3))
- use slash command and correct docs URL in installer success message ([2411ac8](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/2411ac8fd6bf5695619652f5276a44b1d252fc99))
- use two-step gh release fetch since list --json lacks body field ([#31](https://github.com/armelhbobdad/bmad-module-skill-forge/issues/31)) ([c7f35f6](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/c7f35f6bc57cef6b46927327756a18eee5c53f7e))

### Reverts

- Revert "0.2.0" (pre-v0.3.0 tag, never published) ([ed2df11](https://github.com/armelhbobdad/bmad-module-skill-forge/commit/ed2df11237d3a785259a76938b6935dcf0368258))
