---
type: static-reference
---

# provenance-map.json Schema

Canonical schema templates for the workspace `provenance-map.json` artifact written in step 7 §7. Two variants exist — choose by the run's resolved mode:

- **code-mode** — when the workflow analyzed a real codebase with manifest files and AST-extracted exports
- **compose-mode** — when the workflow synthesized a stack from pre-generated constituent skills + an architecture document

Both variants share the top-level `provenance_version`, `skill_name`, `skill_type`, `generated_at`, `entries[]`, and `integrations[]` shape. They differ in source-anchor fields (`source_repo` / `source_commit` / `source_ref`), in `entries[].extraction_method` values, in `integrations[].detection_method` values, and in compose-mode's additional `constituents[]` array which enables drift detection via metadata-hash comparison.

> **Note:** A per-export entry has the fields the templates below give, with `source_library` naming its library and no `ast_node_type`: the stack methods `ast_bridge` and `source_reading` pair with no node kind.

## Code-mode variant

Used when the workflow ran in code-mode against an actual codebase. `source_repo` and `source_commit` capture the upstream anchor(s); `entries[].extraction_method` names the tool that read the export (`ast_bridge` or `source_reading`): step 4 §1 gives the labels each method pairs with, and §3a checks them with `skf-render-metadata-stats.py`. `entries[].source_file` is relative to `{scan_root}`, the project root (`project_root` from step 1), and `source_line` is the line that defines the export. `integrations[].detection_method` is `"co-import grep"` because integration pairs are confirmed by co-import file evidence.

```json
{
  "provenance_version": "2.0",
  "skill_name": "{project_name}-stack",
  "skill_type": "stack",
  "source_repo": ["{repo_url_1}", "{repo_url_2}"],
  "source_commit": {"{repo_1}": "{hash_1}", "{repo_2}": "{hash_2}"},
  "generated_at": "{ISO-8601}",
  "entries": [
    {
      "export_name": "{name}",
      "export_type": "{type}",
      "source_library": "{library-name}",
      "params": [],
      "return_type": "{type}",
      "source_file": "{file}",
      "source_line": 0,
      "confidence": "T1|T1-low",
      "extraction_method": "ast_bridge|source_reading",
      "signature_source": "T1|T1-low"
    }
  ],
  "integrations": [
    {
      "libraries": ["{libA}", "{libB}"],
      "pattern_type": "{type}",
      "detection_method": "co-import grep",
      "co_import_files": [{"file": "{path}", "line": 0}],
      "confidence": "T1|T1-low"
    }
  ]
}
```

## Compose-mode variant

Used when the workflow ran in compose-mode against pre-generated constituent skills. Source-anchor fields (`source_repo`, `source_commit`, `source_ref`) are `null` because there is no codebase to anchor against: provenance traces back to the constituent skills instead, captured in the `constituents[]` array. Each entry's `extraction_method` is `"compose-from-skill"`; integrations have `detection_method` of `"architecture_co_mention"` (named in the architecture doc), `"constituent_documented_contract"` (a cross-library contract documented in a constituent skill's integration docs but not co-mentioned in the architecture document, e.g. a grep-verified upstream seam cited from a source skill), or `"inferred_from_shared_domain"` (synthesized inference from shared language/domain, no cited contract). `detection_method` records *how* an edge was discovered; it is orthogonal to `confidence`, which is inherited from the constituent skills per the Confidence Tier Inheritance rule in `{composeModeRulesPath}` (the integration tier is the weaker of the pair, never forced to a fixed band by detection method).

```json
{
  "provenance_version": "2.0",
  "skill_name": "{project_name}-stack",
  "skill_type": "stack",
  "source_repo": null,
  "source_commit": null,
  "source_ref": null,
  "generated_at": "{ISO-8601}",
  "entries": [
    {
      "export_name": "{literal identifier}",
      "export_type": "{type}",
      "source_library": "{library-name}",
      "params": [],
      "return_type": "{type}",
      "source_file": "{from constituent skill}",
      "source_line": 0,
      "confidence": "T1|T1-low|T2|T3",
      "extraction_method": "compose-from-skill",
      "signature_source": "T1|T1-low|T2|T3"
    }
  ],
  "integrations": [
    {
      "libraries": ["{libA}", "{libB}"],
      "pattern_type": "{type}",
      "detection_method": "architecture_co_mention|constituent_documented_contract|inferred_from_shared_domain",
      "co_import_files": [],
      "confidence": "T1|T1-low|T2|T3"
    }
  ],
  "constituents": [
    {
      "skill_name": "{constituent-skill-name}",
      "skill_path": "skills/{skill-dir}/",
      "version": "{version from constituent metadata.json}",
      "composed_at": "{ISO-8601}",
      "metadata_hash": "sha256:{hash of constituent metadata.json}"
    }
  ]
}
```

**Use the `metadata_hash` value already stored in workflow state during step 2 (S13) — do NOT re-read and re-hash at step 7 time. The stored hash captures the state as it was at manifest-detection time, which is the correct provenance anchor.**
