/**
 * Required Checks
 *
 * Merges to main need every status check the `Default` ruleset lists, and
 * each one must be the name of a check a job of .github/workflows/quality.yaml
 * reports, matrix value included (issue #570). docs/_internal/RELEASING.md
 * holds a third copy of the list, between the required-checks markers. When
 * they drift, nothing else says so: a check the ruleset requires that no job
 * reports blocks every pull request, and keeps a release's bot PR waiting
 * until the Wait for required status checks step of release.yaml times out,
 * after the release commit is pushed; a job the ruleset does not require
 * gates nothing. This tool derives the check names from quality.yaml and
 * compares them with the other two lists.
 *
 * A job reports one check, named by its `name:` or else by its key. A job
 * whose strategy.matrix has one dimension reports one check per value,
 * `<name> (<value>)`, as GitHub names them. The tool stops instead of
 * guessing on a job whose check names it cannot derive: a matrix with
 * several dimensions, with include or exclude, or that is not a mapping of
 * one list of plain strings (an expression, a number GitHub reads its own
 * way); an expression in `name:`; a call to a reusable workflow, whose
 * checks are named after the called jobs.
 *
 * Modes:
 *   (none)       Print the check names, one per line.
 *   --releasing  Compare them with the list between the required-checks
 *                markers of docs/_internal/RELEASING.md (one "- `name`" item
 *                per line). `npm run test:docs-links-tool` runs this, so the
 *                required validate job of quality.yaml checks it on every
 *                pull request, with no token, and so does `npm test`.
 *   --ruleset    Compare them with the required status checks of the live
 *                `Default` ruleset, found by name as the Wait for required
 *                status checks step does, through gh (GH_TOKEN in Actions).
 *                release.yaml runs this on a main dispatch after the tests
 *                and before Bump version, so drift stops the release before
 *                anything is committed or pushed. A failed lookup is tried
 *                again, six times ten seconds apart (tools/release-state.js
 *                does the lookup).
 *
 * Usage:
 *   node tools/check-required-checks.js
 *   node tools/check-required-checks.js --releasing
 *   node tools/check-required-checks.js --ruleset [--repo <owner/repo>]
 *
 * --repo defaults to $GITHUB_REPOSITORY; --root <dir> reads another checkout
 * (the tests use this). In GitHub Actions each problem is also an error
 * annotation.
 *
 * Exit codes:
 *   0  the lists agree (with no mode: the names were printed)
 *   1  they differ: each check missing from a list and each extra one is
 *      named
 *   2  cannot run: a bad argument, quality.yaml or the RELEASING.md list
 *      missing or in a shape the tool does not handle, or a ruleset lookup
 *      that kept failing
 */

const fs = require('node:fs');
const path = require('node:path');
// Dev-only tool: yaml is a devDependency (the validate job and release.yaml
// run npm ci first).
const YAML = require('yaml');

const WORKFLOW = '.github/workflows/quality.yaml';
const RELEASING = 'docs/_internal/RELEASING.md';
const START = '<!-- required-checks:start -->';
const END = '<!-- required-checks:end -->';
const ITEM = /^- `([^`]+)`$/;
const EXPRESSION = '${{';
const RULESET = 'Default';
const SECTION = `${RELEASING}, Branch Protection on main`;

class CannotRun extends Error {
  constructor(message) {
    super(message);
    this.exitCode = 2;
  }
}

function isMapping(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readText(root, file) {
  try {
    return fs.readFileSync(path.join(root, file), 'utf8');
  } catch {
    throw new CannotRun(`${file} not found under ${root}.`);
  }
}

// --- quality.yaml ---

/** The checks one job reports, as {checks} or {problem}. */
function jobChecks(key, job) {
  if (!isMapping(job)) return { problem: 'the job is not a mapping' };
  if (job.uses !== undefined) return { problem: 'it calls a reusable workflow, whose checks are named after the called jobs' };
  if (job.name !== undefined && typeof job.name !== 'string') return { problem: '`name:` is not a string' };
  const name = job.name === undefined ? key : job.name.trim();
  if (name === '') return { problem: '`name:` is empty' };
  if (name.includes(EXPRESSION)) return { problem: `\`name:\` holds an expression (${name})` };
  if (job.strategy === undefined) return { checks: [name] };
  if (!isMapping(job.strategy)) return { problem: '`strategy:` is not a mapping' };
  const { matrix } = job.strategy;
  if (matrix === undefined) return { checks: [name] };
  if (!isMapping(matrix)) return { problem: 'its matrix is not a mapping (an expression?)' };
  const dimensions = Object.keys(matrix);
  for (const special of ['include', 'exclude']) {
    if (dimensions.includes(special)) return { problem: `its matrix has ${special}` };
  }
  if (dimensions.length !== 1) return { problem: `its matrix has ${dimensions.length} dimensions (${dimensions.join(', ')}), not one` };
  const [dimension] = dimensions;
  const values = matrix[dimension];
  if (!Array.isArray(values) || values.length === 0) return { problem: `matrix.${dimension} is not a list of values` };
  const odd = values.find((value) => typeof value !== 'string' || value.trim() === '' || value.includes(EXPRESSION));
  if (odd !== undefined) {
    return {
      problem: `matrix.${dimension} holds ${JSON.stringify(odd)}, which is not a plain string (quote a number: GitHub names it its own way)`,
    };
  }
  return { checks: values.map((value) => `${name} (${value})`) };
}

/**
 * The check names the jobs of a quality.yaml text report, in job order.
 * Throws CannotRun naming every job whose names it cannot derive.
 */
function expectedChecks(text, file = WORKFLOW) {
  let workflow;
  try {
    workflow = YAML.parse(text);
  } catch (error) {
    throw new CannotRun(`${file} is not valid YAML: ${String(error.message).split('\n')[0]}`);
  }
  const jobs = isMapping(workflow) ? workflow.jobs : undefined;
  if (!isMapping(jobs) || Object.keys(jobs).length === 0) throw new CannotRun(`${file} has no jobs.`);
  const checks = [];
  const problems = [];
  for (const [key, job] of Object.entries(jobs)) {
    const result = jobChecks(key, job);
    if (result.problem) problems.push(`job \`${key}\`: ${result.problem}`);
    else checks.push(...result.checks);
  }
  if (problems.length > 0) {
    throw new CannotRun(
      `${file}: cannot tell which checks these jobs report, so nothing was compared (teach tools/check-required-checks.js the shape first):\n` +
        problems.map((problem) => `  - ${problem}`).join('\n'),
    );
  }
  return [...new Set(checks)];
}

// --- docs/_internal/RELEASING.md ---

/**
 * The check names listed between the required-checks markers of a
 * RELEASING.md text, and the 1-based line of the start marker. Throws
 * CannotRun when the markers are not one start line then one end line, or a
 * line between them is neither blank nor a "- `name`" item.
 */
function documentedChecks(text, file = RELEASING) {
  const lines = text.split(/\r?\n/);
  const at = (marker) => lines.flatMap((line, index) => (line.trim() === marker ? [index] : []));
  const starts = at(START);
  const ends = at(END);
  if (starts.length !== 1 || ends.length !== 1 || ends[0] < starts[0]) {
    throw new CannotRun(`${file} needs one ${START} line, then one ${END} line, around the list of required checks.`);
  }
  const checks = [];
  const problems = [];
  for (let index = starts[0] + 1; index < ends[0]; index += 1) {
    const line = lines[index].trim();
    if (line === '') continue;
    const match = ITEM.exec(line);
    if (match) checks.push(match[1]);
    else problems.push(`${file}:${index + 1}: not a "- \`check name\`" item: ${line}`);
  }
  if (problems.length > 0) {
    throw new CannotRun(`The list of required checks in ${file} cannot be read:\n${problems.map((problem) => `  ${problem}`).join('\n')}`);
  }
  return { checks, line: starts[0] + 1 };
}

// --- Comparison ---

/**
 * What `actual` gets wrong against `expected`: the expected names it lacks
 * (missing), in expected order, the names it has that are not expected
 * (extra), and the names it holds more than once (repeated), each in its
 * own order.
 */
function compareChecks(expected, actual) {
  const want = new Set(expected);
  const have = new Set(actual);
  return {
    missing: expected.filter((name) => !have.has(name)),
    extra: [...have].filter((name) => !want.has(name)),
    repeated: [...new Set(actual.filter((name, index) => actual.indexOf(name) !== index))],
  };
}

function names(list) {
  return list.map((name) => `\`${name}\``).join(', ');
}

function annotate(env, message, where = '') {
  if (env.GITHUB_ACTIONS === 'true') console.log(`::error${where}::${message.replaceAll('\n', ' ')}`);
}

function report(env, { title, rows, fix, pass, where }) {
  const lines = rows.filter(([, list]) => list.length > 0).map(([label, list]) => `  ${label}: ${names(list)}`);
  if (lines.length === 0) {
    console.log(pass);
    return 0;
  }
  const message = `${title}:\n${lines.join('\n')}\n${fix}`;
  console.log(message);
  annotate(env, message, where);
  return 1;
}

function checkReleasing(root, expected, env) {
  const { checks, line } = documentedChecks(readText(root, RELEASING));
  const { missing, extra, repeated } = compareChecks(expected, checks);
  return report(env, {
    title: `${RELEASING} and ${WORKFLOW} disagree on the required checks`,
    rows: [
      ['missing from the list (a quality.yaml job reports it)', missing],
      ['listed, but no quality.yaml job reports it', extra],
      ['listed more than once', repeated],
    ],
    fix:
      `Make the list between ${START} and ${END} name each check the jobs of ${WORKFLOW} report, and update the ` +
      `required status checks of the ${RULESET} ruleset with it (${SECTION}).`,
    pass: `${RELEASING} lists the ${expected.length} checks the jobs of ${WORKFLOW} report: ${names(expected)}.`,
    where: ` file=${RELEASING},line=${line}`,
  });
}

function checkRuleset(root, expected, repo, env, io) {
  if (!repo) throw new CannotRun('--ruleset needs --repo <owner/repo> or $GITHUB_REPOSITORY.');
  // release-state.js reads the ruleset for the resume path; it needs semver
  // and changes.js, so it is loaded only here.
  const releaseState = require('./release-state.js');
  const required = releaseState.requiredContexts(io || releaseState.defaultIo(root), repo);
  const { missing, extra } = compareChecks(expected, required);
  return report(env, {
    title: `The ${RULESET} ruleset of ${repo} and ${WORKFLOW} disagree on the required checks`,
    rows: [
      ['reported by a quality.yaml job, but not required, so it gates nothing', missing],
      [
        'required, but no quality.yaml job reports it, so every pull request waits for it, and the bot PR until the Wait for required status checks step times out',
        extra,
      ],
    ],
    fix:
      `Update the required status checks of the ${RULESET} ruleset or ${WORKFLOW} so that they agree, and the list in ` +
      `${RELEASING} with them (${SECTION}).`,
    pass: `The ${RULESET} ruleset of ${repo} requires the ${expected.length} checks the jobs of ${WORKFLOW} report: ${names(expected)}.`,
  });
}

// --- Command ---

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1] || null;
}

const USAGE = `Usage: node tools/check-required-checks.js [--releasing] [--ruleset [--repo <owner/repo>]]

  (no mode)    print the check names the jobs of ${WORKFLOW} report
  --releasing  compare them with the list between the required-checks markers of ${RELEASING}
  --ruleset    compare them with the required status checks of the live ${RULESET} ruleset (gh)

  --repo defaults to $GITHUB_REPOSITORY; --root <dir> reads another checkout.
  Exit 0: they agree; 1: they differ, each missing and extra check named; 2: cannot run.`;

const FLAGS = new Set(['--releasing', '--ruleset']);
const VALUE_FLAGS = new Set(['--repo', '--root']);

function main(argv = process.argv.slice(2), env = process.env, io = null) {
  if (argv.includes('--help') || argv.includes('-h')) {
    console.log(USAGE);
    return 0;
  }
  for (let index = 0; index < argv.length; index += 1) {
    if (VALUE_FLAGS.has(argv[index]) && argv[index + 1] !== undefined) index += 1;
    else if (!FLAGS.has(argv[index])) {
      console.error(`Unknown or incomplete argument: ${argv[index]}\n\n${USAGE}`);
      return 2;
    }
  }
  const root = path.resolve(argValue(argv, '--root') || path.join(__dirname, '..'));
  try {
    const expected = expectedChecks(readText(root, WORKFLOW));
    const modes = [];
    if (argv.includes('--releasing')) modes.push(() => checkReleasing(root, expected, env));
    if (argv.includes('--ruleset')) {
      const repo = argValue(argv, '--repo') || env.GITHUB_REPOSITORY;
      modes.push(() => checkRuleset(root, expected, repo, env, io));
    }
    if (modes.length === 0) {
      console.log(expected.join('\n'));
      return 0;
    }
    return Math.max(...modes.map((mode) => mode()));
  } catch (error) {
    // release-state.js throws its own error class, with the same exitCode.
    if (!error || !Number.isInteger(error.exitCode)) throw error;
    console.error(`error: ${error.message}`);
    annotate(env, error.message);
    return error.exitCode;
  }
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { END, RELEASING, START, WORKFLOW, compareChecks, documentedChecks, expectedChecks, jobChecks, main };
