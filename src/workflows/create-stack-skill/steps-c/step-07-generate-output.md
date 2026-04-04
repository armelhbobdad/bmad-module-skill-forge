---
name: 'step-07-generate-output'
description: 'Write all output files — SKILL.md, references, metadata, context-snippet, and forge-data'

nextStepFile: './step-08-validate.md'
stackSkillTemplate: '../data/stack-skill-template.md'
---

# Step 7: Generate Output Files

## STEP GOAL:

Write all deliverable and workspace artifact files to their target directories.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill packager operating in Ferris Architect mode
- ✅ Precise file writing — every file matches its template structure
- ✅ Hard halt on any write failure — partial output is worse than no output

### Step-Specific Rules:

- 🎯 Write ALL output files in correct directory structure
- 🚫 FORBIDDEN to modify compiled content — step 06 produced the approved version
- 💬 Report each file written with path and size
- 🎯 Create directory structure before writing files

## EXECUTION PROTOCOLS:

- 🎯 Create output directories, write all files
- 💾 Store written_files list as workflow state
- 📖 Auto-proceed to validation after all files written
- 🚫 HARD HALT on any individual file write failure

## CONTEXT BOUNDARIES:

- From step 06: skill_content (approved compiled SKILL.md)
- From step 04: per_library_extractions[] for reference files
- From step 05: integration_graph for integration pair references
- From step 01: forge_tier, project info for metadata
- This step produces: written_files[] (all output artifacts)
- Path resolution: See `knowledge/version-paths.md` for canonical path templates. Stack skills use `{project_name}-stack` as the skill name

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
  "libraries": {
    "lib_name": {
      "manifest_source": "package.json",
      "extraction_method": "ast_bridge|source_reading|qmd_bridge",
      "confidence": "T1|T1-low|T2",
      "files_analyzed": N,
      "exports_found": N
    }
  },
  "integrations": {
    "libA+libB": {
      "detection_method": "co-import grep",
      "co_import_files": N,
      "type": "pattern_type"
    }
  }
}
```

**In compose-mode:**
```json
{
  "libraries": {
    "lib_name": {
      "source_skill_path": "skills/{skill_dir}/",
      "compose_source": "architecture_co_mention|inferred_from_shared_domain",
      "confidence": "T1|T1-low|T2",
      "source_skill_tier": "{original skill confidence tier}",
      "exports_found": N
    }
  },
  "integrations": {
    "libA+libB": {
      "detection_method": "architecture_co_mention|inferred_from_shared_domain",
      "type": "pattern_type"
    }
  }
}
```

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All deliverable files written to {skill_package}
- All workspace artifacts written to {forge_version}
- Directory structure created correctly with version nesting
- Active symlink created at {skill_group}/active -> {version}
- Each file matches its template structure
- Write summary displayed with accurate counts

### ❌ SYSTEM FAILURE:

- Any file write failure not caught (hard halt required)
- Modifying approved skill_content during writing
- Missing files from the expected output set
- Wrong directory paths for output

**Master Rule:** Write everything, modify nothing. Hard halt on any write failure.
