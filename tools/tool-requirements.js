/**
 * Tool Requirements
 *
 * src/shared/tool-requirements.yaml is the one list of the external tools SKF
 * uses (Node, Python, uv, git, gh, ast-grep, ccc, qmd, tessl, skill-check),
 * with each one's minimum and tested versions. Its header says how those
 * numbers are set. This tool generates the prerequisites table in
 * docs/getting-started.md from it and checks every other copy of those
 * versions in the repository against it.
 *
 * What --check reports, each finding with its file and line:
 * - The list itself: schema_version 1, the keys of every tool, versions
 *   written as strings, a minimum for Node and Python (the copy checks
 *   compare with it), and no minimum above every tested version.
 * - The table between the tool-requirements markers in
 *   docs/getting-started.md differs from what --write generates.
 * - A prose minimum ("Node.js >= 22", "Python ≥ 3.11") in README.md,
 *   CONTRIBUTING.md or docs/, or the README Python badge, differs from the
 *   tool's minimum. The install lines of README.md, docs/index.md,
 *   docs/getting-started.md and CONTRIBUTING.md must state both the Node.js
 *   and the Python minimum.
 * - package.json engines.node is not ">=" Node's minimum.
 * - .nvmrc is not one of Node's tested versions.
 * - The install smoke test's node-version is not Node's minimum, or another
 *   workflow's node-version is not one of Node's tested versions.
 * - A python-version in .github/workflows/ is not one of Python's tested
 *   versions, or no workflow runs Python's minimum.
 *   Both are read from the `with:` of each step and job, a list or a
 *   multi-line value item by item. `${{ matrix.<key> }}` reads the job's
 *   strategy.matrix values for that key (its list and include entries); any
 *   other expression is skipped. A workflow that is not YAML is reported.
 * - The ast-grep-cli== pin in package.json test:python is not one of
 *   ast-grep's tested versions.
 * - The README Acknowledgements table has no row for a tier or optional
 *   tool (its acknowledged_as).
 * - A PEP 723 requires-python header under src/ is below Python's minimum.
 *   This check is off (REQUIRES_PYTHON_CHECK) until every header declares
 *   the minimum: turn it on in the change that raises them.
 *
 * --write regenerates the table, then checks. The other copies are only
 * reported: each finding says which value the list expects there.
 *
 * No network and no other checkout, so it runs on every pull request.
 *
 * Usage:
 *   node tools/tool-requirements.js --check          # Exit 1 on any mismatch
 *   node tools/tool-requirements.js --write          # Regenerate the table, then check
 *   node tools/tool-requirements.js --root <dir>     # Check another checkout (its tests use this)
 *
 * Exit codes:
 *   0  every copy agrees with the list
 *   1  a mismatch (or, with --write, one the table rewrite could not fix)
 *   2  cannot run: no --check or --write, or the list is missing or not YAML
 */

const fs = require('node:fs');
const path = require('node:path');
// Dev-only tool: yaml is a devDependency (the validate job runs npm ci first).
const YAML = require('yaml');

const REQUIREMENTS = 'src/shared/tool-requirements.yaml';
const PREREQUISITES_DOC = 'docs/getting-started.md';
const START = '<!-- tool-requirements:start -->';
const END = '<!-- tool-requirements:end -->';
const GENERATED_NOTE =
  '<!-- Generated from src/shared/tool-requirements.yaml by `node tools/tool-requirements.js --write`: edit that file, not this table. -->';
const REQUIRES_PYTHON_CHECK = false;

const VERSION = /^\d+(?:\.\d+)*$/;
const TIERS = ['Quick', 'Forge', 'Forge+', 'Deep'];
const KINDS = ['runtime', 'tier', 'optional'];
// The tools whose copies this tool checks by key, and those whose minimum it
// compares the copies with.
const REQUIRED_TOOLS = ['node', 'python', 'ast_grep'];
const REQUIRED_MINIMUMS = ['node', 'python'];
const TOOL_KEYS = {
  name: 'string',
  summary: 'optional-string',
  kind: 'kind',
  tiers: 'tiers',
  workflows: 'workflows',
  used_for: 'string',
  minimum: 'minimum',
  tested: 'tested',
  basis: 'string',
  version_command: 'command',
  install_url: 'url',
  upgrade: 'string',
  acknowledged_as: 'optional-string',
};

const TABLE_HEADER = ['Tool', 'Used for', 'Minimum', 'Tested on', 'Install'];
// Rows with no version to check, appended after the tools.
const FIXED_ROWS = [
  [
    '`ast-grep` MCP server (recommended alongside CLI)',
    'Optional in Forge, Forge+ and Deep: workflows use it when present and fall back to the CLI',
    '',
    '',
    '<https://github.com/ast-grep/ast-grep-mcp>',
  ],
  [
    '`SNYK_TOKEN` (Snyk API token, **Enterprise plan required**)',
    'Optional security scan',
    '',
    '',
    '<https://docs.snyk.io/snyk-api/authentication-for-api>',
  ],
];

// Prose names a tool goes by where they differ from its `name`.
const PROSE_NAMES = { node: ['Node.js', 'Node'] };
// Files whose install line must state these minimums.
const REQUIRED_PROSE = {
  'README.md': ['node', 'python'],
  'docs/index.md': ['node', 'python'],
  'docs/getting-started.md': ['node', 'python'],
  'CONTRIBUTING.md': ['node', 'python'],
};
const PYTHON_BADGE = /img\.shields\.io\/badge\/python-%3E%3D([\d.]+)-/i;
const WORKFLOWS_DIR = '.github/workflows';
const INSTALL_SMOKE = '.github/workflows/install-smoke.yaml';
const MATRIX_VALUE = /^\$\{\{\s*matrix\.([A-Za-z_][\w-]*)\s*\}\}$/;
const AST_GREP_PIN = /--with ast-grep-cli==([^\s"]+)/;

class CannotRun extends Error {}

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1];
}

function toPosix(file) {
  return file.split(path.sep).join('/');
}

function readLines(root, file) {
  try {
    return fs.readFileSync(path.join(root, file), 'utf8').split(/\r?\n/);
  } catch {
    return null;
  }
}

function escapeRegExp(text) {
  return text.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

/** Compare dotted versions, reading missing parts as 0 ("22" equals "22.0.0"). */
function compareVersions(a, b) {
  const x = String(a).split('.').map(Number);
  const y = String(b).split('.').map(Number);
  for (let index = 0; index < Math.max(x.length, y.length); index += 1) {
    const diff = (x[index] ?? 0) - (y[index] ?? 0);
    if (diff !== 0) return Math.sign(diff);
  }
  return 0;
}

function isTested(tool, version) {
  return tool.tested.some((tested) => compareVersions(tested, version) === 0);
}

function listVersions(versions) {
  return versions.length > 0 ? versions.join(', ') : 'none recorded';
}

/**
 * Parse YAML text. `nodeLine(node)` is the 1-based line a node starts on;
 * `error` is the first parse error as { line, message }, or null.
 */
function parseYaml(text) {
  const lineCounter = new YAML.LineCounter();
  const doc = YAML.parseDocument(text, { lineCounter, prettyErrors: false });
  const nodeLine = (node) => lineCounter.linePos(node.range[0]).line;
  const first = doc.errors[0];
  const error = first
    ? {
        line: first.linePos ? first.linePos[0].line : lineCounter.linePos(first.pos[0]).line,
        message: `not valid YAML: ${first.message.split('\n')[0]}`,
      }
    : null;
  return { doc, nodeLine, error };
}

/**
 * Parse the list. Throws CannotRun when it is missing or not YAML; the
 * result carries `lineOf(...keys)` for findings about the list itself.
 */
function loadRequirements(root) {
  let text;
  try {
    text = fs.readFileSync(path.join(root, REQUIREMENTS), 'utf8');
  } catch {
    throw new CannotRun(`${REQUIREMENTS} not found`);
  }
  const { doc, nodeLine, error } = parseYaml(text);
  if (error) throw new CannotRun(`${REQUIREMENTS}:${error.line}: ${error.message}`);
  const lineOf = (...keys) => {
    for (let depth = keys.length; depth > 0; depth -= 1) {
      const node = doc.getIn(keys.slice(0, depth), true);
      if (node && node.range) return nodeLine(node);
    }
    return 1;
  };
  return { data: doc.toJS() || {}, lineOf };
}

function checkField(type, value, root) {
  switch (type) {
    case 'string': {
      return typeof value === 'string' && value.trim() !== '' ? null : 'must be a non-empty string';
    }
    case 'optional-string': {
      return value === undefined || (typeof value === 'string' && value.trim() !== '') ? null : 'must be a non-empty string';
    }
    case 'kind': {
      return KINDS.includes(value) ? null : `must be one of ${KINDS.join(', ')}`;
    }
    case 'tiers': {
      return Array.isArray(value) && value.every((tier) => TIERS.includes(tier)) ? null : `must be a list of ${TIERS.join(', ')}`;
    }
    case 'workflows': {
      if (!Array.isArray(value) || value.length === 0) return 'must be a non-empty list';
      if (value.length === 1 && value[0] === 'all') return null;
      const unknown = value.filter((name) => typeof name !== 'string' || !fs.existsSync(path.join(root, 'src', `skf-${name}`)));
      return unknown.length === 0 ? null : `names no src/skf-<name> folder: ${unknown.join(', ')} (or use [all])`;
    }
    case 'minimum': {
      return value === null || (typeof value === 'string' && VERSION.test(value))
        ? null
        : 'must be null or a quoted version such as "3.11"';
    }
    case 'tested': {
      return Array.isArray(value) && value.every((version) => typeof version === 'string' && VERSION.test(version))
        ? null
        : 'must be a list of quoted versions such as ["3.11"] ([] when none is recorded)';
    }
    case 'command': {
      return Array.isArray(value) && value.length > 0 && value.every((part) => typeof part === 'string' && part !== '')
        ? null
        : 'must be a non-empty list of strings';
    }
    case 'url': {
      return typeof value === 'string' && /^https:\/\/\S+$/.test(value) ? null : 'must be an https URL';
    }
    default: {
      return null;
    }
  }
}

/** Findings for the list itself. The copy checks run only when there are none. */
function validateRequirements(root, requirements) {
  const { data, lineOf } = requirements;
  const findings = [];
  const add = (keys, message) => findings.push({ file: REQUIREMENTS, line: lineOf(...keys), message });
  if (data.schema_version !== 1) add(['schema_version'], 'schema_version must be 1');
  const tools = data.tools;
  if (!tools || typeof tools !== 'object' || Array.isArray(tools)) {
    add(['tools'], 'tools must be a mapping of tool keys to entries');
    return findings;
  }
  for (const key of Object.keys(data)) {
    if (key !== 'schema_version' && key !== 'tools') add([key], `unknown top-level key "${key}"`);
  }
  for (const key of REQUIRED_TOOLS) {
    if (!(key in tools)) add(['tools'], `tools.${key} is missing: the copy checks need it`);
  }
  for (const key of REQUIRED_MINIMUMS) {
    if (tools[key] && typeof tools[key] === 'object' && tools[key].minimum === null) {
      add(['tools', key, 'minimum'], `tools.${key}.minimum must be a version: the copy checks need it`);
    }
  }
  for (const [key, tool] of Object.entries(tools)) {
    if (!/^[a-z][a-z0-9_]*$/.test(key)) add(['tools', key], `tool key "${key}" must be lower case with underscores`);
    if (!tool || typeof tool !== 'object' || Array.isArray(tool)) {
      add(['tools', key], `tools.${key} must be a mapping`);
      continue;
    }
    for (const field of Object.keys(tool)) {
      if (!(field in TOOL_KEYS)) add(['tools', key, field], `tools.${key}: unknown key "${field}"`);
    }
    for (const [field, type] of Object.entries(TOOL_KEYS)) {
      if (!type.startsWith('optional') && !(field in tool)) {
        add(['tools', key], `tools.${key}.${field} is missing`);
        continue;
      }
      const problem = checkField(type, tool[field], root);
      if (problem) add(['tools', key, field], `tools.${key}.${field} ${problem}`);
    }
    if (tool.kind === 'tier' && Array.isArray(tool.tiers) && tool.tiers.length === 0) {
      add(['tools', key, 'tiers'], `tools.${key}.tiers: a tier tool names the tiers that need it`);
    }
    if ((tool.kind === 'tier' || tool.kind === 'optional') && tool.acknowledged_as === undefined) {
      add(['tools', key], `tools.${key}.acknowledged_as is missing: a ${tool.kind} tool has a README Acknowledgements row`);
    }
    const tested = Array.isArray(tool.tested) ? tool.tested.filter((version) => typeof version === 'string' && VERSION.test(version)) : [];
    const minimum = typeof tool.minimum === 'string' && VERSION.test(tool.minimum) ? tool.minimum : null;
    if (minimum && tested.length > 0 && tested.every((version) => compareVersions(minimum, version) > 0)) {
      add(['tools', key, 'minimum'], `tools.${key}.minimum ${minimum} is above every tested version (${tested.join(', ')})`);
    }
  }
  return findings;
}

function escapeCell(text) {
  return String(text).replaceAll('|', String.raw`\|`);
}

/** The prerequisites table, one row per tool in list order, then FIXED_ROWS. */
function renderTable(tools) {
  const rows = Object.values(tools).map((tool) => [
    tool.summary ? `\`${tool.name}\` (${tool.summary})` : `\`${tool.name}\``,
    tool.used_for,
    tool.minimum ?? 'none',
    tool.tested.length > 0 ? tool.tested.join(', ') : 'not recorded',
    `<${tool.install_url}>`,
  ]);
  const table = [TABLE_HEADER, ...rows, ...FIXED_ROWS].map((row) => row.map((cell) => escapeCell(cell)));
  const widths = TABLE_HEADER.map((_, column) => Math.max(3, ...table.map((row) => row[column].length)));
  const line = (row) => `| ${row.map((cell, column) => cell.padEnd(widths[column])).join(' | ')} |`;
  return [line(table[0]), `| ${widths.map((width) => '-'.repeat(width)).join(' | ')} |`, ...table.slice(1).map((row) => line(row))];
}

function renderBlock(tools) {
  return [START, GENERATED_NOTE, '', ...renderTable(tools), '', END];
}

/** The [start, end] line indexes (0-based) of the generated block, or null. */
function findBlock(lines) {
  const start = lines.findIndex((line) => line.trim() === START);
  const end = lines.findIndex((line, index) => index > start && line.trim() === END);
  return start === -1 || end === -1 ? null : [start, end];
}

function checkTable(root, tools) {
  const lines = readLines(root, PREREQUISITES_DOC);
  if (!lines) return [{ file: PREREQUISITES_DOC, line: 1, message: `${PREREQUISITES_DOC} not found` }];
  const block = findBlock(lines);
  if (!block) {
    return [{ file: PREREQUISITES_DOC, line: 1, message: `no ${START} ... ${END} block for the generated prerequisites table` }];
  }
  const current = lines.slice(block[0], block[1] + 1).join('\n');
  if (current === renderBlock(tools).join('\n')) return [];
  return [
    {
      file: PREREQUISITES_DOC,
      line: block[0] + 1,
      message: `the prerequisites table differs from ${REQUIREMENTS}: run node tools/tool-requirements.js --write (do not edit the table by hand)`,
    },
  ];
}

/** Rewrite the generated block. Returns 'written', 'unchanged' or a finding. */
function writeTable(root, tools) {
  const file = path.join(root, PREREQUISITES_DOC);
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    return { file: PREREQUISITES_DOC, line: 1, message: `${PREREQUISITES_DOC} not found` };
  }
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  const lines = text.split(/\r?\n/);
  const block = findBlock(lines);
  if (!block) {
    return { file: PREREQUISITES_DOC, line: 1, message: `no ${START} ... ${END} block to write the table into: add the two markers` };
  }
  const next = [...lines.slice(0, block[0]), ...renderBlock(tools), ...lines.slice(block[1] + 1)].join(eol);
  if (next === text) return 'unchanged';
  fs.writeFileSync(file, next);
  return 'written';
}

function listMarkdown(root, dir) {
  const out = [];
  const walk = (rel) => {
    let entries;
    try {
      entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const child = path.posix.join(rel, entry.name);
      if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') walk(child);
      else if (entry.isFile() && entry.name.endsWith('.md')) out.push(child);
    }
  };
  walk(dir);
  return out;
}

/** One regex per tool with a minimum, matching "<name> >= <version>" in prose. */
function proseMatchers(tools) {
  const matchers = [];
  for (const [key, tool] of Object.entries(tools)) {
    if (tool.minimum === null) continue;
    const names = PROSE_NAMES[key] || [tool.name];
    const alternatives = names.map((name) => escapeRegExp(name)).join('|');
    // The name, maybe in backticks or as a Markdown link, then >= or ≥.
    const regex = new RegExp(String.raw`\b(?:${alternatives})\`?(?:\]\([^)\s]*\))?\s*(?:>=|≥|&gt;=)\s*v?(\d+(?:\.\d+)*)`, 'g');
    matchers.push({ key, tool, regex });
  }
  return matchers;
}

function checkProse(root, tools) {
  const findings = [];
  const matchers = proseMatchers(tools);
  const files = ['README.md', 'CONTRIBUTING.md', ...listMarkdown(root, 'docs')];
  for (const file of Object.keys(REQUIRED_PROSE)) {
    if (!files.includes(file)) files.push(file);
  }
  for (const file of files) {
    const lines = readLines(root, file);
    if (!lines) {
      if (REQUIRED_PROSE[file]) findings.push({ file, line: 1, message: `${file} not found` });
      continue;
    }
    const block = file === PREREQUISITES_DOC ? findBlock(lines) : null;
    const seen = new Set();
    for (const [index, text] of lines.entries()) {
      if (block && index >= block[0] && index <= block[1]) continue;
      for (const { key, tool, regex } of matchers) {
        for (const match of text.matchAll(regex)) {
          seen.add(key);
          if (compareVersions(match[1], tool.minimum) !== 0) {
            findings.push({
              file,
              line: index + 1,
              message: `"${match[0].trim()}" says ${match[1]}, but the ${tool.name} minimum in ${REQUIREMENTS} is ${tool.minimum}`,
            });
          }
        }
      }
      if (file === 'README.md') {
        const badge = PYTHON_BADGE.exec(text);
        if (badge) {
          seen.add('python-badge');
          if (tools.python && compareVersions(badge[1], tools.python.minimum) !== 0) {
            findings.push({
              file,
              line: index + 1,
              message: `the Python badge says >=${badge[1]}, but the Python minimum in ${REQUIREMENTS} is ${tools.python.minimum}`,
            });
          }
        }
      }
    }
    for (const key of REQUIRED_PROSE[file] || []) {
      const tool = tools[key];
      if (!tool || tool.minimum === null || seen.has(key)) continue;
      findings.push({
        file,
        line: 1,
        message: `no copy of the ${tool.name} minimum: the install line must say "${(PROSE_NAMES[key] || [tool.name])[0]} >= ${tool.minimum}"`,
      });
    }
    if (file === 'README.md' && !seen.has('python-badge')) {
      findings.push({ file, line: 1, message: 'no Python version badge (img.shields.io/badge/python-%3E%3D<minimum>-...)' });
    }
  }
  return findings;
}

function lineIndex(lines, regex, from = 0) {
  for (let index = from; index < lines.length; index += 1) {
    if (regex.test(lines[index])) return index;
  }
  return -1;
}

function checkPackageJson(root, tools) {
  const file = 'package.json';
  const lines = readLines(root, file);
  let pkg;
  try {
    pkg = JSON.parse(lines.join('\n'));
  } catch {
    return [{ file, line: 1, message: 'package.json not found or not JSON' }];
  }
  const findings = [];
  const node = tools.node;
  const engines = pkg.engines && pkg.engines.node;
  const enginesLine = lineIndex(lines, /"node"\s*:/, Math.max(0, lineIndex(lines, /"engines"\s*:/))) + 1 || 1;
  const floor = /^>=\s*v?(\d+(?:\.\d+)*)$/.exec(String(engines || '').trim());
  if (!floor || compareVersions(floor[1], node.minimum) !== 0) {
    findings.push({
      file,
      line: enginesLine,
      message: `engines.node is ${JSON.stringify(engines ?? null)}, but the Node.js minimum in ${REQUIREMENTS} is ${node.minimum} (">=${node.minimum}.0.0")`,
    });
  }
  const script = (pkg.scripts && pkg.scripts['test:python']) || '';
  const scriptLine = lineIndex(lines, /"test:python"\s*:/) + 1 || 1;
  const pin = AST_GREP_PIN.exec(script);
  const astGrep = tools.ast_grep;
  if (!pin) {
    findings.push({ file, line: scriptLine, message: 'test:python pins no ast-grep-cli version (--with ast-grep-cli==<version>)' });
  } else if (!isTested(astGrep, pin[1])) {
    findings.push({
      file,
      line: scriptLine,
      message: `test:python pins ast-grep-cli==${pin[1]}, which is not an ast-grep tested version in ${REQUIREMENTS} (${listVersions(astGrep.tested)})`,
    });
  }
  return findings;
}

function checkNvmrc(root, tools) {
  const lines = readLines(root, '.nvmrc');
  if (!lines) return [{ file: '.nvmrc', line: 1, message: '.nvmrc not found' }];
  const value = lines[0].trim().replace(/^v/, '');
  if (VERSION.test(value) && isTested(tools.node, value)) return [];
  return [
    {
      file: '.nvmrc',
      line: 1,
      message: `.nvmrc is "${lines[0].trim()}", which is not a Node.js tested version in ${REQUIREMENTS} (${listVersions(tools.node.tested)})`,
    },
  ];
}

function listWorkflows(root) {
  try {
    return fs
      .readdirSync(path.join(root, WORKFLOWS_DIR))
      .filter((name) => /\.ya?ml$/.test(name))
      .sort()
      .map((name) => `${WORKFLOWS_DIR}/${name}`);
  } catch {
    return [];
  }
}

/**
 * The versions a parsed workflow gives `key` (node-version or python-version)
 * in the `with:` of its steps and jobs, each as { value, line }. A list or a
 * multi-line value gives one version per item. `${{ matrix.<name> }}` gives
 * the job's strategy.matrix values for <name>, from its list and its include
 * entries, at the lines they are written on; any other expression is not a
 * version and is skipped. An alias reads its anchor.
 */
function workflowValues(workflow, key) {
  const { doc, nodeLine } = workflow;
  const deref = (node) => (YAML.isAlias(node) ? node.resolve(doc) : node);
  const get = (node, name) => {
    const map = deref(node);
    return YAML.isMap(map) ? (deref(map.get(name, true)) ?? null) : null;
  };
  const items = (node) => {
    if (YAML.isSeq(node)) return node.items.flatMap((item) => items(deref(item)));
    if (!YAML.isScalar(node) || node.value === null) return [];
    return String(node.value)
      .split('\n')
      .map((text) => text.trim())
      .filter((text) => text !== '')
      .map((value) => ({ value, line: nodeLine(node) }));
  };
  const matrixItems = (job, name) => {
    const matrix = get(get(job, 'strategy'), 'matrix');
    const include = get(matrix, 'include');
    const entries = YAML.isSeq(include) ? include.items : [];
    return [...items(get(matrix, name)), ...entries.flatMap((entry) => items(get(entry, name)))];
  };
  const values = new Map();
  const jobs = get(doc.contents, 'jobs');
  for (const { value: job } of YAML.isMap(jobs) ? jobs.items : []) {
    const steps = get(job, 'steps');
    const blocks = [get(job, 'with'), ...(YAML.isSeq(steps) ? steps.items.map((step) => get(step, 'with')) : [])];
    for (const item of blocks.flatMap((block) => items(get(block, key)))) {
      const matrixKey = MATRIX_VALUE.exec(item.value);
      for (const found of matrixKey ? matrixItems(job, matrixKey[1]) : [item]) {
        if (!found.value.includes('${{')) values.set(`${found.line}\n${found.value}`, found);
      }
    }
  }
  return [...values.values()];
}

function checkWorkflows(root, tools) {
  const findings = [];
  const { node, python } = tools;
  let smokeHasNode = false;
  let minimumRun = false;
  let firstPython = null;
  for (const file of listWorkflows(root)) {
    const workflow = parseYaml((readLines(root, file) || []).join('\n'));
    if (workflow.error) {
      findings.push({
        file,
        line: workflow.error.line,
        message: `${workflow.error.message} (its node-version and python-version are not checked)`,
      });
      continue;
    }
    for (const { value, line } of workflowValues(workflow, 'node-version')) {
      if (file === INSTALL_SMOKE) {
        smokeHasNode = true;
        if (compareVersions(value, node.minimum) !== 0) {
          findings.push({
            file,
            line,
            message: `node-version is ${value}, but the install smoke test runs the Node.js minimum in ${REQUIREMENTS} (${node.minimum})`,
          });
        }
      } else if (!VERSION.test(value) || !isTested(node, value)) {
        findings.push({
          file,
          line,
          message: `node-version ${value} is not a Node.js tested version in ${REQUIREMENTS} (${listVersions(node.tested)})`,
        });
      }
    }
    for (const { value, line } of workflowValues(workflow, 'python-version')) {
      firstPython ??= { file, line };
      if (VERSION.test(value) && compareVersions(value, python.minimum) === 0) minimumRun = true;
      if (!VERSION.test(value) || !isTested(python, value)) {
        findings.push({
          file,
          line,
          message: `python-version ${value} is not a Python tested version in ${REQUIREMENTS} (${listVersions(python.tested)})`,
        });
      }
    }
  }
  if (!smokeHasNode) {
    findings.push({
      file: INSTALL_SMOKE,
      line: 1,
      message: `no node-version: the install smoke test runs the Node.js minimum (${node.minimum})`,
    });
  }
  if (!minimumRun) {
    const where = firstPython || { file: WORKFLOWS_DIR, line: 1 };
    findings.push({
      ...where,
      message: `no workflow runs Python ${python.minimum}, the minimum in ${REQUIREMENTS}: the minimum needs a CI run`,
    });
  }
  return findings;
}

function checkAcknowledgements(root, tools) {
  const file = 'README.md';
  const lines = readLines(root, file) || [];
  const heading = lineIndex(lines, /^##\s+Acknowledgements\s*$/);
  if (heading === -1) return [{ file, line: 1, message: 'no "## Acknowledgements" section' }];
  const names = new Set();
  for (let index = heading + 1; index < lines.length && !/^#{1,2}\s/.test(lines[index]); index += 1) {
    const cell = /^\|\s*\[([^\]]+)\]\(/.exec(lines[index]);
    if (cell) names.add(cell[1].trim());
  }
  const findings = [];
  for (const tool of Object.values(tools)) {
    if (tool.acknowledged_as === undefined || names.has(tool.acknowledged_as)) continue;
    findings.push({
      file,
      line: heading + 1,
      message: `the Acknowledgements table has no row for ${tool.name} (a row whose link text is "${tool.acknowledged_as}", its acknowledged_as)`,
    });
  }
  return findings;
}

function listPython(root, dir) {
  const out = [];
  const walk = (rel) => {
    let entries;
    try {
      entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const child = path.posix.join(rel, entry.name);
      if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== '__pycache__') walk(child);
      else if (entry.isFile() && entry.name.endsWith('.py')) out.push(child);
    }
  };
  walk(dir);
  return out;
}

/**
 * The requires-python line of a PEP 723 `# /// script` block, or null. A
 * docstring that quotes a header is outside the block and is not read.
 */
function readRequiresPython(lines) {
  const start = lines.findIndex((line) => line.trim() === '# /// script');
  if (start === -1) return null;
  for (let index = start + 1; index < lines.length && lines[index].startsWith('#'); index += 1) {
    if (lines[index].trim() === '# ///') break;
    const match = /^#\s*requires-python\s*=\s*["']([^"']*)["']/.exec(lines[index]);
    if (match) return { spec: match[1], line: index + 1 };
  }
  return null;
}

/** The lower bound of a requires-python specifier (">=3.10,<4" gives "3.10"), or null. */
function lowerBound(spec) {
  const match = /(?:^|,)\s*>=\s*(\d+(?:\.\d+)*)\s*(?:,|$)/.exec(spec);
  return match ? match[1] : null;
}

function checkRequiresPython(root, tools) {
  const findings = [];
  const minimum = tools.python.minimum;
  for (const file of listPython(root, 'src')) {
    const header = readRequiresPython(readLines(root, file) || []);
    if (!header) continue;
    const floor = lowerBound(header.spec);
    if (floor && compareVersions(floor, minimum) >= 0) continue;
    findings.push({
      file,
      line: header.line,
      message: `requires-python = "${header.spec}" is below the Python minimum in ${REQUIREMENTS}: declare ">=${minimum}"`,
    });
  }
  return findings;
}

/**
 * Every finding for the checkout at `root`. `options.requiresPython`
 * overrides REQUIRES_PYTHON_CHECK (its tests turn it on).
 */
function checkAll(root, requirements, options = {}) {
  const invalid = validateRequirements(root, requirements);
  if (invalid.length > 0) return invalid;
  const tools = requirements.data.tools;
  const findings = [
    ...checkTable(root, tools),
    ...checkProse(root, tools),
    ...checkPackageJson(root, tools),
    ...checkNvmrc(root, tools),
    ...checkWorkflows(root, tools),
    ...checkAcknowledgements(root, tools),
  ];
  if (options.requiresPython ?? REQUIRES_PYTHON_CHECK) findings.push(...checkRequiresPython(root, tools));
  return findings;
}

function main(argv = process.argv.slice(2), env = process.env) {
  const write = argv.includes('--write');
  if (!write && !argv.includes('--check')) {
    console.error('usage: node tools/tool-requirements.js --check | --write [--root <dir>]');
    return 2;
  }
  const root = path.resolve(argValue(argv, '--root') || path.join(__dirname, '..'));
  const annotate = env.GITHUB_ACTIONS === 'true';

  let requirements;
  try {
    requirements = loadRequirements(root);
  } catch (error) {
    if (!(error instanceof CannotRun)) throw error;
    console.error(`error: ${error.message}`);
    return 2;
  }

  const findings = [];
  if (write) {
    const invalid = validateRequirements(root, requirements);
    const result = invalid.length > 0 ? null : writeTable(root, requirements.data.tools);
    if (result === 'written') console.log(`Wrote the prerequisites table in ${PREREQUISITES_DOC}.`);
    else if (result === 'unchanged') console.log(`The prerequisites table in ${PREREQUISITES_DOC} is up to date.`);
    else if (result) findings.push(result);
  }
  findings.push(...checkAll(root, requirements));

  for (const finding of findings) {
    const file = toPosix(finding.file);
    console.log(`${file}:${finding.line}: ${finding.message}`);
    if (annotate) console.log(`::error file=${file},line=${finding.line}::${finding.message}`);
  }
  if (findings.length === 0) {
    console.log(`Tool versions agree with ${REQUIREMENTS}.`);
    return 0;
  }
  console.log(`\n${findings.length} finding(s): make each copy match ${REQUIREMENTS}, or change the list and run --write.`);
  return 1;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  REQUIREMENTS,
  PREREQUISITES_DOC,
  START,
  END,
  compareVersions,
  lowerBound,
  readRequiresPython,
  loadRequirements,
  validateRequirements,
  renderTable,
  renderBlock,
  checkAll,
  main,
};
