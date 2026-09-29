/**
 * Covered-Surface Diff
 *
 * Compares the workflow contract surfaces of two trees, by default the last
 * stable release tag and the working tree, and sorts every difference into
 * one of three groups. tools/changes.js uses the result to set the minimum
 * version bump of a release and to refuse a release whose change fragments
 * do not name a removal.
 *
 * What it reads, each item keyed by the workflow that owns it:
 * - Schema enum values, properties and required fields in the JSON schemas
 *   directly under src/shared/scripts/schemas/, keyed by file and JSON
 *   pointer (the owning workflow is only a label, so adding or removing a
 *   workflow folder never moves a schema item)
 * - Ferris menu codes: the Code column of the Capabilities table in
 *   src/skf-forger/SKILL.md
 * - Pipeline aliases: the Alias table in
 *   src/shared/references/pipeline-contracts.md. An alias named on a
 *   "Deprecated alias:" line still counts as present.
 * - Flags: every --flag or -X that opens a backticked span, and every bare
 *   --flag, in the Flags, Inputs, Headless inputs, Headless flag and
 *   Overrides rows of each workflow's SKILL.md (src/skf-<name>/SKILL.md),
 *   with the text around it. Where each workflow's Markdown (SKILL.md,
 *   references/ at any depth, templates/, assets/) still names a flag is
 *   read too: a --flag as a whole token anywhere, a -X when it opens a
 *   backticked span. Three kinds of mention do not count, because they do
 *   not show the workflow still takes the flag: one in a command that runs
 *   another program (a code span or fenced line that starts with uv, git,
 *   npm, gh and the like, or with a {...Helper} path), one in a span that
 *   hands the flag a {variable} (`--require-tier "{require_tier}"`, an
 *   argument built for a helper), and one in a sentence that says renamed,
 *   removed, deprecated, no longer, formerly or replaced (a migration note).
 *   A flag that leaves every flag row is removed when none of those files
 *   names it any more, and also when another flag, one the workflow never
 *   named before, enters its rows in the same diff: that is a possible
 *   rename, so it stays hard.
 * - Exit codes: the numbered rows of the Code (or Exit code) tables in each
 *   workflow's SKILL.md and references/*.md, with their meaning
 * - Preference keys (src/forger/preferences.yaml) and install config keys
 *   (src/module.yaml)
 * - halt_reason and error.phase values written in the Markdown under src/
 *
 * Groups:
 * - hard: a removed schema enum value or property, menu code, pipeline alias
 *   or flag (a flag no Markdown file of its workflow names any more, or a
 *   possible rename). The release needs a major bump, and a breaking change
 *   fragment must name the item.
 * - additive: one of those surfaces added, or a new preference key or exit
 *   code. The release needs at least a minor bump. A flag that enters a flag
 *   row is added even when the workflow's Markdown named it before: the row
 *   puts it under the contract. The reverse is not a removal (see review).
 * - review: a flag that left every flag row while its workflow's Markdown
 *   still names it (listed first, with the files: it may be a silent
 *   breaking change), halt_reason and error.phase values added or removed, a
 *   flag whose text changed, an exit code removed or given another meaning,
 *   a required field added or removed, a pipeline alias deprecated, an
 *   install config key added, a preference or config key removed, a schema
 *   enum value or property that moved to another place in the same file (an
 *   enum moved into $defs behind a $ref, properties wrapped in allOf).
 *   Listed for a person to judge, never a failure. Exit codes and required
 *   fields stay out of the hard group until the history shows they can be
 *   read without false hits.
 *
 * Usage:
 *   node tools/covered-surfaces.js                       # last stable tag vs the working tree
 *   node tools/covered-surfaces.js --base v2.2.0 --head HEAD
 *   node tools/covered-surfaces.js --json                # findings as JSON
 *   node tools/covered-surfaces.js --root <dir>          # another checkout (the tests use this)
 *
 * The last stable tag is `git describe --tags --abbrev=0 --match 'v[0-9]*'
 * --exclude '*-*'`, as in release.yaml's "Get new version and previous tag"
 * step; keep the two in step. Exit codes: 0 when the report is printed
 * (findings never fail this tool); 2 when a ref does not resolve, or when no
 * stable tag is found in CI. A local run with no stable tag says so and
 * exits 0.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const SCHEMA_FILE = /^src\/shared\/scripts\/schemas\/[^/]+\.json$/;
const FORGER_SKILL = 'src/skf-forger/SKILL.md';
const PIPELINE_CONTRACTS = 'src/shared/references/pipeline-contracts.md';
const PREFERENCES = 'src/forger/preferences.yaml';
const MODULE_CONFIG = 'src/module.yaml';
const WORKFLOW_SKILL = /^src\/(skf-[^/]+)\/SKILL\.md$/;
const WORKFLOW_REFERENCE = /^src\/(skf-[^/]+)\/references\/[^/]+\.md$/;
const WORKFLOW_MARKDOWN = /^src\/(skf-[^/]+)\/.+\.md$/;
const EM_DASH = String.fromCodePoint(0x20_14);

/**
 * How each kind of item is grouped when it is removed, added or changed.
 * A missing entry means that change is not reported.
 */
const KINDS = {
  'schema-enum': { label: 'schema enum value', removed: 'hard', added: 'additive', moved: 'review' },
  'schema-property': { label: 'schema property', removed: 'hard', added: 'additive', moved: 'review' },
  'menu-code': { label: 'Ferris menu code', removed: 'hard', added: 'additive' },
  'pipeline-alias': { label: 'pipeline alias', removed: 'hard', added: 'additive', changed: 'review' },
  flag: {
    label: 'flag',
    removed: 'hard',
    'possible-rename': 'hard',
    added: 'additive',
    changed: 'review',
    'moved-out': 'review',
  },
  'exit-code': { label: 'exit code', removed: 'review', added: 'additive', changed: 'review' },
  preference: { label: 'preference key', removed: 'review', added: 'additive' },
  config: { label: 'install config key', removed: 'review', added: 'review' },
  'schema-required': { label: 'required field', removed: 'review', added: 'review' },
  'halt-reason': { label: 'halt_reason value', removed: 'review', added: 'review' },
  'error-phase': { label: 'error.phase value', removed: 'review', added: 'review' },
};
const GROUPS = ['hard', 'additive', 'review'];
const KIND_ORDER = Object.keys(KINDS);

// --- Reading a tree ---

function makeGit(root) {
  return (args, options = {}) =>
    execFileSync('git', ['-c', 'core.quotePath=false', ...args], {
      cwd: root,
      encoding: 'utf8',
      maxBuffer: 256 * 1024 * 1024,
      stdio: ['pipe', 'pipe', 'pipe'],
      ...options,
    });
}

/** The commit a ref names, or null when it does not resolve. */
function resolveCommit(root, ref) {
  try {
    return makeGit(root)(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`]).trim() || null;
  } catch {
    return null;
  }
}

/**
 * The newest version tag (v<digit>...) with no prerelease suffix reachable
 * from HEAD, or null. A tag that is not a version, such as `stable`, is never
 * taken as the base.
 */
function lastStableTag(root) {
  try {
    return makeGit(root)(['describe', '--tags', '--abbrev=0', '--match', 'v[0-9]*', '--exclude', '*-*']).trim() || null;
  } catch {
    return null;
  }
}

/** True for the files the extractors read. */
function isSurfaceFile(file) {
  if (!file.startsWith('src/')) return false;
  return file.endsWith('.md') || SCHEMA_FILE.test(file) || file === PREFERENCES || file === MODULE_CONFIG;
}

function normalizeNewlines(text) {
  return text === null || text === undefined ? null : text.replaceAll('\r\n', '\n');
}

/** Split `git cat-file --batch` output into the contents of each requested object. */
function parseCatFileBatch(buffer) {
  const contents = [];
  let pos = 0;
  while (pos < buffer.length) {
    const eol = buffer.indexOf(0x0a, pos);
    if (eol === -1) break;
    const header = buffer.toString('utf8', pos, eol).split(' ');
    if (header[1] === 'missing') {
      contents.push(null);
      pos = eol + 1;
      continue;
    }
    const size = Number(header[2]);
    contents.push(buffer.toString('utf8', eol + 1, eol + 1 + size));
    pos = eol + 1 + size + 1;
  }
  return contents;
}

/** A tree read from a git ref: every surface file is read in one git call. */
function refTree(root, ref) {
  const commit = resolveCommit(root, ref);
  if (!commit) throw new Error(`ref ${ref} not found`);
  const git = makeGit(root);
  const blobs = new Map();
  for (const entry of git(['ls-tree', '-r', '-z', '--full-tree', commit, '--', 'src']).split('\0')) {
    const tab = entry.indexOf('\t');
    if (tab === -1) continue;
    const [, type, sha] = entry.slice(0, tab).split(' ');
    if (type === 'blob') blobs.set(entry.slice(tab + 1), sha);
  }
  const wanted = [...blobs.keys()].filter((file) => isSurfaceFile(file));
  const contents = new Map();
  if (wanted.length > 0) {
    const output = execFileSync('git', ['cat-file', '--batch'], {
      cwd: root,
      input: wanted.map((file) => blobs.get(file)).join('\n') + '\n',
      maxBuffer: 512 * 1024 * 1024,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    for (const [index, text] of parseCatFileBatch(output).entries()) contents.set(wanted[index], normalizeNewlines(text));
  }
  return { label: ref, files: [...blobs.keys()].sort(), read: (file) => contents.get(file) ?? null };
}

/** The working tree of a checkout, read from disk. */
function workingTree(root) {
  const files = [];
  const walk = (dir, rel) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__pycache__') continue;
      const childRel = `${rel}/${entry.name}`;
      if (entry.isDirectory()) walk(path.join(dir, entry.name), childRel);
      else if (entry.isFile()) files.push(childRel);
    }
  };
  walk(path.join(root, 'src'), 'src');
  files.sort();
  // Several extractors read each Markdown file: read it from disk once.
  const cache = new Map();
  const readFromDisk = (file) => {
    try {
      return normalizeNewlines(fs.readFileSync(path.join(root, file), 'utf8'));
    } catch {
      return null;
    }
  };
  return {
    label: 'working tree',
    files,
    read: (file) => {
      if (!cache.has(file)) cache.set(file, readFromDisk(file));
      return cache.get(file);
    },
  };
}

/** A tree for a ref, or the working tree when the ref is null. */
function openTree(root, ref) {
  return ref ? refTree(root, ref) : workingTree(root);
}

// --- Extractors ---

function workflowOf(file) {
  const match = /^src\/(skf-[^/]+)\//.exec(file);
  return match ? match[1] : 'shared';
}

/** The workflow a schema belongs to: skf-setup-result-envelope.v1.json is skf-setup's. */
function schemaWorkflow(file, workflows) {
  const stem = path.posix
    .basename(file)
    .replace(/\.v\d+\.json$/, '')
    .replace(/\.json$/, '')
    .replace(/-result-envelope$/, '');
  if (workflows.includes(stem)) return stem;
  const matches = workflows.filter((name) => name.startsWith(`${stem}-`));
  return matches.length === 1 ? matches[0] : 'shared';
}

function pointerToken(key) {
  return String(key).replaceAll('~', '~0').replaceAll('/', '~1');
}

function schemaItems(tree, workflows, add) {
  const files = [];
  for (const file of tree.files.filter((name) => SCHEMA_FILE.test(name))) {
    let json;
    try {
      json = JSON.parse(tree.read(file));
    } catch {
      continue;
    }
    files.push(file);
    const workflow = schemaWorkflow(file, workflows);
    const walk = (node, pointer) => {
      if (Array.isArray(node)) {
        for (const [index, child] of node.entries()) walk(child, `${pointer}/${index}`);
        return;
      }
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node.enum)) {
        for (const value of node.enum) {
          add({ kind: 'schema-enum', workflow, token: String(value), file, where: `${file}#${pointer}`, id: JSON.stringify(value) });
        }
      }
      if (node.properties && typeof node.properties === 'object' && !Array.isArray(node.properties)) {
        for (const name of Object.keys(node.properties)) {
          add({ kind: 'schema-property', workflow, token: name, file, where: `${file}#${pointer}/properties/${pointerToken(name)}` });
        }
      }
      if (Array.isArray(node.required)) {
        for (const name of node.required) {
          add({ kind: 'schema-required', workflow, token: String(name), file, where: `${file}#${pointer}` });
        }
      }
      for (const [key, child] of Object.entries(node)) {
        if (key !== 'enum' && key !== 'required') walk(child, `${pointer}/${pointerToken(key)}`);
      }
    };
    walk(json, '');
  }
  return files;
}

function cells(row) {
  return row.split('|').slice(1, -1);
}

function isSeparatorRow(row) {
  return /^\|[\s:|-]+$/.test(row.trim());
}

/**
 * Rows of every Markdown table whose header row matches `header`.
 *
 * @returns {string[][]} the cells of each body row
 */
function tableRows(text, header) {
  const rows = [];
  let inTable = false;
  for (const line of (text || '').split('\n')) {
    if (!line.trim().startsWith('|')) {
      inTable = false;
      continue;
    }
    if (!inTable) {
      inTable = header.test(line);
      continue;
    }
    if (!isSeparatorRow(line)) rows.push(cells(line.trim()));
  }
  return rows;
}

function menuItems(tree, add) {
  const text = tree.read(FORGER_SKILL);
  if (text === null) return;
  const capabilities = text.split(/^## Capabilities\s*$/m)[1];
  if (capabilities === undefined) return;
  const section = capabilities.split(/^## /m)[0];
  for (const row of tableRows(section, /^\|\s*#\s*\|\s*Code\s*\|/)) {
    const code = (row[1] || '').replaceAll('`', '').trim();
    if (/^[A-Z]{2,3}$/.test(code)) add({ kind: 'menu-code', workflow: 'skf-forger', token: code, where: FORGER_SKILL });
  }
}

function aliasItems(tree, add) {
  const text = tree.read(PIPELINE_CONTRACTS);
  if (text === null) return;
  const aliases = new Map();
  for (const row of tableRows(text, /^\|\s*Alias\s*\|/)) {
    const alias = (row[0] || '').replaceAll('`', '').trim();
    if (/^[a-z][a-z0-9-]*$/.test(alias)) aliases.set(alias, 'active');
  }
  for (const match of text.matchAll(/(?:\*\*)?Deprecated alias(?:es)?:(?:\*\*)?\s*((?:`[\w-]+`(?:\s*(?:,|and|, and)\s*)?)+)/g)) {
    for (const name of match[1].matchAll(/`([\w-]+)`/g)) if (!aliases.has(name[1])) aliases.set(name[1], 'deprecated');
  }
  for (const [alias, state] of aliases) {
    add({ kind: 'pipeline-alias', workflow: 'skf-forger', token: alias, where: PIPELINE_CONTRACTS, detail: state });
  }
}

/** Lower-cased text with punctuation and spacing flattened, so a reflow is not a change. */
function normalizeText(text) {
  return text
    .toLowerCase()
    .replaceAll(EM_DASH, ' ')
    .replaceAll(/[\s:;,.()|\\`]+/g, ' ')
    .trim();
}

const FLAG_IN_BACKTICKS = /`((--[a-z][a-z0-9-]*|-[A-Za-z])(?![\w-])[^`]*)`/g;
// A long flag written without backticks, such as `--batch [optional]` in
// skf-create-skill's Inputs row. Short flags are only read in backticks: a
// bare "-X" is too easy to find in prose.
const BARE_LONG_FLAG = /(?<![\w`-])(--[a-z][a-z0-9-]*)(?![\w-])/g;
// The rows of a SKILL.md table that list a workflow's flags.
const FLAG_ROW = /^\|\s*\*\*(Flags|Inputs|Headless inputs|Headless flag|Overrides)\*\*\s*\|/;

/**
 * The flags of one flag row, each with the text that follows its mentions up
 * to the next flag. A backticked span counts when a flag opens it; a flag
 * inside a span that starts with other text (`campaign resume [--from=<x>]`)
 * is part of that text, not a flag of its own.
 *
 * @returns {Map<string, string>} flag -> normalized text
 */
function flagsInRow(row) {
  const flags = new Map();
  const matches = [...row.matchAll(FLAG_IN_BACKTICKS)].map((match) => ({
    index: match.index,
    length: match[0].length,
    flag: match[2],
    text: match[1],
  }));
  const outsideSpans = row.replaceAll(/`[^`]*`/g, (span) => ' '.repeat(span.length));
  for (const match of outsideSpans.matchAll(BARE_LONG_FLAG)) {
    matches.push({ index: match.index, length: match[0].length, flag: match[1], text: match[1] });
  }
  matches.sort((a, b) => a.index - b.index);
  for (const [index, match] of matches.entries()) {
    const end = index + 1 < matches.length ? matches[index + 1].index : row.length;
    const following = row.slice(match.index + match.length, end);
    const text = normalizeText(`${match.text} ${following}`);
    flags.set(match.flag, flags.has(match.flag) ? `${flags.get(match.flag)} ${text}` : text);
  }
  return flags;
}

function flagItems(tree, add) {
  const skillFiles = [];
  for (const file of tree.files) {
    const match = WORKFLOW_SKILL.exec(file);
    if (!match) continue;
    const text = tree.read(file);
    if (text === null) continue;
    skillFiles.push(file);
    const flags = new Map();
    for (const line of text.split('\n')) {
      if (!FLAG_ROW.test(line)) continue;
      for (const [flag, description] of flagsInRow(line)) {
        flags.set(flag, flags.has(flag) ? `${flags.get(flag)} ${description}` : description);
      }
    }
    for (const [flag, description] of flags) add({ kind: 'flag', workflow: match[1], token: flag, where: file, detail: description });
  }
  return skillFiles;
}

// A long flag named as a whole token, in backticks or not: `--brief <file>`,
// --from=<skill>, `campaign resume [--from=<skill>]`. --brief-file is another flag.
const LONG_FLAG_TOKEN = /(?<![\w-])(--[a-z][a-z0-9-]*)(?![\w-])/g;
// Backticked spans on one line, paired from the left, so the closing backtick
// of one span never opens the next. A short flag counts only when it opens a
// span, as in a flag row: the -H of `curl -H x` belongs to curl.
const BACKTICK_SPAN = /`([^`\n]*)`/g;
const SHORT_FLAG_START = /^(-[A-Za-z])(?![\w-])/;
const FENCE = /^\s*(```|~~~)/;
// A command that runs another program: its flags are that program's, as in
// `uv run {detectToolsHelper} --require-tier "{require_tier}"` or
// `git checkout --force`. `/skf-setup --quiet` runs the workflow itself.
const COMMAND =
  /^\s*(?:\$\s+)?(?:(?:uv|uvx|python3?|py|node|npx|npm|pnpm|yarn|bun|git|gh|bash|sh|curl|jq|ast-grep|sg|qmd|ccc|tessl|docker|make|pip3?|pipx|cargo)(?=\s|$)|\{\w+(?:Helper|Script)\})/;
// A flag handed a {variable}: `--require-tier "{require_tier}"`, an argument
// the workflow builds for a helper. The workflow's own flags are written with
// <placeholders>, as in `--require-tier=<Quick|Forge>`.
const PASSED_FLAG = /^\s*--[a-z][a-z0-9-]*(?:\s+|=)["']?\{/;
// A sentence that records a removal or a rename: "`--quiet` was renamed to
// `--silent`." It names a flag the workflow no longer takes.
const REMOVAL_NOTE = /(?<![\w-])(?:renamed|removed|deprecated|no longer|formerly|replaced)(?![\w-])/i;
const SENTENCE_BREAK = /(?<=[.!?])\s+|\s\|\s/;

function flagKey(workflow, flag) {
  return `${workflow} ${flag}`;
}

/**
 * The text of one Markdown file whose flags show the workflow takes them:
 * commands that run another program, flags handed a {variable} and
 * sentences that record a removal or a rename are left out.
 */
function mentionText(text) {
  const kept = [];
  let fenced = false;
  let continued = false;
  const blankCommands = (line) =>
    line.replaceAll(BACKTICK_SPAN, (span, inner) => (COMMAND.test(inner) || PASSED_FLAG.test(inner) ? ' ' : span));
  for (const line of text.split('\n')) {
    if (FENCE.test(line)) {
      fenced = !fenced;
      continued = false;
      continue;
    }
    if (fenced) {
      // A command line of a fenced block, with the lines a trailing \ continues it onto.
      const command = continued || COMMAND.test(line) || /\buv run\b/.test(line);
      continued = command && /\\\s*$/.test(line);
      if (!command) kept.push(line);
      continue;
    }
    kept.push(
      blankCommands(line)
        .split(SENTENCE_BREAK)
        .filter((sentence) => !REMOVAL_NOTE.test(sentence))
        .join(' '),
    );
  }
  return kept.join('\n');
}

/**
 * Where each workflow's Markdown names each flag, so that a flag whose row is
 * deleted while the workflow still documents it (in a step table, a reference
 * file) is not taken for a removal.
 *
 * @returns {Map<string, string[]>} "workflow flag" -> the files that name it, sorted
 */
function flagMentions(tree) {
  const mentions = new Map();
  const note = (workflow, flag, file) => {
    const key = flagKey(workflow, flag);
    if (!mentions.has(key)) mentions.set(key, []);
    const files = mentions.get(key);
    if (files.at(-1) !== file) files.push(file);
  };
  for (const file of tree.files) {
    const match = WORKFLOW_MARKDOWN.exec(file);
    if (!match) continue;
    const text = tree.read(file);
    if (!text) continue;
    const counted = mentionText(text);
    for (const found of counted.matchAll(LONG_FLAG_TOKEN)) note(match[1], found[1], file);
    for (const span of counted.matchAll(BACKTICK_SPAN)) {
      const short = SHORT_FLAG_START.exec(span[1]);
      if (short) note(match[1], short[1], file);
    }
  }
  return mentions;
}

function exitCodeItems(tree, add) {
  const codes = new Map();
  for (const file of tree.files) {
    const match = WORKFLOW_SKILL.exec(file) || WORKFLOW_REFERENCE.exec(file);
    if (!match) continue;
    const workflow = match[1];
    for (const row of tableRows(tree.read(file), /^\|\s*(Exit code|Exit|Code)\s*\|/i)) {
      const code = /^\s*`?(\d+)`?\s*$/.exec(row[0] || '');
      if (!code) continue;
      const key = `${workflow} ${code[1]}`;
      if (!codes.has(key)) codes.set(key, { workflow, code: code[1], meanings: new Set(), files: new Set() });
      codes.get(key).meanings.add(normalizeText(row[1] || ''));
      codes.get(key).files.add(file);
    }
  }
  for (const { workflow, code, meanings, files } of codes.values()) {
    add({ kind: 'exit-code', workflow, token: code, where: [...files].sort().join(', '), detail: [...meanings].sort().join(' / ') });
  }
}

const HALT_REASON = /halt_reason[`"]?\s*:?\s*[`"]([a-z0-9][a-z0-9-]*)[`"]/g;
const ERROR_PHASE = /phase[`"]?\s*:?\s*[`"]([a-z0-9]+(?: [a-z0-9]+)*:[a-z0-9][a-z0-9-]*)[`"]/g;

function haltItems(tree, add) {
  for (const file of tree.files) {
    if (!file.endsWith('.md')) continue;
    const text = tree.read(file);
    if (!text || (!text.includes('halt_reason') && !text.includes('phase'))) continue;
    const workflow = workflowOf(file);
    for (const match of text.matchAll(HALT_REASON)) add({ kind: 'halt-reason', workflow, token: match[1] });
    for (const match of text.matchAll(ERROR_PHASE)) add({ kind: 'error-phase', workflow, token: match[1] });
  }
}

function keyItems(tree, add) {
  for (const match of (tree.read(PREFERENCES) || '').matchAll(/^([a-z_][a-z0-9_]*):/gm)) {
    add({ kind: 'preference', workflow: 'preferences', token: match[1], where: PREFERENCES });
  }
  for (const match of (tree.read(MODULE_CONFIG) || '').matchAll(/^([a-z_][a-z0-9_]*):\s*$/gm)) {
    add({ kind: 'config', workflow: 'module config', token: match[1], where: MODULE_CONFIG });
  }
}

/**
 * Every covered item of one tree.
 *
 * @returns {{items: Map<string, object>, skillFiles: string[], schemaFiles: string[], workflows: string[],
 *   flagMentions: Map<string, string[]>}}
 */
function extractSurfaces(tree) {
  const items = new Map();
  const add = (item) => {
    // A schema item is keyed by file#pointer and value alone: its workflow is
    // worked out from the workflow folders in the tree, so adding one such as
    // skf-update-stack-skill would otherwise re-key every item of an
    // unchanged skf-update schema and report each as removed.
    const owner = item.kind.startsWith('schema-') ? item.where : item.workflow;
    const key = [item.kind, owner, item.token, item.id || ''].join('|');
    if (!items.has(key)) items.set(key, { key, where: '', detail: '', ...item });
  };
  const workflows = tree.files
    .map((file) => WORKFLOW_SKILL.exec(file))
    .filter(Boolean)
    .map((match) => match[1]);
  const schemaFiles = schemaItems(tree, workflows, add);
  menuItems(tree, add);
  aliasItems(tree, add);
  const skillFiles = flagItems(tree, add);
  exitCodeItems(tree, add);
  haltItems(tree, add);
  keyItems(tree, add);
  return { items, skillFiles, schemaFiles, workflows, flagMentions: flagMentions(tree) };
}

// --- Diff ---

/** "a, b, c and 2 more files": the first few files of a list. */
function fileList(files, shown = 3) {
  if (files.length <= shown) return files.join(', ');
  const more = files.length - shown;
  return `${files.slice(0, shown).join(', ')} and ${more} more file${more === 1 ? '' : 's'}`;
}

function describe(item, change, before) {
  const kind = KINDS[item.kind];
  if (change === 'moved-out') {
    return (
      `${item.workflow}: ${kind.label} \`${item.token}\` left every flag row but is still named in ${fileList(before)}: ` +
      'if the workflow no longer accepts it, add a breaking fragment that names it'
    );
  }
  if (change === 'possible-rename') {
    const successors = before.successors.map((token) => `\`${token}\``).join(', ');
    return (
      `${item.workflow}: ${kind.label} \`${item.token}\` left every flag row as ${successors} entered one, a possible rename ` +
      `(still named in ${fileList(before.still)}; if the workflow still accepts \`${item.token}\`, put it back in a flag row)`
    );
  }
  let text = `${item.workflow}: ${kind.label} \`${item.token}\` ${change}`;
  if (change === 'changed' && item.kind === 'pipeline-alias')
    text = `${item.workflow}: ${kind.label} \`${item.token}\` is now ${item.detail}`;
  if (change === 'changed' && item.kind === 'flag') text = `${item.workflow}: ${kind.label} \`${item.token}\` text changed`;
  if (change === 'changed' && item.kind === 'exit-code') {
    text = `${item.workflow}: ${kind.label} \`${item.token}\` meaning changed from "${before}" to "${item.detail}"`;
  }
  if (change === 'added' && item.kind === 'exit-code') text += ` (${item.detail})`;
  if (change === 'removed' && item.kind === 'exit-code') text += ` (was ${item.detail})`;
  if (change === 'moved') return `${text} from ${before} to #${item.where.slice(item.where.indexOf('#') + 1)}`;
  if (item.where && item.kind.startsWith('schema-')) text += ` (${item.where})`;
  return text;
}

/** Same kind, file, value: an item that may have moved to another pointer. */
function moveKey(item) {
  return [item.kind, item.file, item.token, item.id || ''].join('|');
}

/**
 * Pair each removed schema item with an added one of the same kind and value
 * in the same file: the schema was restructured (an enum moved into $defs
 * behind a $ref, properties wrapped in allOf) and nothing was removed. A
 * value that disappears from one place while it stays at a place it already
 * had is still a removal.
 *
 * @returns {{moves: {from: object, to: object}[], removed: object[], added: object[]}}
 */
function pairMoves(removed, added) {
  const pool = new Map();
  for (const item of added) {
    if (!KINDS[item.kind].moved) continue;
    const key = moveKey(item);
    if (!pool.has(key)) pool.set(key, []);
    pool.get(key).push(item);
  }
  const moves = [];
  const paired = new Set();
  const stillRemoved = [];
  for (const item of removed) {
    const candidates = KINDS[item.kind].moved ? pool.get(moveKey(item)) : undefined;
    if (candidates && candidates.length > 0) {
      const to = candidates.shift();
      paired.add(to);
      moves.push({ from: item, to });
    } else {
      stillRemoved.push(item);
    }
  }
  return { moves, removed: stillRemoved, added: added.filter((item) => !paired.has(item)) };
}

/**
 * Compare two extractions.
 *
 * @returns {{hard: object[], additive: object[], review: object[]}} findings per group
 */
function diffSurfaces(base, head) {
  const findings = [];
  const push = (item, change, before) => {
    const group = KINDS[item.kind][change];
    if (!group) return;
    findings.push({
      group,
      kind: item.kind,
      change,
      workflow: item.workflow,
      token: item.token,
      where: item.where,
      text: describe(item, change, before),
    });
  };
  const removedItems = [];
  for (const [key, item] of base.items) {
    const now = head.items.get(key);
    if (!now) removedItems.push(item);
    else if (item.detail !== now.detail) push(now, 'changed', item.detail);
  }
  const addedItems = [...head.items].filter(([key]) => !base.items.has(key)).map(([, item]) => item);
  const { moves, removed, added } = pairMoves(removedItems, addedItems);
  // Flags that entered a workflow's rows and that its Markdown never named
  // before: new names, which a flag leaving the rows may have been renamed to.
  const newNames = new Map();
  for (const item of added) {
    if (item.kind !== 'flag' || base.flagMentions.has(flagKey(item.workflow, item.token))) continue;
    if (!newNames.has(item.workflow)) newNames.set(item.workflow, []);
    newNames.get(item.workflow).push(item.token);
  }
  for (const item of removed) {
    // A flag that left every flag row but that its workflow's Markdown still
    // names may have moved: the review group lists where it is now. When a
    // new name entered the rows at the same time it may have been renamed
    // instead, with a note or a helper call keeping the old name in the
    // files, so it stays hard.
    const still = item.kind === 'flag' ? head.flagMentions.get(flagKey(item.workflow, item.token)) : undefined;
    const successors = still ? newNames.get(item.workflow) : undefined;
    if (successors) push(item, 'possible-rename', { still, successors });
    else if (still) push({ ...item, where: still.join(', ') }, 'moved-out', still);
    else push(item, 'removed');
  }
  for (const item of added) push(item, 'added');
  for (const { from, to } of moves) push(to, 'moved', from.where);
  // A moved-out flag comes first in the review group: it may be a silent breaking change.
  const movedOutFirst = (finding) => (finding.change === 'moved-out' ? 0 : 1);
  findings.sort(
    (a, b) =>
      movedOutFirst(a) - movedOutFirst(b) ||
      a.workflow.localeCompare(b.workflow, 'en') ||
      KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) ||
      a.token.localeCompare(b.token, 'en', { numeric: true }) ||
      a.text.localeCompare(b.text, 'en'),
  );
  const result = {};
  for (const group of GROUPS) result[group] = findings.filter((finding) => finding.group === group);
  return result;
}

/**
 * Diff the covered surfaces of two refs in `root`. A null `headRef` reads
 * the working tree.
 */
function compareRefs(root, baseRef, headRef = null) {
  const base = extractSurfaces(refTree(root, baseRef));
  const head = extractSurfaces(openTree(root, headRef));
  return { baseRef, headRef, headLabel: headRef || 'working tree', ...diffSurfaces(base, head), head };
}

// --- CLI ---

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1];
}

const GROUP_TITLES = {
  hard: 'hard (minimum major; a breaking fragment must name each one)',
  additive: 'additive (minimum minor)',
  review: 'review (never fails; judge whether each one needs a note)',
};

function formatReport(report) {
  const lines = [`Covered surfaces: ${report.baseRef} -> ${report.headLabel}`];
  for (const group of GROUPS) {
    lines.push('', `${GROUP_TITLES[group]}: ${report[group].length}`);
    for (const finding of report[group]) lines.push(`  - ${finding.text}`);
  }
  return lines.join('\n');
}

function main(argv = process.argv.slice(2), env = process.env) {
  const root = path.resolve(argValue(argv, '--root') || path.join(__dirname, '..'));
  const inCi = env.GITHUB_ACTIONS === 'true' || env.CI === 'true';
  const baseRef = argValue(argv, '--base') || lastStableTag(root);
  const headRef = argValue(argv, '--head');
  if (!baseRef) {
    if (inCi) {
      console.error('error: no stable release tag found. Fetch tags (actions/checkout with fetch-depth: 0) or pass --base <ref>.');
      return 2;
    }
    console.log('No stable release tag found, so there is nothing to compare against (fetch tags or pass --base <ref>).');
    return 0;
  }
  for (const ref of [baseRef, headRef].filter(Boolean)) {
    if (!resolveCommit(root, ref)) {
      console.error(`error: ref ${ref} not found.`);
      return 2;
    }
  }
  const report = compareRefs(root, baseRef, headRef);
  if (argv.includes('--json')) {
    const { hard, additive, review } = report;
    console.log(JSON.stringify({ base: baseRef, head: report.headLabel, hard, additive, review }, null, 2));
  } else {
    console.log(formatReport(report));
  }
  return 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  GROUPS,
  KINDS,
  compareRefs,
  diffSurfaces,
  extractSurfaces,
  flagsInRow,
  formatReport,
  lastStableTag,
  main,
  openTree,
  parseCatFileBatch,
  refTree,
  resolveCommit,
  schemaWorkflow,
  workingTree,
};
