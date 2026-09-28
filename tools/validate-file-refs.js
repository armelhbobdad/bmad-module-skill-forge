/**
 * File Reference Validator
 *
 * Validates cross-file references in BMAD source files (agents, workflows, tasks, steps).
 * Catches broken file paths, missing referenced files, and absolute path leaks.
 *
 * What it checks:
 * - {project-root}/_bmad/ references in YAML and markdown resolve to real src/ files
 * - Relative path references (file.md, ../data/file.csv) point to existing files
 * - exec="..." and <invoke-task> targets exist
 * - Step metadata (thisStepFile, nextStepFile) references are valid
 * - Workflow-data frontmatter keys (<name>Data: 'assets/...' or 'references/...')
 *   resolved relative to the workflow root (parent of references/) — e.g.
 *   assemblyRulesData, skillSectionsData, extractionPatternsData
 * - Load directives (Load: `file.md`) target existing files
 * - No absolute paths (/Users/, /home/, C:\) leak into source files
 * - Every {project-root}/src/<path> is preceded by its installed twin
 *   {project-root}/_bmad/skf/<path>, earlier on the same line or on the line
 *   before. An installed project has no src/ tree, so a src/ path is only a
 *   dev-checkout fallback. Fenced code is scanned too, and so are .py, .toml
 *   and .json files.
 *
 * What it does NOT check (deferred):
 * - {installed_path} variable interpolation (self-referential, low risk)
 * - {{mustache}} template variables (runtime substitution)
 * - {config_source}:key dynamic YAML dereferences
 * - Bare src/<path> mentions written without {project-root}
 *
 * Usage:
 *   node tools/validate-file-refs.js            # Warn on broken references (exit 0)
 *   node tools/validate-file-refs.js --strict    # Fail on broken references (exit 1)
 *   node tools/validate-file-refs.js --verbose   # Show all checked references
 *   node tools/validate-file-refs.js --src-dir <dir>   # Scan <dir> instead of src/ (exit 2 if not a directory)
 *
 * Default mode is warning-only (exit 0) so adoption is non-disruptive.
 * Use --strict when you want CI or pre-commit to enforce valid references.
 */

const fs = require('node:fs');
const path = require('node:path');
// Dev-only tool — yaml and csv-parse are in devDependencies (runs via npm run quality / CI only)
const yaml = require('yaml');
const { parse: parseCsv } = require('csv-parse/sync');

// --src-dir points the tool at another tree (its own tests use fixture trees);
// the parent of that directory becomes the root for displayed paths.
const SRC_DIR_FLAG = process.argv.indexOf('--src-dir');
const SRC_DIR_ARG = SRC_DIR_FLAG === -1 ? null : process.argv[SRC_DIR_FLAG + 1];
const SRC_DIR = SRC_DIR_ARG ? path.resolve(SRC_DIR_ARG) : path.resolve(__dirname, '..', 'src');
const PROJECT_ROOT = path.dirname(SRC_DIR);
const VERBOSE = process.argv.includes('--verbose');
const STRICT = process.argv.includes('--strict');

// --- Constants ---

// File extensions to scan
const SCAN_EXTENSIONS = new Set(['.yaml', '.yml', '.md', '.xml', '.csv']);

// File extensions checked for unpaired {project-root}/src/ paths only
const PAIR_SCAN_EXTENSIONS = new Set([...SCAN_EXTENSIONS, '.py', '.toml', '.json']);

// Skip directories
const SKIP_DIRS = new Set(['node_modules', '.git', '.analysis', '__pycache__']);

// Pattern: {project-root}/_bmad/ references
const PROJECT_ROOT_REF = /\{project-root\}\/_bmad\/([^\s'"<>})\]`]+)/g;

// Patterns: {project-root}/src/ paths and their installed twins. Same path
// character class as PROJECT_ROOT_REF; at least one path character is
// required, so a bare mention of the root (`{project-root}/src/`) is no path.
const SRC_PATH_REF = /\{project-root\}\/src\/([^\s'"<>})\]`]+)/g;
const INSTALLED_PATH_REF = /\{project-root\}\/_bmad\/skf\/([^\s'"<>})\]`]+)/g;

// Pattern: {_bmad}/ shorthand references
const BMAD_SHORTHAND_REF = /\{_bmad\}\/([^\s'"<>})\]`]+)/g;

// Pattern: exec="..." attributes
const EXEC_ATTR = /exec="([^"]+)"/g;

// Pattern: <invoke-task> content
const INVOKE_TASK = /<invoke-task>([^<]+)<\/invoke-task>/g;

// Pattern: relative paths in quotes
const RELATIVE_PATH_QUOTED = /['"](\.\.\/?[^'"]+\.(?:md|yaml|yml|xml|json|csv|txt))['"]/g;
const RELATIVE_PATH_DOT = /['"](\.\/[^'"]+\.(?:md|yaml|yml|xml|json|csv|txt))['"]/g;

// Pattern: step metadata
const STEP_META = /(?:thisStepFile|nextStepFile|continueStepFile|skipToStepFile|altStepFile|workflowFile):\s*['"](\.[^'"]+)['"]/g;

// Pattern: workflow-data frontmatter keys
// Matches any `<name>Data:` frontmatter key with a bare relative path value
// (no leading ./ or ../). These paths resolve relative to the workflow root
// (parent of references/), not the step file's directory. Used by step files to
// reference shared assets like assets/compile-assembly-rules.md or
// references/extraction-patterns.md.
const WORKFLOW_DATA_REF = /(\w+Data):\s*['"]([^'"./][^'"]*\.(?:md|yaml|yml|json))['"]/g;

// Pattern: Load directives
const LOAD_DIRECTIVE = /Load[:\s]+`(\.[^`]+)`/g;

// Pattern: absolute path leaks
const ABS_PATH_LEAK = /(?:\/Users\/|\/home\/|[A-Z]:\\\\)/;

// --- Output Escaping ---

function escapeAnnotation(str) {
  return str.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
}

function escapeTableCell(str) {
  return String(str).replaceAll('|', String.raw`\|`);
}

// Path prefixes/patterns that only exist in installed structure, not in source.
// `agents/` is where bmad-method core agents land under `_bmad/`; referenced by
// some workflows (e.g. test-skill's --discovery-catalog=all escape hatch) but
// never sourced from this repo.
const INSTALL_ONLY_PATHS = ['_config/', '_memory/', 'agents/'];

// Files that are generated at install time and don't exist in the source tree
const INSTALL_GENERATED_FILES = ['config.yaml', 'config.user.yaml', 'VERSION', 'package.json'];

// Variables that indicate a path is not statically resolvable
const UNRESOLVABLE_VARS = [
  '{output_folder}',
  '{value}',
  '{timestamp}',
  '{config_source}:',
  '{installed_path}',
  '{shared_path}',
  '{planning_artifacts}',
  '{research_topic}',
  '{user_name}',
  '{communication_language}',
  '{epic_number}',
  '{next_epic_num}',
  '{epic_num}',
  '{part_id}',
  '{count}',
  '{date}',
  '{outputFile}',
  '{nextStepFile}',
  '{sidecar_path}',
  '{skills_output_folder}',
  '{forge_data_folder}',
  '{project_name}',
  '{document_output_language}',
  '{skf_folder}',
];

// --- File Discovery ---

function getSourceFiles(dir, extensions = SCAN_EXTENSIONS) {
  const files = [];

  function walk(currentDir) {
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });

    for (const entry of entries) {
      if (SKIP_DIRS.has(entry.name)) continue;

      const fullPath = path.join(currentDir, entry.name);

      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile() && extensions.has(path.extname(entry.name))) {
        files.push(fullPath);
      }
    }
  }

  walk(dir);
  return files;
}

// --- Code Block Stripping ---

function stripCodeBlocks(content) {
  return content.replaceAll(/```[\s\S]*?```/g, (m) => m.replaceAll(/[^\n]/g, ''));
}

function stripJsonExampleBlocks(content) {
  // Strip bare JSON example blocks: { and } each on their own line.
  // These are example/template data (not real file references).
  return content.replaceAll(/^\{\s*\n(?:.*\n)*?^\}\s*$/gm, (m) => m.replaceAll(/[^\n]/g, ''));
}

// --- Path Mapping ---

function mapInstalledToSource(refPath) {
  // Strip {project-root}/_bmad/ or {_bmad}/ prefix
  let cleaned = refPath.replace(/^\{project-root\}\/_bmad\//, '').replace(/^\{_bmad\}\//, '');

  // Also handle bare _bmad/ prefix (seen in some invoke-task)
  cleaned = cleaned.replace(/^_bmad\//, '');

  // Skip install-only paths (generated at install time, not in source)
  if (isInstallOnly(cleaned)) return null;

  // Map installed module names to their source directory names
  // _bmad/skf/ → src/ (SKF module)
  if (cleaned.startsWith('skf/')) {
    return path.join(SRC_DIR, cleaned.slice('skf/'.length));
  }

  // Fallback: map directly under src/
  return path.join(SRC_DIR, cleaned);
}

// --- Reference Extraction ---

function isResolvable(refStr) {
  // Skip refs containing unresolvable runtime variables
  if (refStr.includes('{{')) return false;
  // Skip node_modules references (runtime dependency paths)
  if (refStr.includes('node_modules')) return false;
  for (const v of UNRESOLVABLE_VARS) {
    if (refStr.includes(v)) return false;
  }
  return true;
}

function isInstallOnly(cleanedPath) {
  // Skip paths that only exist in the installed _bmad/ structure, not in src/
  for (const prefix of INSTALL_ONLY_PATHS) {
    if (cleanedPath.startsWith(prefix)) return true;
  }
  // Skip files that are generated during installation
  const basename = path.basename(cleanedPath);
  for (const generated of INSTALL_GENERATED_FILES) {
    if (basename === generated) return true;
  }
  return false;
}

function extractYamlRefs(filePath, content) {
  const refs = [];

  let doc;
  try {
    doc = yaml.parseDocument(content);
  } catch {
    return refs; // Skip unparseable YAML (schema validator handles this)
  }

  function checkValue(value, range, keyPath) {
    if (typeof value !== 'string') return;
    if (!isResolvable(value)) return;

    const line = range ? offsetToLine(content, range[0]) : undefined;

    // Check for {project-root}/_bmad/ refs
    const prMatch = value.match(/\{project-root\}\/_bmad\/[^\s'"<>})\]`]+/);
    if (prMatch) {
      refs.push({ file: filePath, raw: prMatch[0], type: 'project-root', line, key: keyPath });
    }

    // Check for {_bmad}/ refs
    const bmMatch = value.match(/\{_bmad\}\/[^\s'"<>})\]`]+/);
    if (bmMatch) {
      refs.push({ file: filePath, raw: bmMatch[0], type: 'project-root', line, key: keyPath });
    }

    // Check for relative paths
    const relMatch = value.match(/^\.\.?\/[^\s'"<>})\]`]+\.(?:md|yaml|yml|xml|json|csv|txt)$/);
    if (relMatch) {
      refs.push({ file: filePath, raw: relMatch[0], type: 'relative', line, key: keyPath });
    }
  }

  function walkNode(node, keyPath) {
    if (!node) return;

    if (yaml.isMap(node)) {
      for (const item of node.items) {
        const key = item.key && item.key.value !== undefined ? item.key.value : '?';
        const childPath = keyPath ? `${keyPath}.${key}` : String(key);
        walkNode(item.value, childPath);
      }
    } else if (yaml.isSeq(node)) {
      for (const [i, item] of node.items.entries()) {
        walkNode(item, `${keyPath}[${i}]`);
      }
    } else if (yaml.isScalar(node)) {
      checkValue(node.value, node.range, keyPath);
    }
  }

  walkNode(doc.contents, '');
  return refs;
}

function offsetToLine(content, offset) {
  let line = 1;
  for (let i = 0; i < offset && i < content.length; i++) {
    if (content[i] === '\n') line++;
  }
  return line;
}

function extractMarkdownRefs(filePath, content) {
  const refs = [];
  const stripped = stripJsonExampleBlocks(stripCodeBlocks(content));

  function runPattern(regex, type) {
    regex.lastIndex = 0;
    let match;
    while ((match = regex.exec(stripped)) !== null) {
      const raw = match[1];
      if (!isResolvable(raw)) continue;
      refs.push({ file: filePath, raw, type, line: offsetToLine(stripped, match.index) });
    }
  }

  // {project-root}/_bmad/ refs
  runPattern(PROJECT_ROOT_REF, 'project-root');

  // {_bmad}/ shorthand
  runPattern(BMAD_SHORTHAND_REF, 'project-root');

  // exec="..." attributes
  runPattern(EXEC_ATTR, 'exec-attr');

  // <invoke-task> tags
  runPattern(INVOKE_TASK, 'invoke-task');

  // Step metadata
  runPattern(STEP_META, 'relative');

  // Workflow-data frontmatter keys — capture the path (group 2, not group 1 which is the key name)
  {
    WORKFLOW_DATA_REF.lastIndex = 0;
    let match;
    while ((match = WORKFLOW_DATA_REF.exec(stripped)) !== null) {
      const raw = match[2];
      if (!isResolvable(raw)) continue;
      refs.push({ file: filePath, raw, type: 'workflow-data', line: offsetToLine(stripped, match.index) });
    }
  }

  // Load directives
  runPattern(LOAD_DIRECTIVE, 'relative');

  // Relative paths in quotes
  runPattern(RELATIVE_PATH_QUOTED, 'relative');
  runPattern(RELATIVE_PATH_DOT, 'relative');

  return refs;
}

function extractCsvRefs(filePath, content) {
  const refs = [];

  let records;
  try {
    records = parseCsv(content, {
      columns: true,
      skip_empty_lines: true,
      relax_column_count: true,
    });
  } catch (error) {
    // No CSV schema validator exists yet (planned as Layer 2c) — surface parse errors visibly.
    // YAML equivalent (line ~198) defers to validate-agent-schema.js; CSV has no such fallback.
    const rel = path.relative(PROJECT_ROOT, filePath);
    console.error(`  [CSV-PARSE-ERROR] ${rel}: ${error.message}`);
    if (process.env.GITHUB_ACTIONS) {
      console.log(`::warning file=${rel},line=1::${escapeAnnotation(`CSV parse error: ${error.message}`)}`);
    }
    return refs;
  }

  // Columns known to contain file path references
  const FILE_PATH_COLUMNS = ['workflow-file', 'fragment_file'];

  const firstRecord = records[0];
  if (!firstRecord) return refs;

  // Find which file-path columns exist in this CSV
  const activeColumns = FILE_PATH_COLUMNS.filter((col) => col in firstRecord);
  if (activeColumns.length === 0) return refs;

  for (const [i, record] of records.entries()) {
    for (const col of activeColumns) {
      const raw = record[col];
      if (!raw || raw.trim() === '') continue;
      if (!isResolvable(raw)) continue;
      // skill: prefixed references are resolved by the IDE/CLI, not as file paths
      if (raw.startsWith('skill:')) continue;

      // Line = header (1) + data row index (0-based) + 1
      const line = i + 2;
      refs.push({ file: filePath, raw, type: 'project-root', line });
    }
  }

  return refs;
}

// --- Reference Resolution ---

function resolveRef(ref) {
  if (ref.type === 'project-root') {
    return mapInstalledToSource(ref.raw);
  }

  if (ref.type === 'relative') {
    return path.resolve(path.dirname(ref.file), ref.raw);
  }

  if (ref.type === 'workflow-data') {
    // Two resolution conventions:
    //  1. Bare path starting with a workflow name (e.g., 'skf-create-skill/references/foo.md')
    //     → resolve relative to src/ (cross-workflow reference).
    //  2. Bare path starting with 'assets/' or 'references/' (or any other directory that is
    //     NOT a sibling workflow) → resolve relative to the current workflow root.
    const stepParent = path.dirname(ref.file); // src/{workflow}/steps-c
    const workflowRoot = path.dirname(stepParent); // src/{workflow}
    const firstSegment = ref.raw.split('/')[0];
    const crossWorkflowCandidate = path.join(SRC_DIR, firstSegment);
    if (firstSegment && fs.existsSync(crossWorkflowCandidate) && fs.statSync(crossWorkflowCandidate).isDirectory()) {
      // First segment is a real directory under src/ — treat as cross-workflow reference.
      return path.resolve(SRC_DIR, ref.raw);
    }
    // Default: resolve relative to the current workflow root.
    return path.resolve(workflowRoot, ref.raw);
  }

  if (ref.type === 'exec-attr') {
    let execPath = ref.raw;
    if (execPath.includes('{project-root}')) {
      return mapInstalledToSource(execPath);
    }
    if (execPath.includes('{_bmad}')) {
      return mapInstalledToSource(execPath);
    }
    if (execPath.startsWith('_bmad/')) {
      return mapInstalledToSource(execPath);
    }
    // Relative exec path
    return path.resolve(path.dirname(ref.file), execPath);
  }

  if (ref.type === 'invoke-task') {
    // Extract file path from invoke-task content
    const prMatch = ref.raw.match(/\{project-root\}\/_bmad\/([^\s'"<>})\]`]+)/);
    if (prMatch) return mapInstalledToSource(prMatch[0]);

    const bmMatch = ref.raw.match(/\{_bmad\}\/([^\s'"<>})\]`]+)/);
    if (bmMatch) return mapInstalledToSource(bmMatch[0]);

    const bareMatch = ref.raw.match(/_bmad\/([^\s'"<>})\]`]+)/);
    if (bareMatch) return mapInstalledToSource(bareMatch[0]);

    return null; // Can't resolve — skip
  }

  return null;
}

// --- Absolute Path Leak Detection ---

function checkAbsolutePathLeaks(filePath, content) {
  const leaks = [];
  const stripped = stripCodeBlocks(content);
  const lines = stripped.split('\n');

  for (const [i, line] of lines.entries()) {
    if (ABS_PATH_LEAK.test(line)) {
      leaks.push({ file: filePath, line: i + 1, content: line.trim() });
    }
  }

  return leaks;
}

// --- Installed-Twin Check for src/ Paths ---

function pathTokens(line, regex) {
  const tokens = [];
  regex.lastIndex = 0;
  let match;
  while ((match = regex.exec(line)) !== null) {
    // A path that ends a sentence or a list item keeps its punctuation in the
    // capture; drop it so `foo.md.` and `foo.md,` both mean `foo.md`.
    tokens.push({ column: match.index, token: match[0], path: match[1].replace(/[.,;:]+$/, '') });
  }
  return tokens;
}

/**
 * Find every {project-root}/src/<path> in raw text and say whether it is
 * paired: its installed twin {project-root}/_bmad/skf/<path> (the same path)
 * appears earlier on the same line or anywhere on the line before. Runs on
 * raw text on purpose: fenced commands are what an agent copies and runs.
 *
 * @param {string} content - Raw file text (LF or CRLF)
 * @returns {{line: number, column: number, token: string, path: string, paired: boolean}[]}
 */
function findSrcPathRefs(content) {
  const refs = [];
  const lines = content.split('\n');
  for (const [i, line] of lines.entries()) {
    const srcTokens = pathTokens(line, SRC_PATH_REF);
    if (srcTokens.length === 0) continue;
    const here = pathTokens(line, INSTALLED_PATH_REF);
    const before = new Set(i > 0 ? pathTokens(lines[i - 1], INSTALLED_PATH_REF).map((t) => t.path) : []);
    for (const src of srcTokens) {
      const paired = before.has(src.path) || here.some((t) => t.path === src.path && t.column < src.column);
      refs.push({ line: i + 1, column: src.column, token: src.token, path: src.path, paired });
    }
  }
  return refs;
}

// --- Exports (for testing) ---
module.exports = { extractCsvRefs, findSrcPathRefs, PAIR_SCAN_EXTENSIONS };

// --- Main ---

if (require.main === module) {
  if (SRC_DIR_FLAG !== -1 && !(SRC_DIR_ARG && fs.existsSync(SRC_DIR) && fs.statSync(SRC_DIR).isDirectory())) {
    console.error('--src-dir needs an existing directory');
    process.exit(2);
  }

  console.log(`\nValidating file references in: ${SRC_DIR}`);
  console.log(`Mode: ${STRICT ? 'STRICT (exit 1 on issues)' : 'WARNING (exit 0)'}${VERBOSE ? ' + VERBOSE' : ''}\n`);

  const files = getSourceFiles(SRC_DIR, PAIR_SCAN_EXTENSIONS);
  console.log(`Found ${files.length} source files\n`);

  let totalRefs = 0;
  let brokenRefs = 0;
  let totalLeaks = 0;
  let totalUnpaired = 0;
  let filesWithIssues = 0;
  const allIssues = []; // Collect for $GITHUB_STEP_SUMMARY

  for (const filePath of files) {
    const relativePath = path.relative(PROJECT_ROOT, filePath);
    const content = fs.readFileSync(filePath, 'utf-8');
    const ext = path.extname(filePath);

    // Extract references (the .py, .toml and .json files are read only for
    // the src/-path check below)
    const refScanned = SCAN_EXTENSIONS.has(ext);
    let refs;
    if (!refScanned) {
      refs = [];
    } else if (ext === '.yaml' || ext === '.yml') {
      refs = extractYamlRefs(filePath, content);
    } else if (ext === '.csv') {
      refs = extractCsvRefs(filePath, content);
    } else {
      refs = extractMarkdownRefs(filePath, content);
    }

    // Resolve and classify all refs before printing anything.
    // This avoids the confusing pattern of printing headers at two different
    // times depending on verbosity — collect first, then print once.
    const broken = [];
    const ok = [];

    for (const ref of refs) {
      totalRefs++;
      const resolved = resolveRef(ref);

      if (resolved && !fs.existsSync(resolved)) {
        const hasExt = path.extname(resolved) !== '';
        if (!hasExt) {
          // Extensionless path that doesn't exist — not a file, not a directory.
          // Flag as UNRESOLVED (distinct from BROKEN which means "file with extension not found").
          broken.push({ ref, resolved: path.relative(PROJECT_ROOT, resolved), kind: 'unresolved' });
          brokenRefs++;
          continue;
        }
        broken.push({ ref, resolved: path.relative(PROJECT_ROOT, resolved), kind: 'broken' });
        brokenRefs++;
        continue;
      }

      if (resolved) {
        ok.push({ ref, tag: 'OK' });
      }
    }

    // Check absolute path leaks
    const leaks = refScanned ? checkAbsolutePathLeaks(filePath, content) : [];
    totalLeaks += leaks.length;

    // Check {project-root}/src/ paths for their installed twin (raw text)
    const unpaired = findSrcPathRefs(content).filter((ref) => !ref.paired);
    totalUnpaired += unpaired.length;

    // Print results — file header appears once, in one place
    const hasFileIssues = broken.length > 0 || leaks.length > 0 || unpaired.length > 0;

    if (hasFileIssues) {
      filesWithIssues++;
      console.log(`\n${relativePath}`);

      if (VERBOSE) {
        for (const { ref, tag, note } of ok) {
          const suffix = note ? ` (${note})` : '';
          console.log(`  [${tag}] ${ref.raw}${suffix}`);
        }
      }

      for (const { ref, resolved, kind } of broken) {
        const location = ref.line ? `line ${ref.line}` : ref.key ? `key: ${ref.key}` : '';
        const tag = kind === 'unresolved' ? 'UNRESOLVED' : 'BROKEN';
        const detail = kind === 'unresolved' ? 'Not found as file or directory' : 'Target not found';
        const issueType = kind === 'unresolved' ? 'unresolved path' : 'broken ref';
        console.log(`  [${tag}] ${ref.raw}${location ? ` (${location})` : ''}`);
        console.log(`     ${detail}: ${resolved}`);
        allIssues.push({ file: relativePath, line: ref.line || 1, ref: ref.raw, issue: issueType });
        if (process.env.GITHUB_ACTIONS) {
          const line = ref.line || 1;
          console.log(
            `::warning file=${relativePath},line=${line}::${escapeAnnotation(`${tag === 'UNRESOLVED' ? 'Unresolved path' : 'Broken reference'}: ${ref.raw} → ${resolved}`)}`,
          );
        }
      }

      for (const leak of leaks) {
        console.log(`  [ABS-PATH] Line ${leak.line}: ${leak.content}`);
        allIssues.push({ file: relativePath, line: leak.line, ref: leak.content, issue: 'abs-path' });
        if (process.env.GITHUB_ACTIONS) {
          console.log(`::warning file=${relativePath},line=${leak.line}::${escapeAnnotation(`Absolute path leak: ${leak.content}`)}`);
        }
      }

      for (const ref of unpaired) {
        const twin = `{project-root}/_bmad/skf/${ref.path}`;
        console.log(`  [SRC-PATH] Line ${ref.line}: ${ref.token}`);
        console.log(`     No installed twin before it: put ${twin} earlier on the line or on the line before`);
        allIssues.push({ file: relativePath, line: ref.line, ref: ref.token, issue: 'src-path unpaired' });
        if (process.env.GITHUB_ACTIONS) {
          console.log(
            `::warning file=${relativePath},line=${ref.line}::${escapeAnnotation(`src/ path with no installed twin before it: ${ref.token} (add ${twin})`)}`,
          );
        }
      }
    } else if (VERBOSE && refs.length > 0) {
      console.log(`\n${relativePath}`);
      for (const { ref, tag, note } of ok) {
        const suffix = note ? ` (${note})` : '';
        console.log(`  [${tag}] ${ref.raw}${suffix}`);
      }
    }
  }

  // Summary
  console.log(`\n${'─'.repeat(60)}`);
  console.log(`\nSummary:`);
  console.log(`   Files scanned: ${files.length}`);
  console.log(`   References checked: ${totalRefs}`);
  console.log(`   Broken references: ${brokenRefs}`);
  console.log(`   Absolute path leaks: ${totalLeaks}`);
  console.log(`   Unpaired src/ paths: ${totalUnpaired}`);

  const hasIssues = brokenRefs > 0 || totalLeaks > 0 || totalUnpaired > 0;

  if (hasIssues) {
    console.log(`\n   ${filesWithIssues} file(s) with issues`);

    if (STRICT) {
      console.log(`\n   [STRICT MODE] Exiting with failure.`);
    } else {
      console.log(`\n   Run with --strict to treat warnings as errors.`);
    }
  } else {
    console.log(`\n   All file references valid!`);
  }

  console.log('');

  // Write GitHub Actions step summary
  if (process.env.GITHUB_STEP_SUMMARY) {
    let summary = '## File Reference Validation\n\n';
    if (allIssues.length > 0) {
      summary += '| File | Line | Reference | Issue |\n';
      summary += '|------|------|-----------|-------|\n';
      for (const issue of allIssues) {
        summary += `| ${escapeTableCell(issue.file)} | ${issue.line} | ${escapeTableCell(issue.ref)} | ${issue.issue} |\n`;
      }
      summary += '\n';
    }
    summary += `**${files.length} files scanned, ${totalRefs} references checked, ${brokenRefs + totalLeaks + totalUnpaired} issues found**\n`;
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
  }

  process.exit(hasIssues && STRICT ? 1 : 0);
}
