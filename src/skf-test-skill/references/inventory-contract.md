# Documented Inventory Contract

The JSON coverage-check.md §1's reader writes to `{run_dir}/inventory-response.txt`: every export the skill documents, in this shape.

```json
{
  "exports": [
    {"name": "functionName", "kind": "function", "params": "...", "return_type": "...", "description": "..."},
    {"name": "ClassName", "kind": "class", "methods": ["..."], "properties": ["..."], "description": "..."},
    {"name": "TypeName", "kind": "type", "fields": ["..."], "description": "..."},
    {"name": "useHook", "kind": "hook", "usage_signature": "...", "description": "...", "signature_form": "partial"},
    {"name": "ComponentName", "kind": "constant", "usage_signature": "<ComponentName prop={value} />", "description": "..."},
    {"name": "Card", "kind": "function", "params": "{ title }", "description": "..."},
    {"name": "Card", "kind": "function", "params": "{ title: string; footer?: ReactNode }", "description": "..."}
  ],
  "references": ["references/api-reference.md"],
  "cross_check_mismatches": [
    {"export": "functionName", "skill_md_line": 42, "reference_file": "references/api-reference.md", "reference_line": 18, "issue": "SKILL.md shows (date: Date) => string, references/api-reference.md (date: Date, format?: string) => string"},
    {"export": "runTasks", "other_file": "references/api-reference.md", "other_line": 40, "reference_file": "references/pipelines.md", "reference_line": 12, "issue": "references/api-reference.md shows (tasks: Task[], data: unknown) => void, references/pipelines.md (tasks: Task[]) => void"}
  ]
}
```

The contract `validate-inventory.py` checks (coverage-check.md §1a): each `kind` is one of `function`, `class`, `type`, `constant`, `hook`, `interface`, `method`, `struct`, `enum`, `trait`, `macro` or `adapter`; every entry carries the `description` the skill gives it (an empty string when it gives none); a function or method carries `params` (`""` or `[]` when it takes none) and `return_type` as the skill documents them, and leaves a key out when the skill documents nothing for it. A `method`'s `name` is the bare method name and its `owner` the class or namespace it is called on (`agents` for `cognee.agents.get`; the class for one reached through a property, `client.messages`); `owner` is not validated. Each `methods` item starts with the method's name, optionally after `async` (`async next_uuid(dep=None)`). A `const` holding a component (a `forwardRef`, `memo` or other wrapper call, or an alias like `const Tabs = TabsPrimitive.Root`) is a `constant` with the declaration or usage form the skill writes as `usage_signature`; a data constant carries no `usage_signature`, `params` or `return_type`. A name documented in several places is listed once per place, each entry with that place's form (`Card` above), and keeps one `kind` in every place. An entry whose signature the skill labels partial (simplified, key parameters, a `...` standing in for omitted members, not rest or variadic syntax; a label in a table's column header, such as `Props (simplified)`, labels each of its rows) carries `signature_form: "partial"`, any other `"full"` or no key: copy the label, never judge the form.

A `cross_check_mismatches` entry gives its `export`, `reference_file`, `reference_line` and an `issue` that names each form by its file's path, and the pair's other side: the SKILL.md body's line as `skill_md_line`, or, for two references, the one that sorts first in codepoint order, by path and then line, as `other_file` and `other_line`, with the one that sorts last as `reference_file` and `reference_line`. Each file is its path in the package, such as `references/api-reference.md`.
