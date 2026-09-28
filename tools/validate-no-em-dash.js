/**
 * Em Dash Validator
 *
 * The project writes no em dashes (U+2014). This tool enforces that rule on
 * the published docs as a whole and on every new line anywhere else.
 *
 * What it checks:
 * - Clean set: every tracked text file in README.md, docs/ (except
 *   docs/_internal/) and website/ holds no em dash at all. These files are
 *   already clean, so any em dash in them is a regression.
 * - Added lines: every line the branch adds, anywhere in the repository,
 *   compared with its merge base on the base branch. Existing lines outside
 *   the clean set are left alone until someone edits them.
 * - Commit messages: every non-merge commit on the branch since that merge base.
 *
 * An em dash is the character itself or an HTML entity that renders it (the
 * named entity mdash, or the decimal 8212 and hex 2014 numeric references).
 * One line shape is exempt: the context-snippet lines
 * SKF writes into every generated skill, such as "|IMPORTANT: ..." and
 * "|key-types:SKILL.md#key-types ...". They start with a pipe followed
 * directly by a key and a colon (a Markdown table row starts "| " and stays
 * checked). SKF's snippet format still puts an em dash in them, and docs quote
 * them verbatim.
 *
 * Not checked: CHANGELOG.md and any package-lock.json. Tools generate them,
 * and the changelog is built from commit subjects older than this rule.
 *
 * Base branch for the added-lines and commit checks: --base <ref>, else
 * $EM_DASH_BASE, else origin/$GITHUB_BASE_REF on a pull request, else
 * origin/main. When the base cannot be resolved, a CI run fails (exit 2),
 * because a skipped check would pass silently. A local run skips those two
 * checks and says so.
 *
 * Usage:
 *   node tools/validate-no-em-dash.js                  # Report findings (exit 0)
 *   node tools/validate-no-em-dash.js --strict         # Exit 1 on any finding
 *   node tools/validate-no-em-dash.js --base <ref>     # Diff against <ref>
 *   node tools/validate-no-em-dash.js --root <dir>     # Check another checkout (its tests use this)
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

// Assembled from parts so that this file does not trip its own check.
const AMP = '&';
const EM_DASH = new RegExp(`${String.fromCodePoint(0x20_14)}|${AMP}mdash;|${AMP}#8212;|${AMP}#x2014;`, 'i');
const EXEMPT_LINE = /^\s*\|[A-Za-z][\w-]*:/;
const CLEAN_SET = ['README.md', 'docs/', 'website/'];
const CLEAN_SET_EXCLUDED = ['docs/_internal/'];
const GENERATED = new Set(['CHANGELOG.md', 'package-lock.json']);
const HINT = 'rewrite it with a colon, a comma, parentheses or a new sentence';

function argValue(argv, flag) {
  const index = argv.indexOf(flag);
  return index === -1 ? null : argv[index + 1];
}

/** True when the line holds an em dash and is not an exempt context-snippet line. */
function hasEmDash(line) {
  return EM_DASH.test(line) && !EXEMPT_LINE.test(line);
}

function isGenerated(file) {
  return GENERATED.has(path.posix.basename(file));
}

/** True for repository-relative POSIX paths in the published, fully clean set. */
function inCleanSet(file) {
  if (isGenerated(file)) return false;
  if (CLEAN_SET_EXCLUDED.some((prefix) => file.startsWith(prefix))) return false;
  return CLEAN_SET.some((entry) => (entry.endsWith('/') ? file.startsWith(entry) : file === entry));
}

/**
 * Parse `git diff -U0` output into the added lines that hold an em dash.
 *
 * @param {string} diff - Output of git diff run with --src-prefix=a/ --dst-prefix=b/
 * @returns {{file: string, line: number, text: string}[]}
 */
function findAddedEmDashes(diff) {
  const findings = [];
  let file = null;
  let lineNo = 0;
  for (const raw of diff.split('\n')) {
    const line = raw.replace(/\r$/, '');
    if (line.startsWith('+++ ')) {
      file = line.startsWith('+++ b/') ? line.slice(6) : null;
      continue;
    }
    if (line.startsWith('@@')) {
      const match = /\+(\d+)/.exec(line);
      lineNo = match ? Number(match[1]) : 0;
      continue;
    }
    if (line.startsWith('+') && file) {
      const text = line.slice(1);
      if (!isGenerated(file) && hasEmDash(text)) findings.push({ file, line: lineNo, text });
      lineNo += 1;
    }
  }
  return findings;
}

function makeGit(root) {
  return (args) =>
    execFileSync('git', ['-c', 'core.quotePath=false', ...args], {
      cwd: root,
      encoding: 'utf8',
      maxBuffer: 256 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
}

function checkCleanSet(root, git) {
  const files = git(['ls-files', '-z']).split('\0').filter(Boolean).filter(inCleanSet);
  const findings = [];
  for (const file of files) {
    let buffer;
    try {
      buffer = fs.readFileSync(path.join(root, file));
    } catch {
      continue; // deleted in the working tree
    }
    if (buffer.includes(0)) continue; // binary
    for (const [index, text] of buffer.toString('utf8').split(/\r?\n/).entries()) {
      if (hasEmDash(text)) findings.push({ file, line: index + 1, text });
    }
  }
  return findings;
}

function resolveBase(git, argv, env) {
  const explicit = argValue(argv, '--base') || env.EM_DASH_BASE;
  const ref = explicit || (env.GITHUB_BASE_REF ? `origin/${env.GITHUB_BASE_REF}` : 'origin/main');
  try {
    git(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`]);
    return { ref, mergeBase: git(['merge-base', ref, 'HEAD']).trim() };
  } catch {
    return { ref, mergeBase: null };
  }
}

function checkAddedLines(git, mergeBase) {
  const diff = git(['diff', '-U0', '--no-color', '--no-ext-diff', '--src-prefix=a/', '--dst-prefix=b/', mergeBase, '--', '.']);
  return findAddedEmDashes(diff).filter((finding) => !inCleanSet(finding.file));
}

function checkCommitMessages(git, mergeBase) {
  const log = git(['log', '--no-merges', '--format=%H%x1f%B%x1e', `${mergeBase}..HEAD`]);
  const findings = [];
  for (const record of log.split('\u001E')) {
    const [sha, body = ''] = record.replace(/^\s+/, '').split('\u001F');
    if (!sha) continue;
    const lines = body.split('\n');
    for (const [index, text] of lines.entries()) {
      if (hasEmDash(text)) findings.push({ commit: sha.slice(0, 8), subject: lines[0], line: index + 1, text });
    }
  }
  return findings;
}

function main(argv = process.argv.slice(2), env = process.env) {
  const root = path.resolve(argValue(argv, '--root') || path.join(__dirname, '..'));
  const strict = argv.includes('--strict');
  const inCi = env.GITHUB_ACTIONS === 'true' || env.CI === 'true';
  const annotate = env.GITHUB_ACTIONS === 'true';
  const git = makeGit(root);

  const clean = checkCleanSet(root, git);
  const base = resolveBase(git, argv, env);
  if (!base.mergeBase && inCi) {
    console.error(`error: base ${base.ref} not found, so added lines and commit messages cannot be checked.`);
    console.error('Fetch it (actions/checkout with fetch-depth: 0) or pass --base <ref>.');
    return 2;
  }
  const added = base.mergeBase ? checkAddedLines(git, base.mergeBase) : [];
  const commits = base.mergeBase ? checkCommitMessages(git, base.mergeBase) : [];

  for (const finding of [...clean, ...added]) {
    console.log(`${finding.file}:${finding.line}: ${finding.text.trim()}`);
    if (annotate) console.log(`::error file=${finding.file},line=${finding.line}::Em dash (U+2014): ${HINT}`);
  }
  for (const finding of commits) {
    console.log(`commit ${finding.commit} "${finding.subject}" (message line ${finding.line}): ${finding.text.trim()}`);
    if (annotate) console.log(`::error::Em dash (U+2014) in the message of commit ${finding.commit}: reword the commit`);
  }

  const total = clean.length + added.length + commits.length;
  const scope = base.mergeBase
    ? `published docs, lines added since ${base.ref} and their commit messages`
    : `published docs only (added lines and commit messages skipped: ${base.ref} not found)`;
  if (total === 0) {
    console.log(`No em dashes: ${scope}.`);
    return 0;
  }
  console.log(`\n${total} em dash finding(s) in ${scope}: ${HINT}.`);
  return strict ? 1 : 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { hasEmDash, inCleanSet, findAddedEmDashes, main };
