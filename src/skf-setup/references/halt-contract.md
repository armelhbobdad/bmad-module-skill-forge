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
