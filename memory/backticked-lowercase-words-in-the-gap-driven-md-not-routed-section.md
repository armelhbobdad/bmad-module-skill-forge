---
created: "2026-11-07 12:13"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Backticked lowercase words in the gap-driven.md Not routed section

`test_gap_routing_keys_on_the_ledger_category` in `test/test-skf-update-source-tree-prose.py` collects every backticked token matching `([a-z][a-z0-9-]*)` between `**Not routed:**` and `**Translation rules` in `src/skf-update-skill/references/gap-driven.md`. It asserts that set plus the routing table equals `CATEGORIES` in `src/skf-test-skill/scripts/gap-ledger.py`, so any backticked lowercase word in that section, such as `default`, fails the test as an unknown category even when it is only prose. On 2026-11-07 the #911 alias reason hit this on its first run and was reworded to "the alias does not rename a default export", with no backticks. The reason text must also match `NOT_ROUTED_REASONS` in `src/shared/scripts/skf-parse-gaps.py` word for word (`test_the_not_routed_list_gives_the_helpers_reasons`), so reword both together. Names with an underscore or brackets, such as `export_name`, `source_line` or `exports[]`, do not match the pattern and are safe there.
