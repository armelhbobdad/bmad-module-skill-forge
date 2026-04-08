# Tier Calculation Rules

## Tool Detection Commands

| Tool | Verification Command | What Confirms Availability |
|------|---------------------|---------------------------|
| ast-grep | `ast-grep --version` | Returns version string without error |
| gh | `gh --version` | Returns version string without error |
| qmd | `qmd status` | Returns status indicating initialized and operational |
| ccc | Step A: `ccc --help` Step B: `ccc doctor` | Step A: exits 0 (binary exists). Step B: daemon running, version string, model check OK |

**Important:** Use verification commands, not existence checks (`which`, `command -v`). A tool must be functional, not just present on PATH. For daemon-based tools (ccc), verify both binary existence and daemon health.

## Tier Calculation

| Priority | Tier | Required Tools | Rule |
|----------|------|---------------|------|
| 1 (highest) | Deep | ast-grep + gh + qmd | All three core tools available and functional |
| 2 | Forge+ | ast-grep + ccc | ast-grep AND ccc available, regardless of gh/qmd |
| 3 | Forge | ast-grep | ast-grep available, without ccc/gh/qmd |
| 4 (default) | Quick | None | Default when no tools are available |

**Evaluation order:** Check Deep first, then Forge+, then Forge. The first match wins. This ensures Deep always takes priority when all tools are present.

**Override:** If `tier_override` is set in preferences.yaml, use that value instead of calculated tier.

**Edge cases:**
- gh available but no ast-grep → Quick (gh alone doesn't unlock Forge)
- ast-grep + gh but no qmd → Forge (qmd required for Deep)
- ast-grep + qmd but no gh → Forge (gh required for Deep)
- ccc available but no ast-grep → Quick (ccc alone doesn't unlock Forge+)
- ast-grep + ccc + gh but no qmd → Forge+ (qmd required for Deep)
- ast-grep + gh + qmd + ccc → Deep (Deep subsumes Forge+; ccc enhances transparently)

## Tier Capability Descriptions

Use these for positive-framing in the report step. Describe what the tier GIVES, never what it lacks.

### Quick Tier
"Quick tier active. You have fast, template-driven skill generation with package-name resolution. Perfect for getting started quickly."

### Forge Tier
"Forge tier active. You have AST-backed structural code analysis with line-level citations, plus template-driven generation. Every skill instruction traces to verified source code."

### Forge+ Tier
"Forge+ tier active. Semantic-guided precision compilation — cocoindex-code maps the codebase semantically before AST extraction runs. Every skill begins with a ranked discovery pass that surfaces the most relevant source regions, then AST-backed verification gives each export its line-level citation."

### Deep Tier
"Deep tier active. Full capability unlocked — AST-backed code analysis, GitHub repository exploration, and QMD knowledge search with cross-repository synthesis. Maximum provenance and intelligence."

## Re-run Tier Change Messages

### Upgrade
"Tier upgraded from {previous} to {current}. {newly available tool(s)} now detected — expanded capabilities unlocked."

### Downgrade
"Tier changed from {previous} to {current}. {tool} no longer detected. Run the tool's installation to restore capabilities."

### Same
"Tier unchanged: {current}. All previously detected tools confirmed."
