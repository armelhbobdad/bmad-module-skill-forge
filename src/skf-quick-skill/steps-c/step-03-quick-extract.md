---
nextStepFile: './step-04-compile.md'
---

# Step 3: Quick Extract

## STEP GOAL:

To read the resolved GitHub repository source and extract the public API surface using surface-level source reading (no AST). Produces an extraction inventory of exports, descriptions, and manifest data for compilation.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a rapid skill compiler extracting public API surface
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Best-effort extraction — completeness is not required
- ✅ Surface-level reading only — no AST, no deep analysis

### Step-Specific Rules:

- 🎯 Focus only on reading source and extracting exports
- 🚫 FORBIDDEN to begin compilation or write output files
- 💬 Approach: Read key files, extract what's visible, move on
- 📋 No AST required — use grep/pattern-based extraction
- 📋 If no exports found, extract what's available from README

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Set state: extraction_inventory (exports list, description, manifest data)
- 📖 Web browsing required to read GitHub source files
- 🚫 Do not spend excessive time on extraction — best-effort

## CONTEXT BOUNDARIES:

- Previous steps provided: resolved_url, repo_name, language, scope_hint
- Web browsing available for reading GitHub source files
- Focus: extraction only, not compilation
- This is best-effort — incomplete extraction is acceptable

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

**Ref-aware source reading:** When `source_ref` is set from tag resolution (see step-01), append `?ref={source_ref}` to all GitHub API content and tree requests (e.g., `gh api repos/{owner}/{repo}/contents/{path}?ref={source_ref}`) to read from the tagged version. When using web browsing, use the tagged URL format (e.g., `github.com/{owner}/{repo}/blob/{source_ref}/{path}`). This ensures extraction reads from the same source version resolved during tag resolution.

### 1. Read README

Read `README.md` from the repository root via web browsing.

Extract:
- **Description:** What the package does (first paragraph or tagline)
- **Features:** Key features or capabilities listed
- **Usage patterns:** Code examples showing common usage
- **Installation:** Package manager install command (confirms package name)

If README is unavailable, note and continue.

### 2. Read Manifest File

Based on detected language, read the primary manifest file:

- **JavaScript/TypeScript:** `package.json` — extract name, version, description, main, exports, dependencies
- **Python:** `pyproject.toml` or `setup.py` — extract project name, version, description, dependencies
- **Rust:** `Cargo.toml` — extract package name, version, description, dependencies
- **Go:** `go.mod` — extract module path, require list

Extract:
- **Package metadata:** name, version, description
- **Entry points:** main, exports, module fields
- **Key dependencies:** direct dependencies list

### 3. Scan Top-Level Exports

Based on language and entry points from manifest, read the primary export files:

**JavaScript/TypeScript:**
- Read `index.js`, `index.ts`, `src/index.ts`, or `main` field from package.json
- Extract: `export` statements, `module.exports` assignments
- Pattern: lines matching `export (const|function|class|default|type|interface)`

**Python:**
- Read `__init__.py` or `src/{package}/__init__.py`
- Extract: `__all__` list, top-level function/class definitions
- Pattern: lines matching `def |class |__all__`

**Rust:**
- Read `src/lib.rs`
- Extract: `pub fn`, `pub struct`, `pub enum`, `pub trait` declarations
- Pattern: lines matching `pub (fn|struct|enum|trait|mod)`

**Go:**
- Read exported functions from top-level `.go` files
- Extract: capitalized function names (Go export convention)
- Pattern: lines matching `func [A-Z]`

**If scope_hint provided:** Focus reading on the specified directories instead of root.

### 4. Build Extraction Inventory

Assemble the extraction inventory from collected data:

```
extraction_inventory:
  description: {from README or manifest}
  package_name: {from manifest}
  version: {from manifest}
  language: {detected}
  exports: [{name, type, brief_description}]
  usage_patterns: [{pattern from README examples}]
  dependencies: [{key deps from manifest}]
  confidence: {high/medium/low based on data quality}
```

**If no exports found:**
- Set confidence to `low`
- Use README description and features as fallback content
- Note: "No exports detected — SKILL.md will be based on README content only"

### 5. Report Extraction Summary

"**Extraction complete:**

- **Package:** {package_name} v{version}
- **Language:** {language}
- **Exports found:** {count}
- **Confidence:** {confidence}
- **Source files read:** {count}

**Proceeding to compilation...**"

### 6. Auto-Proceed to Compilation

#### Menu Handling Logic:

- After extraction summary, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step — extraction results flow directly to compilation
- Proceed directly to next step after summary

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN extraction is complete and extraction_inventory is assembled (even if minimal/low-confidence) will you load and read fully `{nextStepFile}` to execute compilation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- README read and description extracted
- Manifest file read and metadata extracted
- Top-level exports scanned (best-effort)
- extraction_inventory assembled with available data
- Confidence level set appropriately
- Auto-proceeding to compilation

### ❌ SYSTEM FAILURE:

- Spending excessive time trying to achieve complete extraction
- Using AST tools (this is surface-level reading only)
- Beginning compilation or writing output files
- Halting on missing exports instead of using README fallback

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
