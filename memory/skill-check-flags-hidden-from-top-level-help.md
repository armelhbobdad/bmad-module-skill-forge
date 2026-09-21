---
created: "2026-05-19 19:27"
session: "5c98ccfa-dfd4-42f4-86d4-3e24b29517af"
source: claude-mem
source_table: observations
source_ids: [10253, 10254, 10260, 10302]
---

# skill-check subcommand flags hidden from top-level --help

`npx skill-check --help` lists only subcommands; `--no-security-scan` and `--skip-security` appear only in `npx skill-check check --help`. The flag probe in `src/skf-create-skill/references/validate.md` §2 (`npx skill-check check --help 2>/dev/null | grep -- --no-security-scan`) once targeted the top-level help, so it never matched, set `{skill_check_flag_fallback} = true` and every create-skill run silently degraded to §3 manual-only validation with the evidence-report line `skill_check_flag_probe: neither --no-security-scan nor --skip-security supported by installed skill-check; validation performed manually`. Commit fc4fbfc8 fixed the probe but the file does not say why it names the `check` subcommand. Any new probe for a skill-check option (update-skill, create-stack, test-skill hardcode `--no-security-scan` today) must grep the subcommand's help, never the top-level one.
