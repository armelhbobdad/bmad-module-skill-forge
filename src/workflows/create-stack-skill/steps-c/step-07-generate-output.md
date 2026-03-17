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

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Create Output Directories

Create the directory structure:

```
{skills_output_folder}/{project_name}-stack/
├── references/
│   └── integrations/
```

```
{forge_data_folder}/{project_name}-stack/
```

If directories already exist, proceed (overwrite previous output).

### 2. Write SKILL.md

Write `{skills_output_folder}/{project_name}-stack/SKILL.md` with the approved skill_content from step 06.

### 3. Write Per-Library Reference Files

For each confirmed library, write `{skills_output_folder}/{project_name}-stack/references/{library_name}.md`:

Load structure from `{stackSkillTemplate}` references section:
- Library name, version from manifest
- Import count and file count
- Key exports with signatures
- Usage patterns with file:line citations
- Confidence tier label

### 4. Write Integration Pair Reference Files

For each detected integration pair, write `{skills_output_folder}/{project_name}-stack/references/integrations/{libraryA}-{libraryB}.md`:

Load structure from `{stackSkillTemplate}` integrations section:
- Library pair and integration type
- Co-import file count
- Integration pattern description with file:line citations
- Usage convention
- Confidence tier label

**If no integrations detected:** Skip this section (no files to write).

### 5. Write context-snippet.md

Write `{skills_output_folder}/{project_name}-stack/context-snippet.md`:

Use ADR-L v2 format targeting ~50-80 tokens per library entry:
```
**{library}** ({import_count} imports): {top_3_exports}
  → integrates with: {comma-separated integration partners}
```

### 6. Write metadata.json

Write `{skills_output_folder}/{project_name}-stack/metadata.json`:

```json
{
  "skill_type": "stack",
  "name": "{project_name}-stack",
  "version": "{primary_library_version or 1.0.0}",
  "generation_date": "{current_date}",
  "confidence_tier": "{tier}",
  "library_count": N,
  "integration_count": N,
  "libraries": ["lib1", "lib2"],
  "integration_pairs": [["lib1", "lib2"]],
  "confidence_distribution": {"T1": N, "T1-low": N, "T2": N}
}
```

### 7. Write Forge Data Artifacts

Write workspace artifacts to `{forge_data_folder}/{project_name}-stack/`:

**provenance-map.json:**
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

**evidence-report.md:**
- Extraction summary per library
- Integration detection results per pair
- Warnings and failures encountered
- Confidence tier distribution

### 8. Display Write Summary

"**Output files written.**

**Deliverables** ({skills_output_folder}/{project_name}-stack/):
- ✓ SKILL.md ({line_count} lines)
- ✓ context-snippet.md ({token_estimate} tokens)
- ✓ metadata.json
- ✓ references/ — {lib_count} library files
- ✓ references/integrations/ — {pair_count} integration files

**Workspace** ({forge_data_folder}/{project_name}-stack/):
- ✓ provenance-map.json
- ✓ evidence-report.md

**Total files written:** {total_count}

**Proceeding to validation...**"

### 9. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All deliverable files written to skills_output_folder
- All workspace artifacts written to forge_data_folder
- Directory structure created correctly
- Each file matches its template structure
- Write summary displayed with accurate counts

### ❌ SYSTEM FAILURE:

- Any file write failure not caught (hard halt required)
- Modifying approved skill_content during writing
- Missing files from the expected output set
- Wrong directory paths for output

**Master Rule:** Write everything, modify nothing. Hard halt on any write failure.
