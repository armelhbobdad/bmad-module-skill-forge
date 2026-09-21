---
created: "2026-04-03 18:45"
session: "1515905c-e1d7-40f7-8c23-5f52e1cd284a"
source: claude-mem
source_table: both
source_ids: [4058, 4059, 4069, 4070]
---

# Missing forge-tier.yaml is a hard halt, never a Quick-tier fallback

Every skf-* workflow's step 1 HARD HALTs when `{sidecar_path}/forge-tier.yaml` is absent — e.g. `src/skf-analyze-source/references/init.md` §2 "**Cannot proceed.** forge-tier.yaml not found at `{sidecar_path}/forge-tier.yaml`. Please run the setup workflow first…", `src/skf-audit-skill/references/init.md` exit 3 `halt_reason: "forge-tier-missing"`, `src/skf-update-skill/references/init.md` "No forge-tier.yaml found. Run setup first". test-skill and brief-skill used to fall back silently to Quick tier; that produced plausible-looking skills compiled at the wrong tier, so they were changed to halt like the others (3fb7152, 2026-04-03) — keep the rule when adding a workflow: a missing sidecar is a setup error, not a degradation. The deliberate exceptions are explicit and loud: `--tier=<Quick|Forge|Forge+|Deep>` on test-skill bypasses the probe; brief-skill (`references/gather-intent.md`) falls back to Quick only when the file exists but fails to parse and says so; Ferris (`src/skf-forger/SKILL.md` On Activation) tolerates an absent file on a first run but halts when `{sidecar_path}` is still the literal placeholder string (a known installer issue with `prompt: false` config variables).
