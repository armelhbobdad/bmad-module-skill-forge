---
nextStepFile: './step-08-validate.md'
stackSkillTemplate: 'assets/stack-skill-template.md'
---

# Step 7: Generate Output Files

## STEP GOAL:

Write all deliverable and workspace artifact files to their target directories.

## Rules

- Write all output files in correct directory structure — do not modify compiled content from Step 06
- Create directory structure before writing files
- Report each file written with path and size

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Create Output Directories

Resolve `{version}` from the primary library version or default to `1.0.0`. Create the directory structure:

```
{skill_group}                          # {skills_output_folder}/{project_name}-stack/
{skill_package}                        # {skills_output_folder}/{project_name}-stack/{version}/{project_name}-stack/
├── references/
│   └── integrations/
```

```
{forge_version}                        # {forge_data_folder}/{project_name}-stack/{version}/
```

Where the skill name is `{project_name}-stack` and `{version}` is the semver version (with build metadata stripped per `knowledge/version-paths.md`).

If directories already exist, proceed (overwrite previous output).

### 2. Write SKILL.md

Write `{skill_package}/SKILL.md` with the approved skill_content from step 06.

### 3. Write Per-Library Reference Files

For each confirmed library, write `{skill_package}/references/{library_name}.md`:

Load structure from `{stackSkillTemplate}` references section:
- Library name, version from manifest (**in compose-mode**: version from source skill `metadata.json`)
- Import count and file count (**in compose-mode**: export count from source skill metadata)
- Key exports with signatures
- Usage patterns with file:line citations (**in compose-mode**: usage patterns from source skill SKILL.md)
- Confidence tier label

### 4. Write Integration Pair Reference Files

For each detected integration pair, write `{skill_package}/references/integrations/{libraryA}-{libraryB}.md`:

Load structure from `{stackSkillTemplate}` integrations section:
- Library pair and integration type
- Co-import file count
- Integration pattern description with file:line citations
- Usage convention
- Confidence tier label

**If no integrations detected:** Skip this section (no files to write).

### 5. Write context-snippet.md

Write `{skill_package}/context-snippet.md`:

Use the Vercel-aligned indexed format targeting ~80-120 tokens:
```
[{project_name}-stack v{version — in code-mode: primary_library_version or 1.0.0; in compose-mode: highest version across constituent skill metadata.json files, or 1.0.0 if none}]|root: skills/{project_name}-stack/
|IMPORTANT: {project_name}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {1-2 most critical integration pitfalls}
```

### 6. Write metadata.json

Write `{skill_package}/metadata.json`:

Populate all fields from the metadata.json schema defined in `{stackSkillTemplate}`:

```json
{
  "skill_type": "stack",
  "name": "{project_name}-stack",
  "version": "{primary_library_version or 1.0.0}",
  "generation_date": "{current_date}",
  "confidence_tier": "{tier}",
  "spec_version": "1.3",
  "source_authority": "{official|community|internal — use the lowest authority among constituent skills}",
  "generated_by": "create-stack-skill",
  "exports": [],
  "library_count": N,
  "integration_count": N,
  "libraries": ["lib1", "lib2"],
  "integration_pairs": [["lib1", "lib2"]],
  "language": "{primary language or list of languages from constituent skills}",
  "ast_node_count": "{number or omit if no AST extraction performed}",
  "confidence_distribution": {"t1": N, "t1_low": N, "t2": N, "t3": N},
  "tool_versions": {
    "ast_grep": "{version or null}",
    "qmd": "{version or null}",
    "skf": "{skf_version}"
  },
  "stats": {
    "exports_documented": N,
    "exports_public_api": N,
    "exports_internal": N,
    "exports_total": N,
    "public_api_coverage": 0.0,
    "total_coverage": 0.0,
    "scripts_count": N,
    "assets_count": N
  },
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```

### 7. Write Forge Data Artifacts

Write workspace artifacts to `{forge_version}`:

**provenance-map.json:**

**In code-mode:**
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
      "confidence": "T1|T1-low|T2",
      "extraction_method": "ast_bridge|source_reading|qmd_bridge",
      "signature_source": "T1|T2|T3"
    }
  ],
  "integrations": [
    {
      "libraries": ["{libA}", "{libB}"],
      "pattern_type": "{type}",
      "detection_method": "co-import grep",
      "co_import_files": [{"file": "{path}", "line": 0}],
      "confidence": "T1|T2"
    }
  ]
}
```

**In compose-mode:**
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
      "export_name": "{name}",
      "export_type": "{type}",
      "source_library": "{library-name}",
      "params": [],
      "return_type": "{type}",
      "source_file": "{from constituent skill}",
      "source_line": 0,
      "confidence": "T1|T1-low|T2",
      "extraction_method": "compose-from-skill",
      "signature_source": "T1|T2|T3"
    }
  ],
  "integrations": [
    {
      "libraries": ["{libA}", "{libB}"],
      "pattern_type": "{type}",
      "detection_method": "architecture_co_mention|inferred_from_shared_domain",
      "co_import_files": [],
      "confidence": "T2|T3"
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

> **Note:** Per-export entries use the same schema as single skills (see `skill-sections.md`), with `source_library` identifying the originating library. In compose-mode, `constituents[]` enables audit to detect constituent drift via metadata hash comparison.

**evidence-report.md:**
- Extraction summary per library
- Integration detection results per pair
- Warnings and failures encountered
- Confidence tier distribution

### 8. Create Active Symlink

Create or update the `active` symlink at `{skill_group}/active` pointing to `{version}`:

```
{skill_group}/active -> {version}
```

If the symlink already exists, remove it first and recreate. This ensures `{skill_group}/active/{project_name}-stack/` resolves to the just-written skill package.

### 9. Display Write Summary

"**Output files written.**

**Deliverables** ({skill_package}):
- SKILL.md ({line_count} lines)
- context-snippet.md ({token_estimate} tokens)
- metadata.json
- references/ -- {lib_count} library files
- references/integrations/ -- {pair_count} integration files

**Workspace** ({forge_version}):
- provenance-map.json
- evidence-report.md

**Symlink:** {skill_group}/active -> {version}

**Total files written:** {total_count}

**Proceeding to validation...**"

### 10. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

