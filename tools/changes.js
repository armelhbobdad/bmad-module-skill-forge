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
 *              text for the bot PR, and writes that text in full to the
 *              step summary in GitHub Actions. --notes-only skips
 *              CHANGELOG.md. --date YYYY-MM-DD overrides today's date
 *              (UTC). The notes and the review are kept under GitHub's size
 *              limits (see RELEASE_BODY_LIMIT): when the full text does not
 *              fit, each is shortened and says where the full text is, and
 *              in GitHub Actions the log shows what was shortened.
 *   pr         Check one branch, from its merge base with the base branch
 *              to HEAD (commits only: the working tree is not read). The
 *              base is --base <ref>, else origin/$GITHUB_BASE_REF on a pull
 *              request, else origin/main. The branch fails (exit 1) when:
 *              it changes the code the package ships (src/, tools/cli/,
 *              tools/skf-npx-wrapper.js) or .npmignore with no fragment of
 *              its own and no "Changelog: none (<reason>)" line in one of its
 *              commit messages, merge commits included; a covered item it
 *              removes is not named in backticks by a breaking fragment on
 *              the branch; a covered item it adds is not covered by an added
 *              or breaking fragment on the branch; a fragment it adds or
 *              edits fails the checks of `check`, or edits, renames or copies
 *              a released fragment. The line covers the whole branch, but
 *              never a removal or an addition. An added or breaking fragment
 *              the branch adds covers every addition; an unreleased fragment
 *              it only edits counts only for the items it names in backticks,
 *              and then also stands in for a fragment of its own. The rest of
 *              what the package ships (package.json, README.md, docs/) is not
 *              checked. A failure prints what is missing and a fragment to
 *              fill in, typed and scoped from the changes, which fails
 *              `check` until its marked sentences are rewritten; in GitHub
 *              Actions the verdict and the surface changes to review also go
 *              to the step summary. A head ref under release/bot/
 *              (GITHUB_HEAD_REF: the release commit of release.yaml) passes
 *              with a note only when PR_HEAD_REPO and GITHUB_REPOSITORY name
 *              the same repository; otherwise it is checked like any other
 *              branch. The released-fragment rule takes the last stable tag
 *              reachable from the base (--tag <ref> replaces it). Exit 2 when
 *              the base or, in CI, the stable tag is missing, or when a
 *              shallow clone hides the merge base.
 *
 * Common options: --base <ref> (instead of the last stable tag; for pr, the
 * base branch), --root <dir> (another checkout; the tests use this). With no
 * stable tag a CI run exits 2; a local run selects every fragment, skips the
 * surface diff and says so.
 *
 * Usage:
 *   node tools/changes.js check
 *   node tools/changes.js preview [--bump major]
 *   node tools/changes.js gate --bump minor
 *   node tools/changes.js release [--review release_review.md]
 *   node tools/changes.js pr [--base origin/main]
 */

const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
// Dev-only tool: yaml and semver are devDependencies (release.yaml runs npm ci first).
const semver = require('semver');
const YAML = require('yaml');
const { KINDS, compareRefs, lastStableTag, resolveCommit } = require('./covered-surfaces.js');
const { hasEmDash } = require('./validate-no-em-dash.js');

const CHANGES_DIR = 'changes';
const NOT_FRAGMENTS = new Set(['README.md', '.gitkeep']);
const NOT_A_FRAGMENT = 'not a fragment: fragments are <topic>.yaml files (README.md and .gitkeep are the only other files allowed)';
const IN_SUBFOLDER = 'fragments go directly in changes/, not in a subfolder';
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
// fragmentTemplate starts each sentence to rewrite with this, so a template committed as printed fails.
const TEMPLATE_MARK = 'Rewrite this paragraph';
const TEMPLATE_FIX = { summary: 'say what changed, in words a user understands', migration: 'give the exact action a user takes' };
// GitHub's size limits on what a release writes. A length here is a
// JavaScript string length, in UTF-16 code units, never fewer than the
// characters GitHub counts (a character outside the Basic Multilingual Plane
// takes two units), and each budget keeps a margin under its limit.
// GitHub refuses a release body over 125,000 characters.
const RELEASE_BODY_LIMIT = 125_000;
const NOTES_BUDGET = RELEASE_BODY_LIMIT - 5000;
// GitHub refuses a pull request body over 65,536 characters. REVIEW_BUDGET
// leaves room for the lines release.yaml adds around the review (the Open
// bot PR step, which checks the review against the same number).
const PR_BODY_LIMIT = 65_536;
const REVIEW_BUDGET = 60_000;
// GitHub drops a step summary over 1 MiB; this limit and its budget are bytes.
const STEP_SUMMARY_LIMIT = 1_048_576;
const SUMMARY_BUDGET = 1_000_000;

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
    if (text.includes(TEMPLATE_MARK)) errors.push(`${key} still holds the template text ("${TEMPLATE_MARK}"): ${TEMPLATE_FIX[key]}`);
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
      problems.push({ file, errors: [IN_SUBFOLDER] });
      continue;
    }
    if (!entry.name.endsWith('.yaml')) {
      problems.push({ file, errors: [NOT_A_FRAGMENT] });
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
 * The fragments `baseTag` released: each path with its blob id, and each
 * blob id with the first path that holds it.
 */
function releasedIndex(root, baseTag) {
  const atBase = fragmentBlobsAtRef(root, baseTag);
  const releasedAs = new Map();
  for (const [file, sha] of atBase) {
    if (!NOT_FRAGMENTS.has(path.posix.basename(file)) && !releasedAs.has(sha)) releasedAs.set(sha, file);
  }
  return { baseTag, atBase, releasedAs };
}

/**
 * Why `file`, with blob id `hash`, breaks the released-fragment rule, or
 * null: a released fragment whose content changed, or a new path with the
 * content of a released one (a rename or a copy).
 */
function releasedProblem({ baseTag, atBase, releasedAs }, file, hash) {
  if (atBase.has(file)) {
    if (atBase.get(file) === hash) return null;
    return {
      file,
      errors: [
        `is in ${baseTag}, so it was already released, and it has changed since. A released fragment is never read again: ` +
          `restore it (git checkout ${baseTag} -- ${file}) and put the new change in a fragment with a new name.`,
      ],
    };
  }
  const source = releasedAs.get(hash);
  if (!source) return null;
  return {
    file,
    errors: [
      `has the same content as ${source}, which ${baseTag} already released, so it would announce that change again: ` +
        'delete it, or write the new change in it.',
    ],
  };
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
  const released = releasedIndex(root, baseTag);
  const hashes = hashFiles(
    root,
    fragments.map((fragment) => fragment.file),
  );
  const selected = [];
  const problems = [];
  for (const [index, fragment] of fragments.entries()) {
    const problem = releasedProblem(released, fragment.file, hashes[index]);
    if (problem) problems.push(problem);
    else if (!released.atBase.has(fragment.file)) selected.push(fragment);
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
  const found = sections(fragments);
  for (const { type, title, group } of found) {
    lines.push(`### ${title}`, '');
    for (const fragment of group) {
      lines.push(entry(fragment, repoUrl));
      if (type === 'breaking') lines.push('', `  **Migration:** ${oneParagraph(fragment.data.migration)}`, '');
    }
    if (type !== 'breaking') lines.push('');
  }
  if (found.length === 0 && !lead) lines.push('No change fragments were added for this release.', '');
  return `${lines.join('\n').trimEnd()}\n`;
}

/** The sections that have entries, in SECTIONS order, each with its entries ordered by scope, then file name. */
function sections(fragments) {
  return SECTIONS.map(([type, title]) => ({
    type,
    title,
    group: fragments
      .filter((fragment) => fragment.data.type === type)
      .sort((a, b) => (a.data.scope || '').localeCompare(b.data.scope || '', 'en') || a.name.localeCompare(b.name, 'en')),
  })).filter(({ group }) => group.length > 0);
}

// The shortened forms of the block, longest first, each with the notice that
// says what it leaves out; `full` is where the full notes are.
const SHORT_NOTICES = {
  compact: (full) =>
    '> **Shortened to fit this page.** Each entry gives only its scope and the first sentence of its summary. ' +
    `The full notes, with each migration and the linked issues and pull requests, are in ${full}.`,
  outline: (full) =>
    '> **Shortened to fit this page.** Each section gives only its number of changes, and each breaking change ' +
    `only its scope and the first sentence of its summary. The full notes, with each migration, are in ${full}.`,
  counts: (full) => `> **Shortened to fit this page.** Each section gives only its number of changes. The full notes are in ${full}.`,
};
const SHORT_FORMS = Object.keys(SHORT_NOTICES);

/** The first sentence of a paragraph: up to the first ".", "!" or "?" outside a code span that ends a word, else all of it. */
function firstSentence(text) {
  const paragraph = oneParagraph(text);
  let code = false;
  for (let index = 0; index < paragraph.length; index += 1) {
    const char = paragraph[index];
    if (char === '`') code = !code;
    if (code || !'.!?'.includes(char) || /\S/.test(paragraph[index + 1] || ' ')) continue;
    if (!/\b(?:e\.g|i\.e)$/i.test(paragraph.slice(0, index))) return paragraph.slice(0, index + 1);
  }
  return paragraph;
}

/**
 * The block in one of SHORT_FORMS, for a page too small for it: the version
 * heading, the lead paragraph (not in counts), the notice, and every
 * section heading. compact gives each entry its scope and its first
 * sentence; outline gives each section its number of entries and lists its
 * breaking changes as compact does; counts gives the numbers only.
 *
 * @returns {string} the block, ending with one newline
 */
function shortBlock({ version, baseTag, date, fragments, repoUrl, form, full }) {
  const lines = [`## [${version}](${compareUrl(repoUrl, baseTag, version)}) (${date})`, ''];
  const lead = fragments.find((fragment) => fragment.data.type === 'lead');
  if (lead && form !== 'counts') lines.push(oneParagraph(lead.data.summary), '');
  lines.push(SHORT_NOTICES[form](full), '');
  for (const { type, title, group } of sections(fragments)) {
    lines.push(`### ${title}`, '');
    if (form !== 'compact') lines.push(`${group.length} ${group.length === 1 ? 'change' : 'changes'}.`, '');
    if (form === 'compact' || (form === 'outline' && type === 'breaking')) {
      for (const { data } of group) lines.push(`- ${data.scope ? `**${data.scope.trim()}:** ` : ''}${firstSentence(data.summary)}`);
      lines.push('');
    }
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

/**
 * Where the full notes of a release stay, as a Markdown link: its block in
 * CHANGELOG.md at its tag, under the heading's anchor (GitHub renders a
 * Markdown file there in full well past the 537,000 characters CHANGELOG.md
 * reaches with 3.0.0), or, for a prerelease, which has no block, the change
 * fragments at its tag.
 */
function fullNotesLink({ version, date, repoUrl }) {
  if (semver.prerelease(version)) {
    return `the change fragments in [changes/ at v${version}](${repoUrl}/tree/v${version}/changes), one file per entry`;
  }
  const anchor = `${version} (${date})`
    .toLowerCase()
    .replaceAll(/[^\w\- ]/g, '')
    .replaceAll(' ', '-');
  return `[CHANGELOG.md at v${version}](${repoUrl}/blob/v${version}/CHANGELOG.md#${anchor})`;
}

/**
 * `text` when it fits `budget`, else its longest run of whole lines that
 * fits with `note` after it (or alone, when the note does not fit either).
 * With `bytes`, sizes are UTF-8 bytes.
 */
function cutToFit(text, budget, note, bytes = false) {
  const size = (part) => (bytes ? Buffer.byteLength(part) : part.length);
  if (size(text) <= budget) return text;
  const tail = size(note) + 3 <= budget ? `\n\n${note}\n` : '';
  const room = budget - size(tail);
  // A byte prefix can end inside a character; the cut at its last line break drops that part.
  const prefix = bytes ? Buffer.from(text).subarray(0, room).toString() : text.slice(0, room);
  return `${text.slice(0, Math.max(prefix.lastIndexOf('\n'), 0))}${tail}`;
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

/**
 * The GitHub Release body that fits `budget`: renderNotes when it does
 * (every release before 3.0.0), else renderNotes of the first form of
 * SHORT_FORMS that does, linking to the full notes (fullNotesLink).
 *
 * @returns {{notes: string, form: string, fullLength: number}} the body, the form used ('full', a short form, or 'cut'), and the length of the full body
 */
function fitNotes({ block, version, baseTag, date, fragments, repoUrl, packageName, budget = NOTES_BUDGET }) {
  const notesOf = (text) => renderNotes({ block: text, version, baseTag, repoUrl, packageName });
  const full = notesOf(block);
  if (full.length <= budget) return { notes: full, form: 'full', fullLength: full.length };
  const link = fullNotesLink({ version, date, repoUrl });
  let notes = full;
  for (const form of SHORT_FORMS) {
    notes = notesOf(shortBlock({ version, baseTag, date, fragments, repoUrl, form, full: link }));
    if (notes.length <= budget) return { notes, form, fullLength: full.length };
  }
  return {
    notes: cutToFit(notes, budget, `(Cut to fit a GitHub Release: the full notes are in ${link}.)`),
    form: 'cut',
    fullLength: full.length,
  };
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

const SURFACE_TITLES = {
  hard: 'Hard (a breaking fragment names each one):',
  additive: 'Additive:',
  review: 'Review (never fails; decide whether each one needs a note):',
};
const NO_REASON = '- no fragment or surface change sets one';
const reasonLine = (reason) => `- ${reason.level}: ${reason.text}`;

/** The heading, the step, an optional notice and the checklist of the review. */
function reviewHead({ version, baseTag, gate }, notice = []) {
  return [
    '## Review before approving',
    '',
    `v${version} is a ${gate.reached} step from ${baseTag || 'the last release'}; the change fragments and covered surfaces need at least ${gate.floor.level}.`,
    '',
    ...notice,
    'Approve only when:',
    '',
    '- [ ] each breaking change says what stopped working and gives a migration a user can follow;',
    '- [ ] each surface change below is described by a fragment of the right type, or needs no note;',
    '- [ ] the notes below read well as the GitHub Release page (it adds Installation and the compare link).',
    '',
  ];
}

/** The "Review before approving" section in full: every reason, every surface change and the notes. The run summary shows it. */
function fullReview({ version, baseTag, gate, surfaces, block }) {
  const { reasons } = gate.floor;
  const lines = [
    ...reviewHead({ version, baseTag, gate }),
    `### Why the minimum is ${gate.floor.level}`,
    '',
    ...(reasons.length === 0 ? [NO_REASON] : reasons.map(reasonLine)),
    '',
  ];
  if (surfaces) {
    lines.push(`### Surface changes since ${baseTag || 'the last release'}`, '');
    for (const group of ['hard', 'additive', 'review']) lines.push(SURFACE_TITLES[group], '', ...surfaceList(surfaces, group), '');
  } else {
    lines.push('No stable release tag was found, so the covered surfaces were not compared.', '');
  }
  lines.push(demoteHeadings(block.trimEnd()), '');
  return lines.join('\n');
}

/**
 * The "Review before approving" section of the bot PR: fullReview when it
 * fits `budget` (every release before 3.0.0), else shortReview.
 */
function renderReview(input) {
  const full = fullReview(input);
  return full.length <= (input.budget || REVIEW_BUDGET) ? full : shortReview(input);
}

/** "77 major, 805 minor and 121 patch reasons", highest level first. */
function countReasons(reasons) {
  const counts = LEVELS.toReversed().map((level) => [level, reasons.filter((reason) => reason.level === level).length]);
  const named = counts.filter(([, count]) => count > 0).map(([level, count]) => `${count} ${level}`);
  return `${andList(named)} ${reasons.length === 1 ? 'reason' : 'reasons'}`;
}

/** The first lines that fit in `budget` characters, one line break each. */
function linesWithin(lines, budget) {
  const shown = [];
  let size = 0;
  for (const line of lines) {
    size += line.length + 1;
    if (size > budget) break;
    shown.push(line);
  }
  return shown;
}

// The log group runRelease prints the full review in when the review is shortened.
const FULL_REVIEW_GROUP = 'The full review';

/**
 * The review shortened to fit `budget`: the checklist in full, a notice that
 * points to the full review of the run at `runUrl` (its log, while the bot
 * PR waits: GitHub shows a job's summary only once the job ends), and each
 * part at the longest of its forms that still fits, tried in this order:
 * the reasons at the minimum level (up to a third of the budget), the hard
 * surface changes, the notes (full, then each of SHORT_FORMS), every reason,
 * the additive and then the review surface changes. A part that does not
 * fit is only counted.
 */
function shortReview({ version, baseTag, gate, surfaces, block, fragments, date, repoUrl, runUrl = null, budget = REVIEW_BUDGET }) {
  const where = runUrl ? 'the full review' : 'the output of `npm run changes:preview`';
  const notice = [
    runUrl
      ? '> **Shortened to fit a pull request body.** The full review, with every reason, every surface change and the full notes, ' +
        `is in the log of [the release run](${runUrl}), in the group "${FULL_REVIEW_GROUP}", and in its summary once the job ends.`
      : `> **Shortened to fit a pull request body.** Every reason, every surface change and the full notes are in ${where}.`,
    '',
  ];
  const { reasons } = gate.floor;
  const top = linesWithin(reasons.filter((reason) => reason.level === gate.floor.level).map(reasonLine), Math.floor(budget / 3));
  const more = reasons.slice(top.length);
  const counted = (count) => (count === 0 ? '- none' : `- ${count} ${count === 1 ? 'change' : 'changes'}, listed in ${where}.`);
  const surfaceForms = (group) => (surfaces ? [counted(surfaces[group].length), surfaceList(surfaces, group).join('\n')] : []);
  const notesIn = (form) => demoteHeadings(shortBlock({ version, baseTag, date, fragments, repoUrl, form, full: where }).trimEnd());
  // Each part's forms, shortest first.
  const forms = {
    why:
      reasons.length === 0
        ? [NO_REASON]
        : [
            `- ${countReasons(reasons)}, listed in ${where}.`,
            [...top, ...(more.length > 0 ? [`- ${countReasons(more)} more, listed in ${where}.`] : [])].join('\n'),
            reasons.map(reasonLine).join('\n'),
          ],
    hard: surfaceForms('hard'),
    additive: surfaceForms('additive'),
    review: surfaceForms('review'),
    notes: [...SHORT_FORMS.toReversed().map((form) => notesIn(form)), demoteHeadings(block.trimEnd())],
  };
  const pick = { why: 0, hard: 0, additive: 0, review: 0, notes: 0 };
  const text = () => {
    const lines = [
      ...reviewHead({ version, baseTag, gate }, notice),
      `### Why the minimum is ${gate.floor.level}`,
      '',
      forms.why[pick.why],
      '',
    ];
    if (surfaces) {
      const total = `${surfaces.hard.length} hard, ${surfaces.additive.length} additive and ${surfaces.review.length} to review.`;
      lines.push(`### Surface changes since ${baseTag || 'the last release'}`, '', total, '');
      for (const group of ['hard', 'additive', 'review']) lines.push(SURFACE_TITLES[group], '', forms[group][pick[group]], '');
    } else {
      lines.push('No stable release tag was found, so the covered surfaces were not compared.', '');
    }
    lines.push(forms.notes[pick.notes], '');
    return lines.join('\n');
  };
  const steps = [
    ['why', 1],
    ['hard', 1],
    ['notes', 3],
    ['notes', 2],
    ['notes', 1],
    ['why', 2],
    ['additive', 1],
    ['review', 1],
  ];
  for (const [part, form] of steps) {
    if (pick[part] >= form || form >= forms[part].length) continue;
    const before = pick[part];
    pick[part] = form;
    if (text().length > budget) pick[part] = before;
  }
  return cutToFit(text(), budget, '(Cut to fit a pull request body: the notice at the top says where the full review is.)');
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
  const fitted = fitNotes({ block, version, baseTag, date, fragments: valid, repoUrl, packageName: pkg.name });
  fs.writeFileSync(notesPath, fitted.notes);
  const notesFile = path.relative(root, notesPath);
  written.push(notesFile);
  const notices = [];
  // Shortened texts and what they leave out, shown in the log while the bot PR waits.
  const groups = [];
  if (fitted.form !== 'full') {
    notices.push(
      `The full notes run to ${fitted.fullLength} characters, over the ${NOTES_BUDGET} kept for a GitHub Release body ` +
        `(GitHub's limit is ${RELEASE_BODY_LIMIT}): ${notesFile} holds the ${fitted.form} form (${fitted.notes.length} characters), ` +
        `which links to the full notes. The log shows it in the group "${notesFile}".`,
    );
    groups.push([notesFile, fitted.notes]);
  }
  const reviewArg = argValue(argv, '--review');
  if (reviewArg) {
    const reviewPath = path.resolve(root, reviewArg);
    const input = { version, baseTag, gate, surfaces, block, fragments: valid, date, repoUrl, runUrl: runUrlOf(env) };
    const full = fullReview(input);
    const review = renderReview(input);
    fs.writeFileSync(reviewPath, review);
    written.push(path.relative(root, reviewPath));
    const cut = '(Cut to fit the run summary: run `npm run changes:preview` for the full text.)';
    writeStepSummary(env, [cutToFit(full, SUMMARY_BUDGET, cut, true)]);
    if (review !== full) {
      notices.push(
        `The full review runs to ${full.length} characters, over the ${REVIEW_BUDGET} kept for a pull request body ` +
          `(GitHub's limit is ${PR_BODY_LIMIT}): ${path.relative(root, reviewPath)} is shortened (${review.length} characters). ` +
          `The log shows the full review in the group "${FULL_REVIEW_GROUP}", and the run summary holds it.`,
      );
      groups.push([FULL_REVIEW_GROUP, full]);
    }
  }
  console.log(`Release ${version} from ${valid.length} change fragment(s) since ${baseTag || 'the start'}. Wrote ${written.join(', ')}.`);
  for (const notice of notices) {
    console.log(notice);
    annotate(env, 'notice', notice);
  }
  if (env.GITHUB_ACTIONS === 'true') {
    // The texts quote the fragments: no line of theirs is read as a workflow command.
    const token = crypto.randomUUID();
    for (const [title, text] of groups)
      console.log(`::group::${title}\n::stop-commands::${token}\n${text.trimEnd()}\n::${token}::\n::endgroup::`);
  }
  if (gate.prerelease) console.log('A prerelease leaves CHANGELOG.md alone: its fragments are rendered again for the stable release.');
  return 0;
}

/** The URL of this GitHub Actions run, or null outside one. */
function runUrlOf(env) {
  const { GITHUB_SERVER_URL: server, GITHUB_REPOSITORY: repository, GITHUB_RUN_ID: run } = env;
  return server && repository && run ? `${server}/${repository}/actions/runs/${run}` : null;
}

// --- Pull request check ---

// The code the npm package ships, and .npmignore, which decides what ships: a
// branch that changes one of these needs a change fragment, or a
// "Changelog: none (<reason>)" line in one of its commit messages. The
// package also ships package.json, README.md and docs/, which are not
// checked: a change a user notices there still takes a fragment.
const SHIPPED_PATHS = [/^src\//, /^tools\/cli\//, /^tools\/skf-npx-wrapper\.js$/, /^\.npmignore$/];
const SHIPPED_PATHSPECS = ['src', 'tools/cli', 'tools/skf-npx-wrapper.js', '.npmignore'];
// release.yaml pushes its release commit to release/bot/vX.Y.Z-<run id>-<run attempt>.
const BOT_BRANCH = /^release\/bot\//;
const TRAILER_LINE = /^changelog\s*:(.*)$/i;
const TRAILER_NONE = /^none\s*\((.*)\)$/i;
// The reason as the tool's own messages print it, pasted unchanged: no reason at all.
const TRAILER_PLACEHOLDER = /^<[^>]*>$/;
const TRAILER_FORM = '`Changelog: none (<reason>)`';
const NO_FINDINGS = { hard: [], additive: [], review: [] };
const PR_SUMMARY_TITLE = '### Change fragments for this pull request';

/** True for a file of the code the npm package ships, or .npmignore, which decides what it ships. */
function isShipped(file) {
  return SHIPPED_PATHS.some((pattern) => pattern.test(file));
}

/** "a", "a and b", "a, b and c". */
function andList(items) {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
}

/** The first few items of a list: "a, b, c and 4 more". */
function someOf(items, shown = 3) {
  return items.length <= shown ? items.join(', ') : `${items.slice(0, shown).join(', ')} and ${items.length - shown} more`;
}

/**
 * The "Changelog: none (<reason>)" lines of the branch's commit messages,
 * and the lines that start "Changelog:" in any other shape (no reason, the
 * `<reason>` placeholder itself, or not "none"), which cover nothing.
 *
 * @param {{commit: string, message: string}[]} commits
 * @returns {{waivers: {commit: string, reason: string}[], malformed: {commit: string, line: string}[]}}
 */
function changelogTrailers(commits) {
  const waivers = [];
  const malformed = [];
  for (const { commit, message } of commits) {
    for (const raw of message.split('\n')) {
      const line = raw.trim();
      const key = TRAILER_LINE.exec(line);
      if (!key) continue;
      const none = TRAILER_NONE.exec(key[1].trim());
      const reason = none ? none[1].trim() : '';
      if (reason && !TRAILER_PLACEHOLDER.test(reason)) waivers.push({ commit, reason });
      else malformed.push({ commit, line });
    }
  }
  return { waivers, malformed };
}

/** Fragments whose type could be read, invalid ones included (their errors are reported on their own). */
function typedFragments(fragments) {
  return fragments.filter((fragment) => fragment.data && TYPES.includes(fragment.data.type));
}

/** An unreleased fragment the branch edits rather than adds (a fragment with no status counts as added). */
const isEdited = (fragment) => fragment.status !== undefined && fragment.status !== 'A';

/**
 * True when `fragment` covers the covered-surface `finding` of `group`: a
 * removal needs a breaking fragment that names it in backticks; an addition
 * needs an added or breaking fragment the branch adds, or one it edits that
 * names it in backticks.
 */
function coversFinding(fragment, group, finding) {
  const { type } = fragment.data;
  if (group === 'hard') return type === 'breaking' && namesToken(fragment, finding.token);
  return (type === 'added' || type === 'breaking') && (!isEdited(fragment) || namesToken(fragment, finding.token));
}

/**
 * What a branch is missing and what it must fix. A fragment the branch adds
 * (status A, or no status) counts for every rule. An unreleased fragment it
 * only edits (another status) counts only for the covered items it names in
 * backticks, and stands in for a fragment of its own only when it names one:
 * otherwise editing someone else's pending fragment would cover anything.
 *
 * @param {object} input
 * @param {string[]} input.touched - The files the branch changes in the code the package ships (see isShipped)
 * @param {object[]} input.fragments - The fragments it adds, and the unreleased ones it edits, parsed, each with its status
 * @param {{file: string, errors: string[]}[]} [input.problems] - Files it adds to changes/ that are not usable fragments
 * @param {{hard: object[], additive: object[], review: object[]}|null} [input.surfaces] - Covered-surface findings, merge base to HEAD
 * @param {{waivers: object[], malformed: object[]}} [input.trailers] - Its "Changelog:" commit-message lines
 * @returns {{failures: string[], missing: {fragment: boolean, hard: object[], additive: object[]}, template: string|null}}
 */
function evaluatePullRequest({ touched, fragments, problems = [], surfaces = null, trailers = { waivers: [], malformed: [] } }) {
  const failures = [];
  for (const { file, errors } of [...problems, ...fragments]) {
    for (const error of errors) failures.push(`${file}: ${error}`);
  }
  const typed = typedFragments(fragments);
  const edited = typed.filter((fragment) => isEdited(fragment));
  const breaking = typed.filter((fragment) => fragment.data.type === 'breaking');
  const found = surfaces || NO_FINDINGS;
  const coversAny = (fragment) =>
    found.hard.some((finding) => coversFinding(fragment, 'hard', finding)) ||
    found.additive.some((finding) => coversFinding(fragment, 'additive', finding));
  const missing = {
    fragment:
      touched.length > 0 &&
      trailers.waivers.length === 0 &&
      !typed.some((fragment) => fragment.data.type !== 'lead' && (!isEdited(fragment) || coversAny(fragment))),
    hard: found.hard.filter((finding) => !typed.some((fragment) => coversFinding(fragment, 'hard', finding))),
    additive: found.additive.filter((finding) => !typed.some((fragment) => coversFinding(fragment, 'additive', finding))),
  };
  if (missing.fragment) {
    const editedFiles = edited.map((fragment) => fragment.file);
    const onlyEdited =
      editedFiles.length > 0
        ? ` Editing an unreleased fragment (${andList(editedFiles)}) does not count here: an edited fragment counts only for a ` +
          'covered item the branch removes or adds that it names in backticks.'
        : '';
    failures.push(
      `this branch changes the code the package ships (${someOf(touched)}) and adds no change fragment: add one ` +
        "(this check's output gives a template), or, when no user or pipeline can notice any of the branch's changes, " +
        `add a ${TRAILER_FORM} line to one of its commit messages.${onlyEdited}`,
    );
    for (const { commit, line } of trailers.malformed) {
      failures.push(`commit ${commit}: "${line}" covers nothing: write ${TRAILER_FORM}, with the actual reason inside the parentheses.`);
    }
  }
  const notWaived = trailers.waivers.length > 0 ? ' A Changelog: none line never covers a surface change.' : '';
  const named = andList(breaking.map((fragment) => fragment.file));
  for (const finding of missing.hard) {
    failures.push(
      `${finding.text}, and no breaking fragment on this branch names \`${finding.token}\` in backticks: ` +
        `${named ? `name it in ${named}, or add` : 'add'} a breaking fragment that says what changed and gives the migration.${notWaived}`,
    );
  }
  const editedCovering = andList(
    edited.filter((fragment) => fragment.data.type === 'added' || fragment.data.type === 'breaking').map((fragment) => fragment.file),
  );
  for (const finding of missing.additive) {
    const orName = editedCovering ? `, or name \`${finding.token}\` in backticks in ${editedCovering}, which it edits` : '';
    failures.push(
      `${finding.text}, and no added or breaking fragment on this branch covers it: add one that describes it${orName}.${notWaived}`,
    );
  }
  const needed = missing.fragment || missing.hard.length > 0 || missing.additive.length > 0;
  return {
    failures,
    missing,
    template: needed ? fragmentTemplate({ hard: missing.hard, additive: missing.additive, touched }) : null,
  };
}

/** The scope a template names for a file the branch changes. */
function scopeOfPath(file) {
  const workflow = /^src\/(skf-[^/]+)\//.exec(file);
  if (workflow) return workflow[1];
  if (file.startsWith('src/forger/')) return 'skf-forger';
  if (file.startsWith('src/')) return 'all workflows';
  if (file.startsWith('tools/cli/')) return 'installer';
  return 'packaging';
}

/** The scope a template names for a covered-surface finding. */
function scopeOfFinding(finding) {
  if (finding.workflow.startsWith('skf-')) return finding.workflow;
  return finding.workflow === 'preferences' ? 'skf-forger' : 'all workflows';
}

/** One scope line: the workflows by name, up to three, else "all workflows". */
function templateScope(scopes) {
  const unique = [...new Set(scopes)].sort();
  const workflows = unique.filter((scope) => scope.startsWith('skf-'));
  const others = unique.filter((scope) => !scope.startsWith('skf-'));
  const wide = others.includes('all workflows') || workflows.length > 3;
  const scope = [...(wide ? [] : workflows), ...others.filter((name) => name !== 'all workflows')];
  return [...(wide ? ['all workflows'] : []), ...scope].join(', ') || 'all workflows';
}

function itemNames(findings) {
  return [...new Set(findings.map((finding) => `${KINDS[finding.kind] ? KINDS[finding.kind].label : finding.kind} \`${finding.token}\``))];
}

/**
 * A fragment for what the branch is missing, typed and scoped from the
 * covered items it removes or adds, else from the files it changes. Each
 * sentence to rewrite starts with TEMPLATE_MARK, which validateFragment
 * refuses, so the template fails `check` until those sentences are rewritten.
 *
 * @returns {string} YAML, ending with one newline
 */
function fragmentTemplate({ hard = [], additive = [], touched = [] }) {
  let type = 'fixed';
  if (hard.length > 0) type = 'breaking';
  else if (additive.length > 0) type = 'added';
  const findings = [...hard, ...additive];
  const scopes = findings.length > 0 ? findings.map((finding) => scopeOfFinding(finding)) : touched.map((file) => scopeOfPath(file));
  const lines = [
    '# The type is what a user sees: breaking, added, changed, fixed or docs (changes/README.md).',
    `type: ${type}`,
    `scope: ${templateScope(scopes)}`,
    'summary: |',
  ];
  const added = itemNames(additive);
  if (type === 'breaking') {
    const tokens = andList([...new Set(hard.map((finding) => `\`${finding.token}\``))]);
    const adds = added.length > 0 ? ` Adds the ${andList(added)}.` : '';
    lines.push(
      `  Removes the ${andList(itemNames(hard))}.${adds} ${TEMPLATE_MARK}: what a user or a pipeline sees now, and why.`,
      'migration: |',
      `  ${TEMPLATE_MARK}: the exact action a user takes instead of relying on ${tokens}.`,
    );
  } else if (type === 'added') {
    const each = added.length === 1 ? 'it does' : 'each one does';
    lines.push(`  New ${andList(added)}. ${TEMPLATE_MARK}: what ${each}, and when a user needs it.`);
  } else {
    lines.push(`  ${TEMPLATE_MARK}: what a user or a pipeline now sees, with flags, statuses and file names in backticks.`);
  }
  lines.push('# prs: [<pull request number>]', '# issues: [<issue number>]');
  return `${lines.join('\n')}\n`;
}

function inCi(env) {
  return env.GITHUB_ACTIONS === 'true' || env.CI === 'true';
}

/**
 * The base branch and the branch's merge base with it: --base, else
 * origin/$GITHUB_BASE_REF on a pull request, else origin/main.
 */
function resolveBranchBase(root, argv, env) {
  const ref = argValue(argv, '--base') || (env.GITHUB_BASE_REF ? `origin/${env.GITHUB_BASE_REF}` : 'origin/main');
  if (!resolveCommit(root, ref)) {
    throw new ToolError(
      `base ${ref} not found, so the branch cannot be compared with it. Fetch it (git fetch origin; in CI, actions/checkout with fetch-depth: 0) or pass --base <ref>.`,
      2,
    );
  }
  let mergeBase = '';
  try {
    mergeBase = git(root, ['merge-base', ref, 'HEAD']).trim();
  } catch {
    // No commit in common: reported below.
  }
  if (mergeBase) return { ref, mergeBase };
  let shallow = false;
  try {
    shallow = git(root, ['rev-parse', '--is-shallow-repository']).trim() === 'true';
  } catch {
    // An older git: report the plain case.
  }
  if (shallow) {
    throw new ToolError(
      `${ref} and HEAD have no commit in common that this clone has: this clone is shallow, so the merge base is not in it. ` +
        'Fetch the full history (git fetch --unshallow origin; in CI, actions/checkout with fetch-depth: 0), then run the check again.',
      2,
    );
  }
  throw new ToolError(`${ref} and HEAD have no commit in common, so the branch cannot be compared with it.`, 2);
}

/**
 * The last stable tag, for the released-fragment rule, as the other commands
 * find it but reachable from the base branch, so a branch forked before the
 * latest release is checked against it as CI checks it (--tag replaces it).
 */
function resolvePrTag(root, argv, env, baseRef) {
  const tag = argValue(argv, '--tag') || lastStableTag(root, baseRef);
  if (tag && !resolveCommit(root, tag)) throw new ToolError(`ref ${tag} not found.`, 2);
  if (tag) return { tag, warnings: [] };
  if (inCi(env)) {
    throw new ToolError('no stable release tag found. Fetch tags (actions/checkout with fetch-depth: 0) or pass --tag <ref>.', 2);
  }
  return {
    tag: null,
    warnings: [
      'No stable release tag found: the fragments this branch adds or edits were not compared with a release. Fetch tags to fix this.',
    ],
  };
}

/** Each file the branch changes, with its status (A, M, D or T; a rename is a deletion and an addition). */
function branchChanges(root, mergeBase) {
  const fields = git(root, ['diff', '--name-status', '--no-renames', '-z', mergeBase, 'HEAD']).split('\0');
  const changed = [];
  for (let index = 0; index + 1 < fields.length; index += 2) {
    if (fields[index]) changed.push({ status: fields[index][0], file: fields[index + 1] });
  }
  return changed;
}

/**
 * The message of each commit on the branch, merge commits included: the
 * range leaves out every commit of the base branch, and the merge commit CI
 * checks out for a pull request carries no Changelog line.
 */
function branchCommits(root, mergeBase) {
  const log = git(root, ['log', '--format=%H%x1F%B%x1E', `${mergeBase}..HEAD`]);
  const commits = [];
  for (const record of log.split('\u001E')) {
    const [sha, message = ''] = record.replace(/^\s+/, '').split('\u001F');
    if (sha) commits.push({ commit: sha.slice(0, 8), message });
  }
  return commits;
}

/**
 * The fragments the branch adds, and the unreleased ones it edits, read at
 * HEAD and checked as `check` checks them; the other files it adds to
 * changes/ that are not fragments; the fragments it deletes.
 */
function branchFragments(root, changed, stableTag) {
  const released = stableTag ? releasedIndex(root, stableTag) : null;
  const atHead = fragmentBlobsAtRef(root, 'HEAD');
  const fragments = [];
  const problems = [];
  const deleted = [];
  for (const { status, file } of changed) {
    if (!file.startsWith(`${CHANGES_DIR}/`)) continue;
    const name = file.slice(CHANGES_DIR.length + 1);
    if (status === 'D') {
      if (!NOT_FRAGMENTS.has(name)) deleted.push(file);
      continue;
    }
    if (NOT_FRAGMENTS.has(name)) continue;
    if (name.includes('/')) {
      problems.push({ file, errors: [IN_SUBFOLDER] });
      continue;
    }
    if (!name.endsWith('.yaml')) {
      problems.push({ file, errors: [NOT_A_FRAGMENT] });
      continue;
    }
    if (released) {
      const problem = releasedProblem(released, file, atHead.get(file));
      if (problem) {
        problems.push(problem);
        continue;
      }
      // Back to its released content: not a fragment of this branch.
      if (released.atBase.has(file)) continue;
    }
    fragments.push({ ...parseFragment(file, git(root, ['show', `HEAD:${file}`])), status });
  }
  return { fragments, problems, deleted };
}

/** A file name for the template, from the branch name, else <topic>. */
function suggestedFile(root, env) {
  let branch = env.GITHUB_HEAD_REF || '';
  if (!branch) {
    try {
      branch = git(root, ['rev-parse', '--abbrev-ref', 'HEAD']).trim();
    } catch {
      branch = '';
    }
  }
  const slug = branch
    .split('/')
    .at(-1)
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, '-')
    .replaceAll(/^-+|-+$/g, '');
  const file = `${CHANGES_DIR}/${slug}.yaml`;
  if (!slug || slug === 'head' || !FRAGMENT_NAME.test(`${slug}.yaml`) || fs.existsSync(path.join(root, file))) {
    return `${CHANGES_DIR}/<topic>.yaml`;
  }
  return file;
}

/**
 * The exemption of the release branch, and the note to print. It fails
 * closed: only a head repository known to be this repository is exempt, so
 * an empty PR_HEAD_REPO (a deleted fork, or a step that does not pass it) is
 * checked like any other branch.
 */
function botBranch(env) {
  const head = env.GITHUB_HEAD_REF || '';
  if (!BOT_BRANCH.test(head)) return { exempt: false, note: null };
  if (env.PR_HEAD_REPO && env.PR_HEAD_REPO === env.GITHUB_REPOSITORY) {
    return {
      exempt: true,
      note:
        `${head} is the release branch of release.yaml: its release commit only bumps the version and renders the notes ` +
        'from fragments already merged, so it needs no fragment of its own.',
    };
  }
  let why = `it comes from ${env.PR_HEAD_REPO}, not ${env.GITHUB_REPOSITORY}`;
  if (!env.PR_HEAD_REPO) why = 'PR_HEAD_REPO does not say which repository it comes from';
  else if (!env.GITHUB_REPOSITORY) why = `GITHUB_REPOSITORY is not set, so ${env.PR_HEAD_REPO} cannot be confirmed as this repository`;
  return { exempt: false, note: `${head} is named like the release branch, but ${why}, so it is checked like any other branch.` };
}

function surfaceMark(group, finding, typed) {
  if (group === 'review') return null;
  const covering = typed.filter((fragment) => coversFinding(fragment, group, finding)).map((fragment) => fragment.file);
  if (group === 'hard') return covering.length > 0 ? `named in ${andList(covering)}` : 'NOT NAMED in a breaking fragment on this branch';
  return covering.length > 0 ? `covered by ${andList(covering)}` : 'NOT COVERED by an added or breaking fragment on this branch';
}

const PR_GROUP_TITLES = {
  hard: 'Hard (a breaking fragment on the branch names each one)',
  additive: 'Additive (an added or breaking fragment on the branch covers each one)',
  review: 'Review (never fails; decide whether each one needs a note)',
};

function runPr(root, argv, env) {
  const bot = botBranch(env);
  if (bot.exempt) {
    console.log(`Passed without a check: ${bot.note}`);
    writeStepSummary(env, [PR_SUMMARY_TITLE, '', `**Passes.** ${bot.note}`, '']);
    return 0;
  }
  const base = resolveBranchBase(root, argv, env);
  const { tag, warnings } = resolvePrTag(root, argv, env, base.ref);
  if (bot.note) warnings.push(bot.note);
  const uncommitted = git(root, ['status', '--porcelain', '--untracked-files=all', '--', CHANGES_DIR, ...SHIPPED_PATHSPECS]).trim() !== '';
  if (uncommitted) {
    warnings.push(
      'changes under changes/ or in the code the package ships are not committed, and this check reads commits only: ' +
        'commit them, then run it again.',
    );
  }
  const changed = branchChanges(root, base.mergeBase);
  const touched = changed.map((entry) => entry.file).filter((file) => isShipped(file));
  const { fragments, problems, deleted } = branchFragments(root, changed, tag);
  const surfaces = changed.some((entry) => entry.file.startsWith('src/')) ? compareRefs(root, base.mergeBase, 'HEAD') : null;
  const trailers = changelogTrailers(branchCommits(root, base.mergeBase));
  const result = evaluatePullRequest({ touched, fragments, problems, surfaces, trailers });
  const typed = typedFragments(fragments);
  const short = base.mergeBase.slice(0, 8);

  const out = [
    ...warnings.map((warning) => `warning: ${warning}`),
    `Branch: ${base.ref} (merge base ${short}) -> HEAD`,
    `Files changed in the code the package ships: ${touched.length}`,
    ...touched.map((file) => `  ${file}`),
    `Change fragments on this branch: ${fragments.length}`,
    ...(fragments.length > 0
      ? fragmentLines(fragments).map((line, index) => (fragments[index].status === 'A' ? line : `${line}  (edited)`))
      : []),
    ...problems.map(({ file }) => `  ?         ${file}  (not a usable fragment)`),
    ...deleted.map((file) => `  deleted   ${file}`),
    `Changelog: none lines: ${trailers.waivers.length}`,
    ...trailers.waivers.map(({ commit, reason }) => `  commit ${commit}: ${reason}`),
  ];
  if (surfaces) {
    out.push(`Covered surfaces, ${short} -> HEAD:`);
    for (const group of ['hard', 'additive', 'review']) {
      out.push(`  ${group}: ${surfaces[group].length}`);
      for (const finding of surfaces[group]) {
        const mark = surfaceMark(group, finding, typed);
        out.push(`    - ${finding.text}${mark ? `  [${mark}]` : ''}`);
      }
    }
  } else {
    out.push('Covered surfaces: not compared (the branch changes nothing under src/).');
  }
  const file = result.template ? suggestedFile(root, env) : null;
  if (result.failures.length === 0) {
    out.push(
      '',
      uncommitted
        ? 'The branch has the change fragments it needs, in its commits: the uncommitted changes were not read.'
        : 'The branch has the change fragments it needs.',
    );
  } else {
    out.push('', `The branch needs ${result.failures.length} fix(es):`, ...result.failures.map((failure) => `  - ${failure}`));
    if (result.template) out.push('', `A fragment to fill in; save it as ${file}:`, '', '```yaml', result.template.trimEnd(), '```');
    out.push('', 'The fragment format is in changes/README.md. Commit the fix, then run npm run changes:pr again.');
  }
  console.log(out.join('\n'));
  for (const failure of result.failures) annotate(env, 'error', failure);

  const summary = [
    PR_SUMMARY_TITLE,
    '',
    result.failures.length === 0 ? '**Passes.**' : `**Fails:** ${result.failures.length} fix(es) needed.`,
    '',
    ...warnings.map((warning) => `- Warning: ${warning}`),
    `- Base: \`${base.ref}\`, merge base \`${short}\``,
    `- Files changed in the code the package ships: ${touched.length}${touched.length > 0 ? ` (${someOf(touched.map((name) => `\`${name}\``))})` : ''}`,
    `- Change fragments on this branch: ${fragments.length > 0 ? fragments.map((fragment) => `\`${fragment.file}\``).join(', ') : 'none'}`,
    `- \`Changelog: none\` lines: ${trailers.waivers.length > 0 ? trailers.waivers.map(({ commit, reason }) => `${commit} (${reason})`).join('; ') : 'none'}`,
    '',
  ];
  if (result.failures.length > 0) summary.push('**To fix:**', '', ...result.failures.map((failure) => `- ${failure}`), '');
  if (surfaces) {
    summary.push('**Covered-surface changes on this branch**', '');
    for (const group of ['hard', 'additive', 'review']) {
      const items = surfaces[group].map((finding) => {
        const mark = surfaceMark(group, finding, typed);
        return `- ${finding.text}${mark ? ` (${mark})` : ''}`;
      });
      summary.push(`${PR_GROUP_TITLES[group]}:`, '', ...(items.length > 0 ? items : ['- none']), '');
    }
  } else {
    summary.push('Covered surfaces: not compared (the branch changes nothing under `src/`).', '');
  }
  if (result.template)
    summary.push(`**A fragment to fill in**; save it as \`${file}\`:`, '', '```yaml', result.template.trimEnd(), '```', '');
  writeStepSummary(env, summary);
  return result.failures.length > 0 ? 1 : 0;
}

const USAGE = `Usage: node tools/changes.js <command> [options]

  check                        validate changes/ and the empty [Unreleased] of CHANGELOG.md
  preview [--bump <type>]      fragments, surface changes, minimum bump, next version, gate verdict, rendered block
  gate --bump <type>           refuse a version_bump the fragments and surfaces do not allow
  release [--review <file>]    render CHANGELOG.md (stable only) and release_notes.md
  pr [--base <branch>]         check the fragments a branch needs, from its merge base to HEAD

  <type> is one of ${BUMPS.join(', ')}.
  Options: --base <ref>, --root <dir>, and for release --version <v>, --date YYYY-MM-DD,
  --notes <file>, --notes-only; for pr, --base is the base branch (default origin/main,
  or origin/$GITHUB_BASE_REF on a pull request) and --tag <ref> replaces the last stable
  tag. The fragment format is in changes/README.md.`;

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
      case 'pr': {
        return runPr(root, rest, env);
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
    // pr exits 2 on a git failure, so a broken checkout never reads as a branch that lacks a fragment.
    const gitFailure = command === 'pr' && error && error.stderr !== undefined;
    if (!(error instanceof ToolError) && !gitFailure) throw error;
    const message = error instanceof ToolError ? error.message : `git failed: ${String(error.stderr || error.message).trim()}`;
    console.error(`error: ${message}`);
    annotate(env, 'error', message);
    return error instanceof ToolError ? error.exitCode : 2;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  BUMPS,
  NOTES_BUDGET,
  PR_BODY_LIMIT,
  RELEASE_BODY_LIMIT,
  REVIEW_BUDGET,
  STEP_SUMMARY_LIMIT,
  SUMMARY_BUDGET,
  TYPES,
  changelogTrailers,
  cutToFit,
  evaluateGate,
  evaluatePullRequest,
  firstSentence,
  fitNotes,
  fragmentTemplate,
  fullReview,
  insertIntoChangelog,
  isShipped,
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
  shortBlock,
  unreleasedProblem,
  validateFragment,
};
