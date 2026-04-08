# Registry Resolution Patterns

## Package-to-Repo Resolution

When the user provides a package name instead of a GitHub URL, use this fallback chain to resolve the source repository.

### Detection: URL vs Package Name

- **GitHub URL:** Starts with `https://github.com/` or `github.com/` — extract org/repo directly
- **Package name:** Everything else — enter resolution chain below

### Resolution Fallback Chain

Try each registry in order. Stop at first success.

#### 1. npm Registry (JavaScript/TypeScript)

```
URL: https://registry.npmjs.org/{package_name}
Field: repository.url
Fallback field: homepage
```

Extract `repository.url`, strip `git+` prefix and `.git` suffix if present.

#### 2. PyPI Registry (Python)

```
URL: https://pypi.org/pypi/{package_name}/json
Field: info.project_urls.Source OR info.project_urls.Repository OR info.home_page
```

Check `project_urls` keys in order: Source, Repository, Homepage. Filter for GitHub URLs.

#### 3. crates.io Registry (Rust)

```
URL: https://crates.io/api/v1/crates/{package_name}
Field: crate.repository
```

Direct `repository` field usually points to GitHub.

#### 4. Web Search Fallback

If all registry lookups fail:

```
Search: "{package_name} github repository"
```

Look for GitHub URL in top results. Verify it matches the package name.

#### 5. Resolution Failure

If all methods fail:

```
"Could not resolve '{package_name}' to a GitHub repository.

Please provide the GitHub URL directly, or check:
- Is the package name spelled correctly?
- Is it a private package?
- Is the source hosted on a non-GitHub platform?"
```

**Hard halt** — cannot proceed without a resolved source.

## Language Detection

After resolving to a GitHub repo, detect primary language from:

1. Manifest file presence:
   - `package.json` → JavaScript/TypeScript
   - `pyproject.toml` or `setup.py` → Python
   - `Cargo.toml` → Rust
   - `go.mod` → Go
   - `pom.xml` or `build.gradle` → Java
2. User-provided language hint (overrides detection)
3. GitHub API language field (if accessible)

## Manifest File Priority

For each language, the primary manifest to read:

| Language | Manifest       | Key Fields                                                               |
|----------|----------------|--------------------------------------------------------------------------|
| JS/TS    | package.json   | name, version, description, main, exports, dependencies                  |
| Python   | pyproject.toml | project.name, project.version, project.description, project.dependencies |
| Rust     | Cargo.toml     | package.name, package.version, package.description, dependencies         |
| Go       | go.mod         | module path, require list                                                |
