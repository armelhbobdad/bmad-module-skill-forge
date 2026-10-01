---
nextStepFile: 'generate-snippet.md'
---

<!-- Config: communicate in {communication_language}. Render the package status in {document_output_language}. -->

# Step 2: Package

## STEP GOAL:

To report each skill's package status from the export-gate verdict step 1 §2 retained, without checking the package again.

## Rules

- Read the verdict, never re-derive a check it covers, and never modify the package
- Auto-proceed when complete
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), report one row per skill, each from its own verdict. See step 1 §1c.

## MANDATORY SEQUENCE

### 1. Read the Verdict

Use the export-gate JSON step 1 §2 retained for `{resolved_skill_package}`. Only when it is not in context, run `python3 {validateOutputHelper} {resolved_skill_package} --export-gate` again: the same package gives the same verdict. Step 1 §2 halts on `NOT_READY`, so `export_status` is `READY` or `WARNINGS` here.

### 2. Report Package Status

"**Package checked.**

**Status:** {export_status}
**references/:** {the count of `.md` files under `{resolved_skill_package}/references/`, or none}

{If export_status is WARNINGS:}
**Warnings** (none of them stops the export):
- {the `field` of each `validation.metadata.recommended_missing` entry, each path in `validation.crossref_7b.orphans`, and the message of each low issue in `validation.metadata.issues`, such as an empty `exports` array or a forge tier in an older stack's `confidence_tier`}"

### 3. Proceed to Snippet Generation

Display: "**Proceeding to snippet generation...**"

Auto-proceed (no user choices): load, read entirely, and execute `{nextStepFile}`.
