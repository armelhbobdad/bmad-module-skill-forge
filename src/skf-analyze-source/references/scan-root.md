<!-- Config: communicate in {communication_language}. -->

# The Scan Root of a Project Path

Every helper of the step-by-step analysis reads a local folder, the project path's **scan root**, never `{project-root}` (the forge workspace). scan-project makes one for each entry of `project_paths[]` and records it in the report's `scan_roots`, discover-additional-source makes one for the path it adds, and identify-units and map-and-detect make one again when a session that resumed the report no longer finds it. `{i}` is the path's place in `project_paths[]` (1 for the first), and its **ref** is its entry in the report's `refs` (a path `refs` leaves out has none). In every command below, a leading `~` of a local path is written as `$HOME`: the commands quote every path, and a `~` inside double quotes does not expand.

- **A local path** (it starts with `/`, `./` or `~`, or names an existing folder) **with no ref:** the path itself. Nothing is copied.
- **A local path with a ref:** the path's folder inside a copy of its repository at the ref, so a package folder of a monorepo is read at the ref too. Print the repository's top folder and the path's place in it, then copy the top folder:

  ```bash
  git -C "{path}" rev-parse --show-toplevel --show-prefix
  git clone --quiet --branch {ref} "{the first line it printed}" "{run_dir}/source-{i}"
  ```

  The scan root is `{run_dir}/source-{i}/` followed by the second line without its trailing slash, or `{run_dir}/source-{i}` itself when that line is empty (the path is the top folder).
- **A remote path:** a copy at its ref, or at the default branch when it has none, which is the scan root:

  ```bash
  git clone --quiet --depth 1 {ref_flag} "{url}" "{run_dir}/source-{i}"
  ```

  `{ref_flag}` is `--branch {ref}` when the path has a ref, else nothing. `{url}` is the URL git reads: the path itself when it starts with a scheme (`https://`, `http://`, `ssh://`, `git://`) or is an SSH address (`git@github.com:acme/mono.git`); `https://github.com/{path}` for the `owner/repo` shorthand (`acme/mono`); and `https://{path}` for a host path without a scheme (`github.com/acme/mono`, `gitlab.com/group/repo`). git reads a shorthand or a host path as a local folder, so it never gets one. The project path stays as it was given everywhere else: in `project_paths[]`, the keys of `scan_roots` and `refs`, and each brief's `source_repo`.

When a command fails, the file that loaded this one says what happens, with the first line it printed on stderr.
