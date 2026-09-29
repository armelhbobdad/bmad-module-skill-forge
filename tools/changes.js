/**
 * Change Fragments and the Release Gate
 *
 * Each user-visible change carries a short YAML fragment in changes/ (the
 * format is in changes/README.md). This tool validates the fragments, sets
 * the minimum version bump a release needs from them and from the
 * covered-surface diff (tools/covered-surfaces.js), refuses a version_bump
 * below it, and renders the fragments into the CHANGELOG.md block and the
 * GitHub Release notes.
 *
 * A release takes the fragments that did not exist at the last stable tag
 * (`git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*'`), so
 * nothing is deleted at release time and a burned run leaves nothing to
 * restore. A released fragment is never read again, so a fragment that was
 * in that tag and has changed since, or a new file with the content of one
 * (a rename or a copy), is refused: the first would drop a change from the
 * notes, the second would announce an old one twice.
 *
 * Minimum bump, the highest of: a breaking fragment (major), an added or
 * changed fragment (minor), a fixed or docs fragment (patch), a hard surface
 * change (major), an additive surface change (minor).
 *
 * Commands:
 *   check      Validate every fragment in changes/, refuse a released
 *              fragment that changed and a file that is not a fragment, and
 *              check that "## [Unreleased]" in CHANGELOG.md is empty. Exit 1
 *              on any problem.
 *   preview    Show the selected fragments, the files in changes/ to fix,
 *              the surface changes, the minimum bump and why, the next
 *              version, the gate verdict for the whole next release and the
 *              rendered block. Takes --bump <type> (default: the minimum).
 *              Exit 1 only when a file in changes/ needs fixing; the gate
 *              verdict is printed, not enforced.
 *   gate       --bump <alpha|beta|rc|patch|minor|major>. Refuses (exit 1)
 *              when the version the Bump version step of release.yaml would
 *              produce is below the minimum (semver.diff from the last stable
 *              tag) or below the current version, when a hard surface change
 *              is not named in backticks in a breaking fragment, when a major
 *              release has no breaking fragment, when a stable release has no
 *              fragment or a non-empty "## [Unreleased]", when a file in
 *              changes/ needs fixing, and when a prerelease cannot reach the
 *              minimum (it names the hand bump to make).
 *   release    Render the block for the version in package.json (or
 *              --version). A stable release inserts it under an empty
 *              "## [Unreleased]" in CHANGELOG.md, leaving older history
 *              byte-identical; every release writes release_notes.md (or
 *              --notes <file>). A prerelease leaves CHANGELOG.md alone.
 *              --review <file> also writes the "Review before approving"
 *              text for the bot PR. --notes-only skips CHANGELOG.md.
 *              --date YYYY-MM-DD overrides today's date (UTC).
 *
 * Common options: --base <ref> (instead of the last stable tag), --root <dir>
 * (another checkout; the tests use this). With no stable tag a CI run exits
 * 2; a local run selects every fragment, skips the surface diff and says so.
 *
 * Usage:
 *   node tools/changes.js check
 *   node tools/changes.js preview [--bump major]
 *   node tools/changes.js gate --bump minor
 *   node tools/changes.js release [--review release_review.md]
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
// Dev-only tool: yaml and semver are devDependencies (release.yaml runs npm ci first).
const semver = require('semver');
const YAML = require('yaml');
const { compareRefs, lastStableTag, resolveCommit } = require('./covered-surfaces.js');
const { hasEmDash } = require('./validate-no-em-dash.js');

const CHANGES_DIR = 'changes';
const NOT_FRAGMENTS = new Set(['README.md', '.gitkeep']);
const FRAGMENT_NAME = /^[a-z0-9][a-z0-9-]*\.yaml$/;
const KEYS = ['type', 'scope', 'summary', 'migration', 'issues', 'prs'];
const TYPES = ['breaking', 'added', 'changed', 'fixed', 'docs', 'lead'];
const SECTIONS = [
  ['breaking', 'Breaking changes'],
  ['added', 'Added'],
  ['changed', 'Changed'],
  ['fixed', 'Fixed'],
  ['docs', 'Documentation'],
];
const TYPE_LEVEL = { breaking: 'major', added: 'minor', changed: 'minor', fixed: 'patch', docs: 'patch', lead: 'none' };
const GROUP_LEVEL = { hard: 'major', additive: 'minor' };
const LEVELS = ['none', 'patch', 'minor', 'major'];
const BUMPS = ['alpha', 'beta', 'rc', 'patch', 'minor', 'major'];
const PREIDS = new Set(['alpha', 'beta', 'rc']);
const SCOPE = /^[a-z0-9][a-z0-9 ,._/-]*$/;
// A pull request body holds at most 65536 characters; leave room for the rest of the body.
const REVIEW_LIMIT = 60_000;

class ToolError extends Error {
  constructor(message, exitCode = 1) {
    super(message);
    this.exitCode = exitCode;
  }
}

const rank = (level) => LEVELS.indexOf(level);

// --- Fragments ---

/**
 * Problems with one parsed fragment.
 *
 * @param {unknown} data - The parsed YAML
 * @returns {string[]} one message per problem; empty when the fragment is valid
 */
function validateFragment(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return ['must be a YAML mapping with at least type and summary'];
  const errors = [];
  for (const key of Object.keys(data)) if (!KEYS.includes(key)) errors.push(`unknown key "${key}" (the keys are ${KEYS.join(', ')})`);
  if (!TYPES.includes(data.type)) errors.push(`type must be one of ${TYPES.join(', ')}`);
  if (typeof data.summary !== 'string' || !data.summary.trim())
    errors.push('summary is required: what changed, in words a user understands');
  if (data.type === 'lead') {
    for (const key of ['scope', 'migration', 'issues', 'prs']) if (key in data) errors.push(`a lead takes only a summary, not ${key}`);
  } else {
    if (!('scope' in data)) {
      if (data.type !== 'docs') errors.push('scope is required: the workflow or area that changed, for example skf-setup');
    } else if (typeof data.scope !== 'string' || !SCOPE.test(data.scope.trim())) {
      errors.push('scope must be one line of lower-case names, for example "skf-create-skill, skf-test-skill"');
    }
    const hasMigration = typeof data.migration === 'string' && data.migration.trim() !== '';
    if (data.type === 'breaking' && !hasMigration) errors.push('a breaking change needs a migration: the exact action a user takes');
    if (data.type !== 'breaking' && 'migration' in data) errors.push('migration is only for breaking changes');
    for (const key of ['issues', 'prs']) {
      if (!(key in data)) continue;
      const list = data[key];
      if (!Array.isArray(list) || list.length === 0 || !list.every((n) => Number.isInteger(n) && n > 0)) {
        errors.push(`${key} must be a list of ${key === 'prs' ? 'pull request' : 'issue'} numbers, for example [509]`);
      }
    }
  }
  for (const key of ['summary', 'migration']) {
    const text = data[key];
    if (typeof text !== 'string') continue;
    if (text.split('\n').some((line) => hasEmDash(line)))
      errors.push(`${key} has an em dash: use a colon, a comma, parentheses or a new sentence`);
    if (text.includes('§')) errors.push(`${key} cites a step-file section: describe the behaviour instead`);
    if (/\n[ \t]*\n/.test(text.trim())) errors.push(`${key} must be one paragraph`);
  }
  return errors;
}

/** Parse one fragment file. */
function parseFragment(file, text) {
  const name = path.posix.basename(file);
  const errors = [];
  if (!FRAGMENT_NAME.test(name)) errors.push('name fragments <topic>.yaml in lower case, with hyphens between words');
  let data = null;
  try {
    data = YAML.parse(text);
  } catch (error) {
    errors.push(`not valid YAML: ${error.message.split('\n')[0]}`);
    return { file, name, data: null, errors };
  }
  errors.push(...validateFragment(data));
  return { file, name, data, errors };
}

/**
 * Every fragment in <root>/changes/, plus the files there that are not fragments.
 *
 * @returns {{fragments: object[], problems: {file: string, errors: string[]}[]}}
 */
function readFragments(root) {
  let entries;
  try {
    entries = fs.readdirSync(path.join(root, CHANGES_DIR), { withFileTypes: true });
  } catch {
    return { fragments: [], problems: [] };
  }
  const fragments = [];
  const problems = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name, 'en'))) {
    const file = `${CHANGES_DIR}/${entry.name}`;
    if (NOT_FRAGMENTS.has(entry.name)) continue;
    if (!entry.isFile()) {
      problems.push({ file, errors: ['fragments go directly in changes/, not in a subfolder'] });
      continue;
    }
    if (!entry.name.endsWith('.yaml')) {
      problems.push({
        file,
        errors: ['not a fragment: fragments are <topic>.yaml files (README.md and .gitkeep are the only other files allowed)'],
      });
      continue;
    }
    fragments.push(parseFragment(file, fs.readFileSync(path.join(root, file), 'utf8')));
  }
  return { fragments, problems };
}

function git(root, args, input) {
  return execFileSync('git', ['-c', 'core.quotePath=false', ...args], {
    cwd: root,
    encoding: 'utf8',
    input,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
}

/** Each file under changes/ at `ref`, with its blob id. */
function fragmentBlobsAtRef(root, ref) {
  const blobs = new Map();
  for (const entry of git(root, ['ls-tree', '-r', '-z', '--full-tree', ref, '--', CHANGES_DIR]).split('\0')) {
    const tab = entry.indexOf('\t');
    if (tab === -1) continue;
    const [, type, sha] = entry.slice(0, tab).split(' ');
    if (type === 'blob') blobs.set(entry.slice(tab + 1), sha);
  }
  return blobs;
}

/** The blob id git would give each working-tree file (line-ending filters applied). */
function hashFiles(root, files) {
  if (files.length === 0) return [];
  return git(root, ['hash-object', '--stdin-paths'], `${files.join('\n')}\n`)
    .trim()
    .split('\n');
}

/**
 * Split the fragments on disk into those this release takes and those it
 * refuses. A fragment whose path was in `baseTag` was released: it is left
 * out, and refused when its content changed since. A fragment with a new
 * path but the content of a released one (a rename or a copy) is refused.
 *
 * @returns {{selected: object[], problems: {file: string, errors: string[]}[]}}
 */
function selectFragments(root, baseTag, fragments) {
  if (!baseTag) return { selected: fragments, problems: [] };
  const atBase = fragmentBlobsAtRef(root, baseTag);
  const releasedAs = new Map();
  for (const [file, sha] of atBase) {
    if (!NOT_FRAGMENTS.has(path.posix.basename(file)) && !releasedAs.has(sha)) releasedAs.set(sha, file);
  }
  const hashes = hashFiles(
    root,
    fragments.map((fragment) => fragment.file),
  );
  const selected = [];
  const problems = [];
  for (const [index, fragment] of fragments.entries()) {
    const hash = hashes[index];
    if (atBase.has(fragment.file)) {
      if (atBase.get(fragment.file) !== hash) {
        problems.push({
          file: fragment.file,
          errors: [
            `is in ${baseTag}, so it was already released, and it has changed since. A released fragment is never read again: ` +
              `restore it (git checkout ${baseTag} -- ${fragment.file}) and put the new change in a fragment with a new name.`,
          ],
        });
      }
      continue;
    }
    const source = releasedAs.get(hash);
    if (source) {
      problems.push({
        file: fragment.file,
        errors: [
          `has the same content as ${source}, which ${baseTag} already released, so it would announce that change again: ` +
            'delete it, or write the new change in it.',
        ],
      });
      continue;
    }
    selected.push(fragment);
  }
  return { selected, problems };
}

/**
 * True when the fragment names `token` in a backticked code span, as a whole
 * item: `--tier=<x>` names `--tier`, but `forge-auto` does not name `forge`,
 * `error.phase` does not name `error`, and the plain word error names nothing.
 */
function namesToken(fragment, token) {
  const text = `${fragment.data.summary || ''}\n${fragment.data.migration || ''}`;
  const escaped = token.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
  const whole = new RegExp(String.raw`(?<![\w.-])${escaped}(?![\w.-])`);
  return [...text.matchAll(/`([^`]+)`/g)].some((span) => whole.test(span[1]));
}

// --- Versions ---

/**
 * The minimum bump and every reason for it, highest first.
 *
 * @param {object[]} fragments - Valid, selected fragments
 * @param {{hard: object[], additive: object[]}|null} surfaces - Covered-surface findings, or null when skipped
 */
function minimumBump(fragments, surfaces) {
  const reasons = [];
  for (const fragment of fragments) {
    const level = TYPE_LEVEL[fragment.data.type];
    if (level && level !== 'none') {
      const scope = fragment.data.scope ? ` (${fragment.data.scope.trim()})` : '';
      reasons.push({ level, text: `${fragment.data.type} fragment ${fragment.file}${scope}` });
    }
  }
  for (const group of ['hard', 'additive']) {
    for (const finding of surfaces ? surfaces[group] : [])
      reasons.push({ level: GROUP_LEVEL[group], text: `${group} surface change: ${finding.text}` });
  }
  reasons.sort((a, b) => rank(b.level) - rank(a.level));
  return { level: reasons.length > 0 ? reasons[0].level : 'none', reasons };
}

/** The version `npm version` gives in the Bump version step of release.yaml. */
function nextVersion(current, bump) {
  if (!BUMPS.includes(bump)) throw new ToolError(`--bump must be one of ${BUMPS.join(', ')}`, 2);
  const next = PREIDS.has(bump) ? semver.inc(current, 'prerelease', bump) : semver.inc(current, bump);
  if (!next) throw new ToolError(`cannot bump version ${current} with ${bump}`, 2);
  return next;
}

/** How far `to` moves from `from`: none, patch, minor or major (a premajor counts as major). */
function reachedLevel(from, to) {
  if (!semver.gt(to, from)) return 'none';
  const level = (semver.diff(from, to) || '').replace(/^pre(?=major|minor|patch)/, '');
  return LEVELS.includes(level) ? level : 'none';
}

/** "a", "a or b", "a, b or c". */
function orList(items) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} or ${items.at(-1)}`;
}

/**
 * Everything the gate refuses for one release.
 *
 * @param {object} input
 * @param {string} input.next - The version being released
 * @param {string} input.bump - The version_bump input, for messages
 * @param {string} input.current - package.json's version before the bump
 * @param {string|null} input.baseTag - The last stable tag, or null
 * @param {object[]} input.fragments - Selected fragments (invalid ones included)
 * @param {object|null} input.surfaces - Covered-surface findings, or null when skipped
 * @param {{file: string, errors: string[]}[]} [input.problems] - Files in changes/ that are not usable fragments
 * @param {string|null} [input.changelog] - CHANGELOG.md, checked for a stable release; null skips the check
 */
function evaluateGate({ next, bump, current, baseTag, fragments, surfaces, problems = [], changelog = null }) {
  const refusals = [];
  const valid = fragments.filter((fragment) => fragment.errors.length === 0);
  for (const { file, errors } of [...problems, ...fragments]) {
    for (const error of errors) refusals.push(`${file}: ${error}`);
  }
  const floor = minimumBump(valid, surfaces);
  const baseVersion = baseTag ? semver.clean(baseTag) : null;
  const from = baseVersion || current;
  const fromLabel = baseVersion ? baseTag : `the current version ${current}`;
  const prerelease = semver.prerelease(next) !== null;
  const reached = reachedLevel(from, next);

  if (semver.lt(next, current)) {
    // npm moves a prerelease to a lower id without complaint: alpha from 3.0.0-rc.1 gives 3.0.0-alpha.0.
    const higher = BUMPS.filter((candidate) => semver.gt(nextVersion(current, candidate), current));
    refusals.push(
      `${bump} from ${current} gives ${next}, which is below the current version ${current}: dispatch ${orList(higher)} instead.`,
    );
  }
  if (semver.gt(next, from)) {
    if (rank(reached) < rank(floor.level)) {
      const why = floor.reasons.filter((reason) => reason.level === floor.level).map((reason) => reason.text);
      if (prerelease) {
        const preid = PREIDS.has(bump) ? bump : 'rc';
        const handBump = semver.inc(from, `pre${floor.level}`, preid);
        refusals.push(
          `${bump} from ${current} gives ${next}, a ${reached} step from ${fromLabel}, and a prerelease cannot reach the minimum ${floor.level} ` +
            `(${why.join('; ')}). Set the version to ${handBump} by hand in a pull request (package.json, package-lock.json, ` +
            `.claude-plugin/marketplace.json and docs/_data/pinned.yaml), then dispatch ${preid}: the first ${preid} published is ` +
            `${semver.inc(handBump, 'prerelease', preid)}. Or release ${floor.level} directly.`,
        );
      } else {
        refusals.push(`${bump} gives ${next}, a ${reached} step from ${fromLabel}, below the minimum ${floor.level} (${why.join('; ')}).`);
      }
    }
  } else {
    refusals.push(`${next} is not above ${fromLabel}.`);
  }

  const breaking = valid.filter((fragment) => fragment.data.type === 'breaking');
  for (const finding of surfaces ? surfaces.hard : []) {
    if (!breaking.some((fragment) => namesToken(fragment, finding.token))) {
      refusals.push(
        `${finding.text}, and no breaking fragment names \`${finding.token}\` in backticks: add one that says what changed and gives the migration.`,
      );
    }
  }
  if (!prerelease && changelog !== null) {
    const problem = unreleasedProblem(changelog);
    if (problem) refusals.push(problem);
  }
  if (reached === 'major' && breaking.length === 0) {
    refusals.push(`${next} is a major release, but no fragment has type: breaking. Add one per breaking change, or pick a lower bump.`);
  }
  const changes = valid.filter((fragment) => fragment.data.type !== 'lead');
  if (!prerelease && changes.length === 0) {
    refusals.push(`a stable release needs at least one change fragment in changes/ added since ${baseTag || 'the last release'}.`);
  }
  const leads = valid.filter((fragment) => fragment.data.type === 'lead');
  if (leads.length > 1) refusals.push(`only one lead fragment per release; found ${leads.map((fragment) => fragment.file).join(', ')}.`);
  return { next, prerelease, reached, floor, refusals };
}

// --- Rendering ---

function oneParagraph(text) {
  return text.trim().replaceAll(/\s*\n\s*/g, ' ');
}

function entry(fragment, repoUrl) {
  const { scope, summary, prs, issues } = fragment.data;
  const refs = [];
  if (prs) refs.push(prs.map((n) => `[#${n}](${repoUrl}/pull/${n})`).join(', '));
  if (issues) refs.push(`${issues.length > 1 ? 'issues' : 'issue'} ${issues.map((n) => `[#${n}](${repoUrl}/issues/${n})`).join(', ')}`);
  const lead = scope ? `**${scope.trim()}:** ` : '';
  return `- ${lead}${oneParagraph(summary)}${refs.length > 0 ? ` (${refs.join('; ')})` : ''}`;
}

function compareUrl(repoUrl, baseTag, version) {
  return baseTag ? `${repoUrl}/compare/${baseTag}...v${version}` : `${repoUrl}/releases/tag/v${version}`;
}

/**
 * The CHANGELOG.md block for one release, in the heading shape the earlier
 * releases use. Entries in a section are ordered by scope, then file name.
 *
 * @returns {string} the block, ending with one newline
 */
function renderBlock({ version, baseTag, date, fragments, repoUrl }) {
  const lines = [`## [${version}](${compareUrl(repoUrl, baseTag, version)}) (${date})`, ''];
  const lead = fragments.find((fragment) => fragment.data.type === 'lead');
  if (lead) lines.push(oneParagraph(lead.data.summary), '');
  let sections = 0;
  for (const [type, title] of SECTIONS) {
    const group = fragments
      .filter((fragment) => fragment.data.type === type)
      .sort((a, b) => (a.data.scope || '').localeCompare(b.data.scope || '', 'en') || a.name.localeCompare(b.name, 'en'));
    if (group.length === 0) continue;
    sections += 1;
    lines.push(`### ${title}`, '');
    for (const fragment of group) {
      lines.push(entry(fragment, repoUrl));
      if (type === 'breaking') lines.push('', `  **Migration:** ${oneParagraph(fragment.data.migration)}`, '');
    }
    if (type !== 'breaking') lines.push('');
  }
  if (sections === 0 && !lead) lines.push('No change fragments were added for this release.', '');
  return `${lines.join('\n').trimEnd()}\n`;
}

/**
 * Where "## [Unreleased]" is in CHANGELOG.md and the first non-blank line
 * after it, or the reason a release cannot go under it.
 */
function locateUnreleased(lines) {
  const unreleased = lines.findIndex((line) => /^## \[Unreleased\]\s*$/.test(line));
  if (unreleased === -1) return { problem: 'CHANGELOG.md has no "## [Unreleased]" heading to insert the release under.' };
  let next = unreleased + 1;
  while (next < lines.length && lines[next].trim() === '') next += 1;
  if (next < lines.length && !/^## \[/.test(lines[next])) {
    return {
      problem:
        '"## [Unreleased]" in CHANGELOG.md is not empty. Move its text into change fragments (changes/*.yaml) and leave the heading with nothing under it.',
    };
  }
  return { unreleased, next, problem: null };
}

/** Why a stable release cannot be inserted into this CHANGELOG.md, or null. */
function unreleasedProblem(changelog) {
  return locateUnreleased(changelog.split('\n')).problem;
}

/**
 * Insert a release block under an empty "## [Unreleased]". Everything from
 * the previous release heading down is kept byte for byte.
 */
function insertIntoChangelog(changelog, block, version) {
  const lines = changelog.split('\n');
  const { unreleased, next, problem } = locateUnreleased(lines);
  if (problem) throw new ToolError(problem);
  if (lines.some((line) => line.startsWith(`## [${version}]`))) throw new ToolError(`CHANGELOG.md already has a ## [${version}] section.`);
  const head = lines.slice(0, unreleased + 1).join('\n');
  if (next >= lines.length) return `${head}\n\n${block.trimEnd()}\n`;
  return `${head}\n\n${block.trimEnd()}\n\n${lines.slice(next).join('\n')}`;
}

/** The GitHub Release body: the block, how to install, and the compare link. */
function renderNotes({ block, version, baseTag, repoUrl, packageName }) {
  const prerelease = semver.prerelease(version) !== null;
  const install = prerelease ? `npx ${packageName}@${version} install` : `npx ${packageName} install`;
  return [
    block.trimEnd(),
    '',
    '## Installation',
    '',
    '```bash',
    install,
    '```',
    '',
    `**Full Changelog**: <${compareUrl(repoUrl, baseTag, version)}>`,
    '',
  ].join('\n');
}

/** Headings one level down, outside fenced code, so the notes nest inside a PR body section. */
function demoteHeadings(markdown) {
  let fenced = false;
  return markdown
    .split('\n')
    .map((line) => {
      if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
      return !fenced && /^#{1,5} /.test(line) ? `#${line}` : line;
    })
    .join('\n');
}

function surfaceList(surfaces, group) {
  return surfaces[group].length === 0 ? ['- none'] : surfaces[group].map((finding) => `- ${finding.text}`);
}

/** The "Review before approving" section of the bot PR. */
function renderReview({ version, baseTag, gate, surfaces, block }) {
  const from = baseTag || 'the last release';
  const lines = [
    '## Review before approving',
    '',
    `v${version} is a ${gate.reached} step from ${from}; the change fragments and covered surfaces need at least ${gate.floor.level}.`,
    '',
    'Approve only when:',
    '',
    '- [ ] each breaking change says what stopped working and gives a migration a user can follow;',
    '- [ ] each surface change below is described by a fragment of the right type, or needs no note;',
    '- [ ] the notes below read well as the GitHub Release page (it adds Installation and the compare link).',
    '',
    `### Why the minimum is ${gate.floor.level}`,
    '',
    ...(gate.floor.reasons.length === 0
      ? ['- no fragment or surface change sets one']
      : gate.floor.reasons.map((reason) => `- ${reason.level}: ${reason.text}`)),
    '',
  ];
  if (surfaces) {
    lines.push(
      `### Surface changes since ${from}`,
      '',
      'Hard (a breaking fragment names each one):',
      '',
      ...surfaceList(surfaces, 'hard'),
      '',
      'Additive:',
      '',
      ...surfaceList(surfaces, 'additive'),
      '',
      'Review (never fails; decide whether each one needs a note):',
      '',
      ...surfaceList(surfaces, 'review'),
      '',
    );
  } else {
    lines.push('No stable release tag was found, so the covered surfaces were not compared.', '');
  }
  lines.push(demoteHeadings(block.trimEnd()), '');
  let text = lines.join('\n');
  if (text.length > REVIEW_LIMIT) {
    const cut = text.lastIndexOf('\n', REVIEW_LIMIT);
    text = `${text.slice(0, cut)}\n\n(Cut to fit a pull request body: run \`npm run changes:preview\` for the full text.)\n`;
  }
  return text;
}

// --- Commands ---

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1] || null;
}

function repoUrlOf(pkg) {
  const raw = typeof pkg.repository === 'string' ? pkg.repository : pkg.repository && pkg.repository.url;
  if (!raw) throw new ToolError('package.json has no repository url to link issues and pull requests to.', 2);
  return raw
    .replace(/^git\+/, '')
    .replace(/\.git$/, '')
    .replace(/^git@github\.com:/, 'https://github.com/');
}

function annotate(env, level, message, file) {
  if (env.GITHUB_ACTIONS === 'true') console.log(`::${level}${file ? ` file=${file}` : ''}::${message.replaceAll('\n', ' ')}`);
}

/**
 * The ref releases are measured from: --base, else the last stable tag. With
 * neither, a CI run stops (exit 2) and a local run goes on with a warning.
 */
function resolveBase(root, argv, env, consequence) {
  const inCi = env.GITHUB_ACTIONS === 'true' || env.CI === 'true';
  const baseTag = argValue(argv, '--base') || lastStableTag(root);
  if (baseTag && !resolveCommit(root, baseTag)) throw new ToolError(`ref ${baseTag} not found.`, 2);
  if (baseTag) return { baseTag, warnings: [] };
  if (inCi) throw new ToolError('no stable release tag found. Fetch tags (actions/checkout with fetch-depth: 0) or pass --base <ref>.', 2);
  return { baseTag: null, warnings: [`No stable release tag found: ${consequence} Fetch tags to fix this.`] };
}

function readChangelog(root) {
  try {
    return fs.readFileSync(path.join(root, 'CHANGELOG.md'), 'utf8');
  } catch {
    return '';
  }
}

/** Fragments, surfaces and versions shared by preview, gate and release. */
function loadContext(root, argv, env) {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  const { baseTag, warnings } = resolveBase(
    root,
    argv,
    env,
    'every fragment in changes/ is selected and the covered surfaces are not compared.',
  );
  const read = readFragments(root);
  const { selected, problems } = selectFragments(root, baseTag, read.fragments);
  const surfaces = baseTag ? compareRefs(root, baseTag, null) : null;
  return {
    pkg,
    repoUrl: repoUrlOf(pkg),
    baseTag,
    fragments: read.fragments,
    problems: [...read.problems, ...problems],
    selected,
    surfaces,
    warnings,
    changelog: readChangelog(root),
  };
}

function runCheck(root, argv, env) {
  const { baseTag, warnings } = resolveBase(root, argv, env, 'released fragments were not compared with the release that shipped them.');
  const read = readFragments(root);
  const released = selectFragments(root, baseTag, read.fragments).problems;
  const unreleased = unreleasedProblem(readChangelog(root));
  const all = [
    ...read.problems,
    ...released,
    ...read.fragments.filter((fragment) => fragment.errors.length > 0),
    ...(unreleased ? [{ file: 'CHANGELOG.md', errors: [unreleased] }] : []),
  ];
  for (const warning of warnings) console.log(`warning: ${warning}`);
  for (const { file, errors } of all) {
    for (const error of errors) {
      console.log(`${file}: ${error}`);
      annotate(env, 'error', error, file);
    }
  }
  if (all.length > 0) {
    console.log(`\n${all.length} file(s) need fixing (the fragment format is in changes/README.md).`);
    return 1;
  }
  console.log(`${read.fragments.length} change fragment(s) valid.`);
  return 0;
}

function fragmentLines(selected) {
  if (selected.length === 0) return ['  (none)'];
  return selected.map((fragment) => {
    const type = fragment.data && TYPES.includes(fragment.data.type) ? fragment.data.type : '?';
    const scope = fragment.data && typeof fragment.data.scope === 'string' ? `  ${fragment.data.scope.trim()}` : '';
    const invalid = fragment.errors.length > 0 ? `  INVALID: ${fragment.errors.join('; ')}` : '';
    return `  ${type.padEnd(8)}  ${fragment.file}${scope}${invalid}`;
  });
}

function runPreview(root, argv, env) {
  const context = loadContext(root, argv, env);
  const { pkg, baseTag, selected, surfaces, warnings, problems, changelog } = context;
  const valid = selected.filter((fragment) => fragment.errors.length === 0);
  const floor = minimumBump(valid, surfaces);
  const bump = argValue(argv, '--bump') || (floor.level === 'none' ? 'patch' : floor.level);
  const next = nextVersion(pkg.version, bump);
  const gate = evaluateGate({ next, bump, current: pkg.version, baseTag, fragments: selected, surfaces, problems, changelog });
  const since = baseTag || 'the start';
  const out = [
    ...warnings.map((warning) => `warning: ${warning}`),
    `Change fragments added since ${since}: ${selected.length}`,
    ...fragmentLines(selected),
    '',
  ];
  if (problems.length > 0) {
    out.push(
      'Files in changes/ to fix (never rendered):',
      ...problems.flatMap(({ file, errors }) => errors.map((error) => `  ${file}: ${error}`)),
      '',
    );
  }
  if (surfaces) {
    out.push(`Covered surfaces, ${baseTag} -> working tree:`);
    for (const group of ['hard', 'additive', 'review']) {
      out.push(`  ${group}: ${surfaces[group].length}`);
      for (const finding of surfaces[group]) {
        let mark = '';
        if (group === 'hard') {
          const named = valid.filter((fragment) => fragment.data.type === 'breaking' && namesToken(fragment, finding.token));
          mark =
            named.length > 0 ? `  [named in ${named.map((fragment) => fragment.name).join(', ')}]` : '  [NOT NAMED in a breaking fragment]';
        }
        out.push(`    - ${finding.text}${mark}`);
      }
    }
    out.push('');
  }
  const verdict =
    gate.refusals.length === 0 ? ['Gate: passes.'] : ['Gate: refuses this bump:', ...gate.refusals.map((refusal) => `  - ${refusal}`)];
  out.push(
    `Minimum bump: ${floor.level}`,
    ...floor.reasons.map((reason) => `  ${reason.level.padEnd(5)}  ${reason.text}`),
    '',
    `Next version: ${pkg.version} -> ${next} (--bump ${bump}, a ${gate.reached} step from ${baseTag || pkg.version})`,
    ...verdict,
    '',
    'Rendered block:',
    '',
    renderBlock({ version: next, baseTag, date: today(), fragments: valid, repoUrl: context.repoUrl }),
  );
  console.log(out.join('\n'));
  return problems.length > 0 || selected.some((fragment) => fragment.errors.length > 0) ? 1 : 0;
}

function writeStepSummary(env, lines) {
  if (!env.GITHUB_STEP_SUMMARY) return;
  try {
    fs.appendFileSync(env.GITHUB_STEP_SUMMARY, `${lines.join('\n')}\n`);
  } catch {
    // The summary is a convenience; the log carries the same text.
  }
}

function runGate(root, argv, env) {
  const bump = argValue(argv, '--bump');
  if (!bump) throw new ToolError(`gate needs --bump <${BUMPS.join('|')}>.`, 2);
  const { pkg, baseTag, selected, surfaces, warnings, problems, changelog } = loadContext(root, argv, env);
  const next = nextVersion(pkg.version, bump);
  const gate = evaluateGate({ next, bump, current: pkg.version, baseTag, fragments: selected, surfaces, problems, changelog });
  for (const warning of warnings) console.log(`warning: ${warning}`);
  const movedOut = surfaces ? surfaces.review.filter((item) => item.change === 'moved-out').length : 0;
  const lines = [
    `Last stable tag: ${baseTag || '(none)'}`,
    `Change fragments since then: ${selected.length}`,
    `Covered-surface changes: ${surfaces ? `${surfaces.hard.length} hard, ${surfaces.additive.length} additive, ${surfaces.review.length} to review` : 'not compared'}`,
    ...(movedOut > 0
      ? [`  ${movedOut} flag(s) left every flag row: confirm each workflow still accepts it, or add a breaking fragment that names it`]
      : []),
    `Minimum bump: ${gate.floor.level}`,
    ...gate.floor.reasons.filter((reason) => reason.level === gate.floor.level).map((reason) => `  ${reason.text}`),
    `${bump}: ${pkg.version} -> ${next} (a ${gate.reached} step)`,
  ];
  console.log(lines.join('\n'));
  const summary = ['### Release gate', '', ...lines.map((line) => (line.startsWith('  ') ? `  - ${line.trim()}` : `- ${line}`)), ''];
  if (gate.refusals.length > 0) {
    console.log('\nThe release gate refuses this version_bump:');
    for (const refusal of gate.refusals) {
      console.log(`  - ${refusal}`);
      annotate(env, 'error', refusal);
    }
    console.log(
      '\nNothing was committed. Fix the fragments by pull request (npm run changes:preview shows the result), or pick another version_bump.',
    );
    writeStepSummary(env, [...summary, '**Refused:**', '', ...gate.refusals.map((refusal) => `- ${refusal}`)]);
    return 1;
  }
  console.log('\nThe release gate passes.');
  writeStepSummary(env, [...summary, '**Passed.**']);
  return 0;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function runRelease(root, argv, env) {
  const context = loadContext(root, argv, env);
  const { pkg, baseTag, selected, surfaces, repoUrl, problems } = context;
  const version = argValue(argv, '--version') || pkg.version;
  if (!semver.valid(version)) throw new ToolError(`version ${version} is not a valid semantic version.`, 2);
  const date = argValue(argv, '--date') || today();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new ToolError('--date takes YYYY-MM-DD.', 2);
  const changelog = argv.includes('--notes-only') ? null : context.changelog;
  const gate = evaluateGate({
    next: version,
    bump: 'release',
    current: pkg.version,
    baseTag,
    fragments: selected,
    surfaces,
    problems,
    changelog,
  });
  if (gate.refusals.length > 0) {
    for (const refusal of gate.refusals) {
      console.log(`error: ${refusal}`);
      annotate(env, 'error', refusal);
    }
    return 1;
  }
  const valid = selected.filter((fragment) => fragment.errors.length === 0);
  const block = renderBlock({ version, baseTag, date, fragments: valid, repoUrl });
  const written = [];
  if (!gate.prerelease && !argv.includes('--notes-only')) {
    const changelogPath = path.join(root, 'CHANGELOG.md');
    const changelog = fs.readFileSync(changelogPath, 'utf8');
    fs.writeFileSync(changelogPath, insertIntoChangelog(changelog, block, version));
    written.push(`CHANGELOG.md (the ${version} block)`);
  }
  const notesPath = path.resolve(root, argValue(argv, '--notes') || 'release_notes.md');
  fs.writeFileSync(notesPath, renderNotes({ block, version, baseTag, repoUrl, packageName: pkg.name }));
  written.push(path.relative(root, notesPath));
  const reviewArg = argValue(argv, '--review');
  if (reviewArg) {
    const reviewPath = path.resolve(root, reviewArg);
    fs.writeFileSync(reviewPath, renderReview({ version, baseTag, gate, surfaces, block }));
    written.push(path.relative(root, reviewPath));
  }
  console.log(`Release ${version} from ${valid.length} change fragment(s) since ${baseTag || 'the start'}. Wrote ${written.join(', ')}.`);
  if (gate.prerelease) console.log('A prerelease leaves CHANGELOG.md alone: its fragments are rendered again for the stable release.');
  return 0;
}

const USAGE = `Usage: node tools/changes.js <command> [options]

  check                        validate changes/ and the empty [Unreleased] of CHANGELOG.md
  preview [--bump <type>]      fragments, surface changes, minimum bump, next version, gate verdict, rendered block
  gate --bump <type>           refuse a version_bump the fragments and surfaces do not allow
  release [--review <file>]    render CHANGELOG.md (stable only) and release_notes.md

  <type> is one of ${BUMPS.join(', ')}.
  Options: --base <ref>, --root <dir>, and for release --version <v>, --date YYYY-MM-DD,
  --notes <file>, --notes-only. The fragment format is in changes/README.md.`;

function main(argv = process.argv.slice(2), env = process.env) {
  const [command, ...rest] = argv;
  const root = path.resolve(argValue(rest, '--root') || path.join(__dirname, '..'));
  try {
    switch (command) {
      case 'check': {
        return runCheck(root, rest, env);
      }
      case 'preview': {
        return runPreview(root, rest, env);
      }
      case 'gate': {
        return runGate(root, rest, env);
      }
      case 'release': {
        return runRelease(root, rest, env);
      }
      case '--help':
      case '-h': {
        console.log(USAGE);
        return 0;
      }
      default: {
        if (command) console.error(`Unknown command: ${command}\n`);
        console.error(USAGE);
        return 2;
      }
    }
  } catch (error) {
    if (!(error instanceof ToolError)) throw error;
    console.error(`error: ${error.message}`);
    annotate(env, 'error', error.message);
    return error.exitCode;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  BUMPS,
  TYPES,
  evaluateGate,
  insertIntoChangelog,
  main,
  minimumBump,
  namesToken,
  nextVersion,
  parseFragment,
  reachedLevel,
  readFragments,
  renderBlock,
  renderNotes,
  renderReview,
  selectFragments,
  unreleasedProblem,
  validateFragment,
};
