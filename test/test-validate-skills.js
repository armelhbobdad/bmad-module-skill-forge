/**
 * Tests for SKILL-06 in tools/validate-skills.js
 *
 * `npm run validate:skills` runs the validator with --strict in CI, which
 * fails on HIGH findings only. SKILL-06 is the SKILL.md description rule
 * docs/_internal/STABILITY.md states:
 *
 * - a "Use when" or "Use if" clause, anywhere in the description and in any
 *   letter case (HIGH, so a missing clause fails CI, #573);
 * - every trigger the clause quotes names its object: a bare verb such as
 *   "drop" or "set up" fires the skill on unrelated requests (HIGH, #600);
 * - at most 1024 characters (MEDIUM, a warning).
 *
 * The rule is called on throwaway skill folders, and the CLI is run on them
 * and on the repository's own skills.
 */

const assert = require('node:assert');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const TOOL = path.join(__dirname, '..', 'tools', 'validate-skills.js');
const { validateSkill, discoverSkillDirs, bareVerbTriggers } = require(TOOL);

const SRC = path.join(__dirname, '..', 'src');

let passed = 0;
let failed = 0;
const tmpRoots = [];

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`\u001B[32m✓\u001B[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`\u001B[31m✗\u001B[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

/** A skill folder named skf-demo whose SKILL.md carries `description`. */
function makeSkill(description) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vskills-'));
  tmpRoots.push(root);
  const dir = path.join(root, 'skf-demo');
  fs.mkdirSync(dir);
  fs.writeFileSync(path.join(dir, 'SKILL.md'), `---\nname: skf-demo\ndescription: ${description}\n---\n\n# Demo\n\nBody.\n`);
  return dir;
}

function skill06(description) {
  return validateSkill(makeSkill(description)).filter((f) => f.rule === 'SKILL-06');
}

function run(dir) {
  const result = spawnSync(process.execPath, [TOOL, '--strict', dir], { encoding: 'utf8' });
  return { status: result.status, out: result.stdout + result.stderr };
}

// --- The wave-2 rule: a "Use when" or "Use if" clause within 1024 characters ---

test('a "Use when" or "Use if" clause anywhere, in any letter case, passes', () => {
  for (const description of [
    'Drops a skill. Use when the user requests to "drop a skill".',
    'use if the user asks to "rename a skill". Renames a skill.',
    'Compiles a skill. USE WHEN the user wants to "compile a skill".',
    'Tests a skill.\nUse  when the user asks to "test a skill".',
  ]) {
    assert.deepStrictEqual(skill06(description), [], description);
  }
});

test('a description with no clause is a HIGH finding', () => {
  const findings = skill06('Drops a skill when the user asks to "drop a skill".');
  assert.strictEqual(findings.length, 1, JSON.stringify(findings));
  assert.strictEqual(findings[0].severity, 'HIGH');
  assert.match(findings[0].detail, /no "Use when" or "Use if" trigger clause/);
});

test('"Use whenever" and "user if" are not the clause', () => {
  for (const description of ['Use whenever you like to "drop a skill".', 'The user if asked may "drop a skill".']) {
    assert.deepStrictEqual(
      skill06(description).map((f) => f.severity),
      ['HIGH'],
      description,
    );
  }
});

test('1024 characters pass and 1025 are a MEDIUM finding', () => {
  const head = 'Use when the user requests to "drop a skill". ';
  const at = head + 'x'.repeat(1024 - head.length);
  assert.strictEqual(at.length, 1024);
  assert.deepStrictEqual(skill06(at), []);
  const over = skill06(at + 'x');
  assert.deepStrictEqual(
    over.map((f) => [f.severity, f.detail]),
    [['MEDIUM', 'description is 1025 characters (max 1024).']],
  );
});

// --- The bare-verb rule ---

test('a one-word or verb-and-particle trigger is a HIGH finding', () => {
  for (const [description, trigger] of [
    ['Drops a skill. Use when the user requests to "drop" or "remove a skill".', 'drop'],
    ['Sets up the forge. Use when the user requests to "set up" or "initialize the forge".', 'set up'],
    ['Exports a skill. Use when the user requests to "export a skill" or "export."', 'export.'],
    ['Cleans a skill. Use if the user asks to “clean up”.', 'clean up'],
    ["Drops a skill. Use when the user says 'drop' or 'remove a skill'.", 'drop'],
    ['Drops a skill. Use when the user says ‘drop’ or ‘remove a skill’.', 'drop'],
  ]) {
    const findings = skill06(description);
    assert.deepStrictEqual(
      findings.map((f) => f.severity),
      ['HIGH'],
      description,
    );
    assert.strictEqual(
      findings[0].detail,
      `description quotes "${trigger}", a one-word or verb-plus-particle trigger that names no object.`,
    );
  }
});

test('a trigger that names its object passes', () => {
  for (const description of [
    'Use when the user requests to "set up the forge" or "initialize the forge".',
    'Use when the user requests a "quick skill" or "skill from URL" or "skill from package."',
    'Use when the user asks to "talk to Ferris" or requests the "Skill Forge agent."',
    'Use when the user requests to "verify a tech stack" or "verify stack."',
  ]) {
    assert.deepStrictEqual(skill06(description), [], description);
  }
});

test('an apostrophe or an inch mark is not a quote', () => {
  assert.deepStrictEqual(bareVerbTriggers("Use when the user's team asks to 'drop a skill'."), []);
  assert.deepStrictEqual(bareVerbTriggers("Use when it's time to 'drop' a skill."), ['drop']);
  assert.deepStrictEqual(bareVerbTriggers('Use when a 12" screen shows "drop" or "drop a skill".'), ['drop']);
});

test('a quote ahead of the clause is not a trigger', () => {
  assert.deepStrictEqual(bareVerbTriggers('The "drop" command. Use when the user requests to "drop a skill".'), []);
  assert.deepStrictEqual(bareVerbTriggers('A "drop" without any clause.'), []);
  assert.deepStrictEqual(bareVerbTriggers('Use when asked to "drop" or "purge".'), ['drop', 'purge']);
});

// --- The CLI and the repository's skills ---

test('--strict fails on a bare-verb trigger and passes on a named object', () => {
  const bare = run(makeSkill('Drops a skill. Use when the user requests to "drop".'));
  assert.strictEqual(bare.status, 1, bare.out);
  assert.match(bare.out, /\[HIGH\] SKILL-06/);
  const named = run(makeSkill('Drops a skill. Use when the user requests to "drop a skill".'));
  assert.strictEqual(named.status, 0, named.out);
});

test('--strict fails on a missing clause', () => {
  const { status, out } = run(makeSkill('Drops a skill on request.'));
  assert.strictEqual(status, 1, out);
  assert.match(out, /no "Use when" or "Use if" trigger clause/);
});

test('every skill under src/ passes SKILL-06', () => {
  const dirs = discoverSkillDirs([SRC]);
  assert.ok(dirs.length >= 16, `${dirs.length} skills found`);
  for (const dir of dirs) {
    const findings = validateSkill(dir).filter((f) => f.rule === 'SKILL-06');
    assert.deepStrictEqual(findings, [], path.relative(SRC, dir));
  }
});

for (const root of tmpRoots) fs.rmSync(root, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
