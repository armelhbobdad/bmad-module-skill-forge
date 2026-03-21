---
name: 'step-03-generate-snippet'
description: 'Generate context-snippet.md in Vercel-aligned indexed format'

nextStepFile: './step-04-update-context.md'
snippetFormatData: '../data/snippet-format.md'
---

# Step 3: Generate Snippet

## STEP GOAL:

To generate or update context-snippet.md for the skill in the Vercel-aligned indexed format, targeting ~80-120 tokens per skill with T1-now content only.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a delivery and packaging specialist in Ferris Delivery mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Compress precisely — every token in a snippet must earn its place

### Step-Specific Rules:

- 🎯 Focus only on generating the context-snippet.md content
- 🚫 FORBIDDEN to include T2 annotations or temporal context — T1-now only
- 💬 This is a deterministic generation step — auto-proceed when complete
- 📋 If `passive_context: false` was detected in step-01, SKIP this step entirely and auto-proceed to step-04

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Write context-snippet.md to skill directory (or hold in context if dry-run)
- 📖 Load {snippetFormatData} for format template
- 🚫 Strict adherence to Vercel-aligned format — no deviations

## CONTEXT BOUNDARIES:

- Available: Skill metadata (name, exports, skill_type, components, integrations) from step-01
- Focus: Snippet generation in exact Vercel-aligned format
- Limits: T1-now content only, ~80-120 tokens target
- Dependencies: Step-01 metadata, step-02 package validation

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step-01:**

"**Passive context disabled in preferences.yaml. Skipping snippet generation.**"

Auto-proceed immediately to {nextStepFile}.

**If `passive_context: true` (default):** Continue to step 2.

### 2. Load Snippet Format

Load {snippetFormatData} and read the format template for the skill type.

### 3. Generate Snippet Content

**For single skills (`skill_type: "single"`):**

1. Read metadata.json for `version`, `exports` array
2. Select top exports (up to 10 for Deep tier, 5 otherwise). Append `()` to function names.
3. Read SKILL.md to extract: heading slugs for `#quick-start` and `#key-types`, inline summary of key types (~10 words)
4. **Anchor verification (split-body awareness):** For each section anchor (`#quick-start`, `#key-types`), verify the heading exists in SKILL.md. If a `references/` directory exists and `## Full` headings in SKILL.md are absent or stubs (indicating split-body, not a stack skill's structural references), rewrite the anchor to point to the reference file path (e.g., `references/{file}.md#key-types`). If the heading cannot be resolved in either location, omit that anchor line from the snippet.
5. Derive gotchas from: T2-future annotations in evidence report (breaking changes), async requirements, version-specific behavior. If no gotchas, omit the gotchas line.

Generate:
```
[{skill-name} v{version}]|root: skills/{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {export-1}(), {export-2}(), {export-3}, {export-4}(), {export-5}
|key-types:{SKILL.md#key-types} — {inline summary ~10 words}
|gotchas: {pitfall-1}, {pitfall-2}
```

**If fewer exports than limit:** List all available.
**If no exports:** Omit the api line.
**If no gotchas derivable:** Omit the gotchas line.

**For stack skills (`skill_type: "stack"`):**

Generate:
```
[{project}-stack v{version}]|root: skills/{project}-stack/
|IMPORTANT: {project}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {pitfall-1}, {pitfall-2}
```

### 4. Verify Token Count

Estimate token count of generated snippet (approximate: words * 1.3).

- Target: ~80-120 tokens per skill
- Warning threshold: >150 tokens
- If exceeding warning threshold, trim description, exports list, or refs to fit

### 5. Write or Preview Snippet

**If dry-run mode:**

"**[DRY RUN] context-snippet.md would be written to:**
`{skills_output_folder}/{skill-name}/context-snippet.md`

**Content:**
```
{generated snippet content}
```

**Estimated tokens:** {count}"

Hold content in context for step-04.

**If NOT dry-run:**

Write the generated content to `{skills_output_folder}/{skill-name}/context-snippet.md`.

"**context-snippet.md written.**
**Path:** `{skills_output_folder}/{skill-name}/context-snippet.md`
**Estimated tokens:** {count}"

### 6. Proceed to Context Update

Display: "**Proceeding to context update...**"

#### Menu Handling Logic:

- After snippet generation completes, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after generation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN snippet generation is complete (or skipped due to passive_context opt-out) will you load and read fully `{nextStepFile}` to execute context update.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Snippet format loaded from {snippetFormatData}
- Content generated matching exact Vercel-aligned format
- Section anchors verified against SKILL.md headings (split-body anchors rewritten or omitted)
- Token count estimated and within target
- File written (or previewed in dry-run)
- Passive context opt-out correctly handled (skip when disabled)
- Auto-proceed to step-04

### ❌ SYSTEM FAILURE:

- Deviating from Vercel-aligned indexed format
- Including T2 annotations or temporal context
- Not checking passive_context setting
- Not estimating token count
- Halting for user input (auto-proceed step)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
