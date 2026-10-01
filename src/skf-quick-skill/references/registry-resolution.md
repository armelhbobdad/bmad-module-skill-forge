<!-- Config: communicate in {communication_language}. -->

# Registry Resolution: Web Search Fallback

`skf-resolve-package.py` reads every target and asks the registries, npm, PyPI and crates.io, and resolve-target §1b to §3 act on its JSON. This file holds what the script leaves to judgment: the web search for a name no registry resolved (resolve-target §3, `status: "fallthrough"`), which a Go module path or a Maven coordinate also tries (resolve-target §2).

## Search

Search `"{package_name} github repository"`, spending at most 15 seconds, and read the top results for a `github.com/<owner>/<repo>` URL.

## Pick the Repository

Take a URL only when that repository is the package's source: its name, or the package or module name its page shows, matches `{package_name}` (`uber-go/zap` for `go.uber.org/zap`, `google/guava` for `com.google.guava:guava`). Prefer the project's own repository over a fork, a mirror or a list that links to it, and keep a `/tree/<ref>/<folder>` URL whole when the package is one folder of a larger repository.

## Result

- **A URL:** resolve-target takes it as the target and parses it again from §1b.
- **None, or the search timed out:** resolve-target halts with its resolution failure.
