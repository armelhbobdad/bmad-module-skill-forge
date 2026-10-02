# Stack metadata.json Contract

The `metadata.json` every stack package carries, which step 7 §6 writes. This file is fixed: `stack_skill_template_path` overrides only the SKILL.md, context-snippet, catalog and reference-file structures of `assets/stack-skill-template.md`, never this contract. `generated_by`, `tool_versions.skf`, and `skill_type` with `forge_tier` or `confidence_tier` are the markers SKF's ownership check reads, so a stack written without them would be refused as not SKF output by every later run.

## metadata.json Structure

```json
{
  "skill_type": "stack",
  "name": "{stack_name}",
  "version": "1.0.0",
  "generation_date": "{ISO-8601}",
  "forge_tier": "{Quick|Forge|Forge+|Deep}",
  "confidence_tier": "{T1|T1-low|T2|T3}",
  "spec_version": "1.3",
  "source_authority": "{official|community|internal}",
  "generated_by": "create-stack-skill",
  "exports": [],
  "library_count": 0,
  "integration_count": 0,
  "libraries": ["lib1", "lib2"],
  "integration_pairs": [["lib1", "lib2"]],
  "language": "{primary language or list of languages from constituent skills}",
  "ast_node_count": "{number-or-omitted-if-no-ast}",
  "confidence_distribution": {
    "t1": 0,
    "t1_low": 0,
    "t2": 0,
    "t3": 0
  },
  "tool_versions": {
    "ast_grep": "{version-or-null}",
    "qmd": "{version-or-null}",
    "skf": "{skf_version}"
  },
  "stats": {
    "exports_documented": 0,
    "exports_public_api": 0,
    "exports_internal": 0,
    "exports_total": 0,
    "public_api_coverage": 0.0,
    "total_coverage": 0.0,
    "scripts_count": 0,
    "assets_count": 0
  },
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```

Step 7 §6 writes `library_count`, `integration_count`, `libraries`, `integration_pairs`, `confidence_distribution`, `confidence_tier` and `source_authority` verbatim from `skf-render-stack-metadata.py`. `confidence_distribution` counts libraries, each by its `per_library_extractions[].confidence`; the evidence report bins the provenance entries.
