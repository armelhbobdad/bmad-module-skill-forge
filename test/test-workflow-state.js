/**
 * Workflow State Consistency Tests - SKF Module
 *
 * Validates cross-step state consistency for VS, RA, and compose-mode workflows:
 * - VS feasibility report frontmatter fields match step consumption
 * - RA state file comment block format matches step 5 recovery parser
 * - Compose-mode confidence tier labels match compose-mode-rules.md matrix
 *
 * These are static analysis tests against the step markdown files.
 * Usage: node test/test-workflow-state.js
 */

const path = require('node:path');
const fs = require('node:fs/promises');

// ANSI colors
const colors = {
  reset: '\u001B[0m',
  green: '\u001B[32m',
  red: '\u001B[31m',
  yellow: '\u001B[33m',
  cyan: '\u001B[36m',
  dim: '\u001B[2m',
};

let passed = 0;
let failed = 0;

function assert(condition, testName, errorMessage = '') {
  if (condition) {
    console.log(`${colors.green}\u2713${colors.reset} ${testName}`);
    passed++;
  } else {
    console.log(`${colors.red}\u2717${colors.reset} ${testName}`);
    if (errorMessage) {
      console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    }
    failed++;
  }
}

async function readFile(filePath) {
  return fs.readFile(filePath, 'utf8');
}

async function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('SKF Workflow State Consistency Tests');
  console.log(`========================================${colors.reset}\n`);

  const projectRoot = path.join(__dirname, '..');
  const srcDir = path.join(projectRoot, 'src');

  // ============================================================
  // Test Suite 1: VS Feasibility Report Frontmatter Fields
  // ============================================================
  console.log(`${colors.yellow}Test Suite 1: VS Frontmatter Field Consistency${colors.reset}\n`);

  const vsTemplate = await readFile(path.join(srcDir, 'skf-verify-stack/assets/feasibility-report-template.md'));
  const vsStep06 = await readFile(path.join(srcDir, 'skf-verify-stack/references/report.md'));
  const vsStep05 = await readFile(path.join(srcDir, 'skf-verify-stack/references/synthesize.md'));

  // Extract frontmatter field names from template
  const templateFrontmatter = vsTemplate.split('---')[1];
  const templateFields = new Set(templateFrontmatter.match(/^(\w+):/gm).map((f) => f.replace(':', '')));

  // Key fields step 6 must read.
  // Producer-local bookkeeping uses camelCase to match the shared
  // schema at src/shared/references/feasibility-report-schema.md (v1.0).
  const requiredStep06Fields = [
    'skillsAnalyzed',
    'coveragePercentage',
    'pairsVerified',
    'pairsPlausible',
    'pairsRisky',
    'pairsBlocked',
    'requirementsFulfilled',
    'requirementsPartial',
    'requirementsNotAddressed',
    'requirementsPass',
    'overallVerdict',
    'recommendationCount',
  ];

  for (const field of requiredStep06Fields) {
    assert(templateFields.has(field), `VS template has frontmatter field: ${field}`, `Missing from feasibility-report-template.md`);
  }

  // Delta fields must exist in template for step 6 consumption
  const deltaFields = ['deltaImproved', 'deltaRegressed', 'deltaNew', 'deltaUnchanged'];
  for (const field of deltaFields) {
    assert(
      templateFields.has(field),
      `VS template has delta field: ${field}`,
      `Missing from feasibility-report-template.md — step 6 reads these`,
    );
  }

  // Step-06 must reference the delta fields by name
  for (const field of deltaFields) {
    assert(vsStep06.includes(field), `VS step 6 references ${field}`, `report.md should reference ${field} for delta display`);
  }

  // Step-05 must write delta fields to frontmatter
  assert(vsStep05.includes('deltaImproved'), 'VS step 5 writes delta fields to frontmatter', 'synthesize.md should set delta* fields');

  // Requirements fields should init to null (not 0) for proper N/A fallback
  assert(
    vsTemplate.includes('requirementsFulfilled: null'),
    'VS template inits requirementsFulfilled to null',
    'Should be null for proper N/A fallback in step 6',
  );
  assert(
    vsTemplate.includes('requirementsPartial: null'),
    'VS template inits requirementsPartial to null',
    'Should be null for proper N/A fallback in step 6',
  );
  assert(
    vsTemplate.includes('requirementsNotAddressed: null'),
    'VS template inits requirementsNotAddressed to null',
    'Should be null for proper N/A fallback in step 6',
  );

  console.log('');

  // ============================================================
  // Test Suite 2: RA State File Comment Block Format
  // ============================================================
  console.log(`${colors.yellow}Test Suite 2: RA State File Consistency${colors.reset}\n`);

  const raStep01 = await readFile(path.join(srcDir, 'skf-refine-architecture/references/init.md'));
  const raStep05 = await readFile(path.join(srcDir, 'skf-refine-architecture/references/compile.md'));

  // Step-01 creates the state file with a specific header format
  assert(
    raStep01.includes('ra-state-{project_name}.md'),
    'RA step 1 creates ra-state file',
    'init.md should create ra-state-{project_name}.md',
  );

  // Step-05 must reference all three comment block markers for recovery
  const commentBlocks = ['<!-- [RA-GAPS] -->', '<!-- [RA-ISSUES] -->', '<!-- [RA-IMPROVEMENTS] -->'];
  for (const block of commentBlocks) {
    assert(raStep05.includes(block), `RA step 5 parses ${block}`, `compile.md must reference ${block} for context recovery`);
  }

  // Step-05 recovery should point to beginning, not mid-workflow
  assert(
    !raStep05.includes('Re-run [RA] from **step 02**'),
    'RA step 5 recovery points to beginning (not step 02)',
    'Recovery should re-run from beginning since step 01 resets state',
  );

  // Step-05 should use {current_date} not {date}
  assert(
    !raStep01.includes('{date}') || raStep01.includes('{current_date}'),
    'RA step 1 uses {current_date} convention',
    'Should use {current_date} for consistency with codebase',
  );

  console.log('');

  // ============================================================
  // Test Suite 3: Compose-Mode Confidence Tier Labels
  // ============================================================
  console.log(`${colors.yellow}Test Suite 3: Compose-Mode Confidence Tier Consistency${colors.reset}\n`);

  const composeModeRules = await readFile(path.join(srcDir, 'skf-create-stack-skill/references/compose-mode-rules.md'));
  const cssStep05 = await readFile(path.join(srcDir, 'skf-create-stack-skill/references/detect-integrations.md'));

  // Compose-mode-rules must cover all pairwise cases
  assert(
    composeModeRules.includes('both skills in a pair are T1'),
    'compose-mode-rules covers T1+T1 case',
    'Missing T1+T1 tier case in compose-mode-rules.md',
  );
  assert(composeModeRules.includes('T1-low'), 'compose-mode-rules covers T1-low case', 'Missing T1-low tier case in compose-mode-rules.md');
  assert(composeModeRules.includes('T2'), 'compose-mode-rules covers T2 case', 'Missing T2 tier case in compose-mode-rules.md');

  // Must have explicit T1+T2 case
  assert(
    composeModeRules.includes('T1 + T2') || composeModeRules.includes('T1+T2'),
    'compose-mode-rules has explicit T1+T2 case',
    'T1+T2 pair must have an explicit row with label format',
  );

  // Step-05 enumeration should only list pairwise cases (no 3-skill compounds)
  assert(
    !cssStep05.includes('T1-low+T1-low+T2'),
    'CSS step 5 has no 3-skill compound cases',
    'Confidence tier matrix is pairwise only — T1-low+T1-low+T2 is invalid',
  );

  // Compose-mode suffix format
  assert(
    composeModeRules.includes('[composed]'),
    'compose-mode-rules uses [composed] suffix',
    'All compose-mode integrations should use [composed] suffix',
  );

  // Inferred integration distinction
  assert(
    composeModeRules.includes('[inferred from shared domain]'),
    'compose-mode-rules distinguishes inferred integrations',
    'Inferred integrations use different suffix from composed',
  );

  console.log('');

  // ============================================================
  // Test Suite 4: VS Step-03 Early Halt Guard
  // ============================================================
  console.log(`${colors.yellow}Test Suite 4: VS Step Sequencing Guards${colors.reset}\n`);

  const vsStep03 = await readFile(path.join(srcDir, 'skf-verify-stack/references/integrations.md'));

  // Step-03 auto-proceed must be gated (not unconditional after halt guard)
  assert(
    vsStep03.includes('{IF NOT halted') || vsStep03.includes('{IF C') || vsStep03.includes('{IF not halted'),
    'VS step 3 gates auto-proceed after halt guard',
    'Proceeding message and next-step load must be inside a conditional',
  );

  console.log('');

  // ============================================================
  // Summary
  // ============================================================
  console.log(`${colors.cyan}========================================`);
  console.log('Test Results:');
  console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
  console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`========================================${colors.reset}\n`);

  if (failed === 0) {
    console.log(`${colors.green}\u2728 All workflow state tests passed!${colors.reset}\n`);
    process.exit(0);
  } else {
    console.log(`${colors.red}\u274C Some workflow state tests failed${colors.reset}\n`);
    process.exit(1);
  }
}

runTests().catch((error) => {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
});
