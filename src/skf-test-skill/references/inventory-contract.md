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
    {"name": "Card", "kind": "function", "params": "{ title: string; footer?: ReactNode }", "description": "..."},
    {"name": "Note", "kind": "class", "params": "each with the base fields id, scope=Scope(); content, title=None", "description": "..."}
  ],
  "references": ["references/api-reference.md"],
  "cross_check_mismatches": [
    {"export": "functionName", "skill_md_line": 42, "reference_file": "references/api-reference.md", "reference_line": 18, "issue": "SKILL.md shows (date: Date) => string, references/api-reference.md (date: Date, format?: string) => string"},
    {"export": "runTasks", "other_file": "references/api-reference.md", "other_line": 40, "reference_file": "references/pipelines.md", "reference_line": 12, "issue": "references/api-reference.md shows (tasks: Task[], data: unknown) => void, references/pipelines.md (tasks: Task[]) => void"}
  ]
}
```

The contract `validate-inventory.py` checks (coverage-check.md §1a): each `kind` is one of `function`, `class`, `type`, `constant`, `hook`, `interface`, `method`, `struct`, `enum`, `trait`, `macro` or `adapter`; every entry carries the `description` the skill gives it (an empty string when it gives none); a function or method carries `params` (`""` or `[]` when it takes none) and `return_type` as the skill documents them, and leaves a key out when the skill documents nothing for it. A `method`'s `name` is the bare method name and its `owner` the class or object it is called on (`agents` for `cognee.agents.get`, where the skill documents `agents` as a class; the class for one reached through a property, `client.messages`); `owner` is not validated. A function the skill documents in a module is a `function` named bare, never a `method`, even when it is called through the module's name (`register_sql_connection` for `cognee.tools.register_sql_connection`, where the skill documents `tools` as a module). Each `methods` item starts with the method's name, optionally after `async` (`async next_uuid(dep=None)`). A `const` holding a component (a `forwardRef`, `memo` or other wrapper call, or an alias like `const Tabs = TabsPrimitive.Root`) is a `constant` with the declaration or usage form the skill writes as `usage_signature`; a data constant carries no `usage_signature`, `params` or `return_type`. A name documented in several places is listed once per place, each entry with that place's form (`Card` above), and keeps one `kind` in every place. Where the skill documents several names and states members they share once, in the same place (a table row, a paragraph) or over a table for all its rows (a sentence or caption just above it, or its column header), each name's entry carries that shared text in its `params` (in its `usage_signature`, for a usage form), never in a `methods` item, which still starts with the method's name: the shared text first, then `; `, then the name's own members as the skill writes them, without the name, never the name's own members alone (`Note` above, from a row that documents `Note` and `Task`, each with the base fields `id, scope=Scope()`, as `Note(content, title=None)` and `Task(title, done=False)`). An entry whose signature the skill labels partial (simplified, key parameters, a `...` standing in for omitted members, not rest or variadic syntax; a label in a table's column header, such as `Props (simplified)`, labels each of its rows) carries `signature_form: "partial"`, any other `"full"` or no key: copy the label, never judge the form.

A `cross_check_mismatches` entry gives its `export`, `reference_file`, `reference_line` and an `issue` that names each form by its file's path, and the pair's other side: the SKILL.md body's line as `skill_md_line`, or, for two references, the one that sorts first in codepoint order, by path and then line, as `other_file` and `other_line`, with the one that sorts last as `reference_file` and `reference_line`. Each file is its path in the package, such as `references/api-reference.md`.
