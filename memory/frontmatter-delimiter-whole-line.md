---
created: "2026-04-09 01:19"
session: "59c7313e-e858-4b50-adc3-7e7cd9e3d750"
source: claude-mem
source_table: observations
source_ids: [4944, 4949, 5055]
---

# Frontmatter closing delimiter must match a whole line

`parse_frontmatter` in `src/shared/scripts/skf-validate-frontmatter.py` and `validate_frontmatter` in `src/shared/scripts/skf-validate-output.py` originally located the closing `---` with a bare substring search (`content.split("---", 2)` / `content.index("---", 3)`), which cut the YAML block off mid-value whenever a field contained `---` (e.g. `description: A---great library`) and produced false frontmatter findings. Both were rewritten to accept `---` only when `line.rstrip("\r") == "---"` on its own line, guarded by `test_frontmatter_with_dashes_in_value` in `test/test-skf-validate-output.py`. `validate_body_structure` in `skf-validate-output.py` still extracts the body with `content.split("---", 2)[-1]`, so the hazard is not fully gone. Any new script under `src/shared/scripts/` that reads SKILL.md or step-file frontmatter must use the line-aware form (see `skf-shard-body.py` or `skf-rewrite-skill-name.py` for the pattern), never a substring split.
