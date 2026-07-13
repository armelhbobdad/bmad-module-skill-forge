# Tier Report Copy

The user-facing report strings the Step 4 report (`report.md`) consumes. Tool-detection probes and tier-calculation rules are owned by `skf-detect-tools.py` (see `references/detect-and-tier.md` §2) — this file holds only display copy, never detection or tier logic.

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
