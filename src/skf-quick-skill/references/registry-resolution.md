<!-- Config: communicate in {communication_language}. -->

# Registry Resolution Patterns

## Package-to-Repo Resolution

When the user provides a package name instead of a GitHub URL, use this registry chain to resolve the source repository. `skf-resolve-package.py` reads the target (`parse-target`) and asks every registry of this chain (`resolve`). Apply the target shapes and registries 1 to 3 by hand only when that script is missing or fails; the web-search fallback and the failure message always apply.

### Detection: Target Shapes

- **GitHub URL:** a github.com repository in any form (`https://`, `git+https://`, `git://`, `git@github.com:`, `github.com/`, `github:` or `<owner>/<repo>`), with or without `.git`. The repository is the first two path parts, dots included (`vercel/next.js`); a `/tree/<ref>/<folder>` tail also gives the ref to read and the folder to scope to. Extract owner/repo directly.
- **Package name:** an npm, PyPI or crates.io name (`lodash`, `@scope/name`, `zope.interface`), optionally ending in `@<version>`, or in `==<version>`, PyPI's pin. A version starts with a digit, or with `v` and a digit; a word such as `latest` or `canary` after the `@` is an npm dist-tag, which pins no version. Look a `==` pin up on PyPI only and a scoped `@scope/name` on npm only; enter the resolution chain below with any other name.
- **Registry page:** `https://www.npmjs.com/package/<name>`, `https://pypi.org/project/<name>` or `https://crates.io/crates/<name>`, optionally with a version (a tab such as crates.io's `/versions` is none): look the name up on that registry only.
- **Another host or a local path:** a URL on another host, or a path starting with `.`, `/`, `\`, `~` or a drive letter. Quick Skill reads GitHub repositories only, so neither resolves.
- **Anything else** (a sentence, for example) is not a target.

**Skill name:** the skill is written under the package name, else the last part of a `/tree/` folder, else the repository name, in lower case with each run of other characters turned into one hyphen (`@babel/core` is `babel-core`, `vercel/next.js` is `next-js`).

### Resolution Fallback Chain

Ask every registry of the chain; the first one, in chain order, that gives a GitHub repository is the pick. A language hint of JavaScript, TypeScript, Python or Rust asks that language's registry alone. When another registry answered for the name with anything other than a 404 or a timeout (it resolves the name too, knows it but gives no GitHub link, or could not be read), the name is **ambiguous**, and those registries are its `also_found_in`: resolve-target §3 handles it. The folder a registry gives for the package (npm's `repository.directory`, or the folder of a `/tree/<ref>/<folder>` repository URL) becomes the default scope.

**Per-call timeout:** apply a 10s timeout to each registry HTTP call (15s for the web-search fallback) so a single hung registry cannot stall the workflow under hostile network conditions. Treat a timeout as a soft failure, like a 404: the registry holds no candidate.

#### 1. npm Registry (JavaScript/TypeScript)

```
URL: https://registry.npmjs.org/{package_name}
Field: repository.url
Fallback field: homepage
Folder field: repository.directory
```

Extract `repository.url`, strip `git+` prefix and `.git` suffix if present. `repository.directory` names the package's folder in a monorepo (`packages/react` for `react`).

#### 2. PyPI Registry (Python)

```
URL: https://pypi.org/pypi/{package_name}/json
Field: info.project_urls.source OR .sourcecode OR .repository OR .github OR .homepage, then info.home_page
```

Read the `project_urls` labels in any letter case, without spaces or punctuation (`Source Code` is `sourcecode`), in that order. Filter for GitHub URLs.

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

Language detection is authoritative in `resolve-target.md` §4 (Detect Language) — this file covers only the package-to-repo registry chain.
