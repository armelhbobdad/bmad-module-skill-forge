---
created: "2026-04-20 13:00"
session: "50b1b301-89a9-4565-b236-0e55e4e001b5"
source: claude-mem
source_table: observations
source_ids: [6369, 6370, 6371, 6387]
---

# Ruleset PUT 422 on do_not_enforce_on_create and integration_id

Editing main's `Default` ruleset (id 13855503) is `gh api --method PUT repos/armelhbobdad/bmad-module-skill-forge/rulesets/13855503 --input <json>` — PATCH answers 404 and PUT replaces the ruleset wholesale, which docs/\_internal/RELEASING.md §Branch Protection records. What it does not record: the first PUT that added the `required_status_checks` rule failed with HTTP 422 `data matches no possible input` on `/rules/4`, and only succeeded after dropping `do_not_enforce_on_create` from that rule's `parameters` and `integration_id: null` from every `required_status_checks[]` entry, leaving bare `{"context": "<check>"}` entries plus `strict_required_status_checks_policy`. The API adds `do_not_enforce_on_create: false` back on read (still present in a GET of the ruleset on 2026-09-21), so a baseline captured with RELEASING.md's `jq '{name, target, enforcement, conditions, rules, bypass_actors}'` snippet carries that key straight into the next PUT. If a baseline replay 422s, strip `do_not_enforce_on_create` (and any `integration_id`) from the required_status_checks rule before retrying.
