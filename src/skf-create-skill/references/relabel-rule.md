# Relabel Rule

A provenance entry's labels follow its `extraction_method`, never the reverse. compile.md §4 and validate.md §7 load this file as `{relabelRuleData}` and apply the rule to each `provenance.entries[<i>].*` violation `skf-render-metadata-stats.py` reports, and validate.md §7a takes a node kind from its second part; the one-line Relabel Rule section of `extraction-patterns.md` points any other reader here.

1. **Labels.** Set the entry's `confidence`, `signature_source` and `ast_node_type` to the violation's `expected` value, and where `expected` is `non-null`, record the node kind part 2 gives. Leave a known `extraction_method` as it is. When the violation is on `extraction_method` itself (unknown or missing), set it to the method of the tool that produced the entry, `ast-grep` or `source-read` (so `direct-read` becomes `source-read`), and relabel what the next check reports. When the run cannot tell which tool produced the entry, set `source-read`: T1 needs evidence that an ast-grep rule matched.
2. **Node kind.** Take the `kind` that the recipe this run's extraction record names for the export (`ast_recipe`) declares in `{extractionPatternsData}` (the ast-grep Patterns table in `extraction-patterns-by-hand.md`, beside it, gives the kind of a `find_code` pattern). When the record names no recipe, or for an entry this run did not extract (one carried over from an earlier map), look the kind up at the entry's `source_file` and `source_line` (the values below are the entry's): from `{project-root}`, run

   ```bash
   uv run {verifyProvenanceCompletenessHelper} kind-at --source-root "{source_root}" --file "{source_file}" --line {source_line} --name "{export_name}" --recipes "{extractionPatternsData}"
   ```

   and record the `kind` it prints when `status` is `found`. On any other status (`ambiguous`, `no-match`, `incomplete` or a `skipped-` one), an exit 2, no resolved verifier or no local source tree, never invent a kind: leave that finding in place and list it as a WARN with the reason.
