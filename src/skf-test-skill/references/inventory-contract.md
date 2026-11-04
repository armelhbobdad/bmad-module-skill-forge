# Documented Inventory Contract

The JSON coverage-check.md §1's reader writes to `{run_dir}/inventory-response.txt`: every export the skill documents, in this shape.

```json
{
  "exports": [
    {"name": "functionName", "kind": "function", "params": "...", "return_type": "...", "description": "..."},
    {"name": "ClassName", "kind": "class", "methods": ["..."], "properties": ["..."], "description": "..."},
    {"name": "TypeName", "kind": "type", "fields": ["..."], "description": "..."},
    {"name": "useHook", "kind": "hook", "usage_signature": "...", "description": "...", "signature_form": "partial"}
  ],
  "references": ["references/api-reference.md"],
  "cross_check_mismatches": [
    {"export": "functionName", "skill_md_line": 42, "reference_file": "references/api-reference.md", "reference_line": 18, "issue": "SKILL.md shows (date: Date) => string, the reference (date: Date, format?: string) => string"}
  ]
}
```

The contract `validate-inventory.py` checks (coverage-check.md §1a): each `kind` is one of `function`, `class`, `type`, `constant`, `hook`, `interface`, `method`, `struct`, `enum`, `trait`, `macro` or `adapter`; every entry carries the `description` the skill gives it (an empty string when it gives none); a function or method carries `params` (`""` or `[]` when it takes none) and `return_type` as the skill documents them, and leaves a key out when the skill documents nothing for it. An entry whose signature the skill labels partial (simplified, key parameters, a `...` standing in for omitted members, not rest or variadic syntax; a label in a table's column header, such as `Props (simplified)`, labels each of its rows) carries `signature_form: "partial"`, any other `"full"` or no key: copy the label, never judge the form.
