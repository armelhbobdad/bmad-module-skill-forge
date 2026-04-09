# Output Contract Schema

Every pipeline-capable skill writes a result JSON file at its final step. This enables reliable CI integration and pipeline chaining.

## Schema

```json
{
  "skill": "skf-skill-name",
  "status": "success" | "failed" | "partial",
  "timestamp": "ISO-8601",
  "outputs": [
    {"type": "report|skill|manifest|config", "path": "relative/path/to/file"}
  ],
  "summary": {
    // skill-specific summary fields
  }
}
```

Write to: `{output_dir}/{skill-name}-result.json`
