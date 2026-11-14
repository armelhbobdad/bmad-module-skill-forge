# Halt Contract

Every halt in this workflow that names a phase, in SKILL.md On Activation and in the step files, follows this contract; the step 4 tier-miss halt names none and displays its `tier_failure` envelope instead. Item numbers name SKILL.md On Activation items. When `{quiet_mode}` is true, run `<runner> <helper> emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>"` (`<path>` written with `/`; no `--path` for a halt without one): `<helper>` is `{emitEnvelopeHelper}` once item 4 bound it, and for the halts of items 1 to 4 `skf-emit-result-envelope.py` at its installed path, else its dev path (`{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, else `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`); `<runner>` is `uv run` in the step files. The halts of items 1 to 4 can fire before `uv` is proven present, so they run the loop below as written, dropping `--path` or the `--stderr-from -` heredoc as the halt needs: it stops at the first runner that exits 0 and prints a line starting `SKF_SETUP_RESULT_JSON:`, and prints that line (the helper is stdlib-only). Display that line verbatim, nothing else. If neither path exists, or no runner exits 0 and prints that line, display the reason alone as that one line. Interactive runs display the reason as their diagnostic and emit no envelope. Text from the user or a helper never goes into the single-quoted `--reason`: write `<message>` there and pass the text on stdin with `--stderr-from -` and a quoted `<<'SKF_TEXT'` heredoc, one per runner tried, for the emitter to fold to one line and escape. Once item 6 binds `{customization_resolver_unavailable}` to a reason, every later halt also passes `--customization-resolver-unavailable-from "{run_dir}/resolver.err"`, which the emitter folds to one line and escapes.

```bash
for r in "uv run" python3 python "py -3"; do
  line=$($r "<helper>" emit-blocked --phase '<phase>' --reason '<reason>' --path "<path>" --stderr-from - <<'SKF_TEXT'
<text>
SKF_TEXT
) && case "$line" in "SKF_SETUP_RESULT_JSON: "*) printf '%s\n' "$line"; break ;; esac
done
```

## On Activation Halts

Each halt of On Activation takes the `path` and reason its phase lists here, passed as the contract above says (item 1's `on-activation:orphan-action-invalid` names its own, with no `path`).

- `on-activation:config-missing` (item 2): `path` `{project-root}/_bmad/skf/config.yaml`, reason `Setup cannot proceed: the SKF config file was not found. SKF is not installed in this project: from the project root, run npx bmad-module-skill-forge install (or npx bmad-method install and add SKF), then re-run /skf-setup.`
- `on-activation:uv-missing` (item 3): no `path`, reason `Setup cannot proceed: uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and re-run /skf-setup.`
- `on-activation:helper-missing` for the parser (item 3): `path` `{project-root}/_bmad/skf/shared/scripts/skf-setup-args.py`, reason `Setup cannot proceed: skf-setup-args.py could not read the flags. Reinstall SKF, then re-run /skf-setup.`
- `on-activation:helper-missing` for preflight (item 4): `path` `{project-root}/_bmad/skf/shared/scripts/skf-preflight.py`, reason `Setup cannot proceed: skf-preflight.py was not found. Reinstall SKF, then re-run /skf-setup.`
- `on-activation:helper-missing` for the helpers (item 4, a `HELPERS_` code): `path` `{project-root}/_bmad/skf/shared/scripts`, reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. `, which names every missing helper or the file whose probe order cannot be read.
- `on-activation:config-malformed` (item 4): `path` `{project-root}/_bmad/skf/config.yaml`, reason `Setup cannot proceed: <message>`: its `error` without the leading `Cannot initialize. ` (else the first line the call printed), never preflight's whole JSON.
- `on-activation:run-folder` (item 5b): `path` `{project-root}/_bmad-output/.skf-run`, reason `Setup cannot proceed: the run folder could not be created: <message>`, where `<message>` is the command's first stderr line. Item 3 proved `uv` and item 4 bound the helper, so this halt runs its own pipe, not the loop: with no run folder to hold that stderr, a quiet run repeats the command with its stderr piped to the emitter, which fills `<message>`; a repeat that succeeds removes the folder it made, and its reason then ends `(no error message)`:

  ```bash
  { mkdir -p "{project-root}/_bmad-output/.skf-run" && rmdir "$(mktemp -d "{project-root}/_bmad-output/.skf-run/skf-setup-XXXXXXXX")"; } 2>&1 >/dev/null | uv run {emitEnvelopeHelper} emit-blocked --phase "on-activation:run-folder" --path "{project-root}/_bmad-output/.skf-run" --reason "Setup cannot proceed: the run folder could not be created: <message>" --stderr-from -
  ```
