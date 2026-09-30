# Tier Report Copy

The strings the step 4 FORGE STATUS banner shows. `render-report` (`skf-emit-result-envelope.py`) reads the first line under each `###` heading below, without its surrounding double quotes, so keep each string on one line. Tool-detection probes and tier-calculation rules are owned by `skf-detect-tools.py`; this file holds only display copy, never detection or tier logic.

## Tier Capability Descriptions

Describe what each tier gives, never what it lacks.

### Quick Tier
"Quick tier active. You have fast, template-driven skill generation with package-name resolution. Perfect for getting started quickly."

### Forge Tier
"Forge tier active. You have AST-backed structural code analysis with line-level citations, plus template-driven generation. Every skill instruction traces to verified source code."

### Forge+ Tier
"Forge+ tier active. Semantic-guided precision compilation: cocoindex-code maps the codebase semantically before AST extraction runs. Every skill begins with a ranked discovery pass that surfaces the most relevant source regions, then AST-backed verification gives each export its line-level citation."

### Deep Tier
"Deep tier active. Full capability unlocked: AST-backed code analysis, GitHub repository exploration, and QMD knowledge search with cross-repository synthesis. Maximum provenance and intelligence."

## Re-run Tier Change Messages

### Upgrade
"Tier upgraded from {previous} to {current}. {newly available tool(s)} now detected: expanded capabilities unlocked."

### Downgrade
"Tier changed from {previous} to {current}. {tool} no longer detected. Run the tool's installation to restore capabilities."

### Same
"Tier unchanged: {current}. All previously detected tools confirmed."
