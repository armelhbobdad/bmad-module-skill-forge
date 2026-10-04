---
skillInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'
  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'
---

<!-- Config: communicate in {communication_language}. -->

# The Scan Root of a Project Path

Every helper of the step-by-step analysis reads a local folder, the project path's **scan root**, never `{project-root}` (the forge workspace). scan-project makes one for each entry of `project_paths[]` and records it in the report's `scan_roots`, discover-additional-source makes one for the path it adds, and identify-units and map-and-detect make one again when a session that resumed the report no longer finds it. `{i}` is the path's place in `project_paths[]` (1 for the first), and its **ref** is its entry in the report's `refs` (a path `refs` leaves out has none). In every command below, a leading `~` of a local path is written as `$HOME`: the commands quote every path, and a `~` inside double quotes does not expand.

**What the path is.** The helper that names every unit tells a local path from a repository and gives the URL git clones a repository from. Resolve `{skillInventoryHelper}` from `{skillInventoryProbeOrder}` (first existing path wins; with none, the command below fails with "`skf-skill-inventory.py` is missing. Re-install SKF." as its first stderr line) and run:

```bash
uv run {skillInventoryHelper} derive-name --target "{path}" --probe-git
```

Its `kind` is `local` for a local path, `remote` for a repository and `docs` for a documentation URL, and its `clone_url` is the URL git reads for a repository.

- **A local path** (`kind` is `local`) **with no ref:** the path itself. Nothing is copied.
- **A local path with a ref:** the path's folder inside a copy of its repository at the ref, so a package folder of a monorepo is read at the ref too. Print the repository's top folder and the path's place in it, then copy the top folder:

  ```bash
  git -C "{path}" rev-parse --show-toplevel --show-prefix
  git clone --quiet --branch {ref} "{the first line it printed}" "{run_dir}/source-{i}"
  ```

  The scan root is `{run_dir}/source-{i}/` followed by the second line without its trailing slash, or `{run_dir}/source-{i}` itself when that line is empty (the path is the top folder).
- **A remote path** (`kind` is `remote`): a copy at its ref, or at the default branch when it has none, which is the scan root:

  ```bash
  git clone --quiet --depth 1 {ref_flag} "{clone_url}" "{run_dir}/source-{i}"
  ```

  `{ref_flag}` is `--branch {ref}` when the path has a ref, else nothing. The project path stays as it was given everywhere else: in `project_paths[]`, the keys of `scan_roots` and `refs`, and each brief's `source_repo`.
- **A documentation URL** (`kind` is `docs`): there is no repository to scan. Treat it as a command that failed with its `halt_message` as the first stderr line when it gives one (the message the [auto] path halts with), else with "{path} is a documentation URL: run the analysis with [auto] for a docs-only brief".

When a command fails, the file that loaded this one says what happens, with the first line it printed on stderr.
