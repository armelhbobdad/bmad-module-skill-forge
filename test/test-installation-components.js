/**
 * Installation Component Tests - SKF Module
 *
 * Tests SKF module installation components in isolation:
 * - Module.yaml structure validation
 * - Agent YAML structure validation
 * - Path references validation
 * - Workflow existence verification
 *
 * These are deterministic unit tests that don't require full installation.
 * Usage: node test/test-installation-components.js
 */

const path = require('node:path');
const fs = require('node:fs/promises');
const yaml = require('js-yaml');

async function pathExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

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

/**
 * Test helper: Assert condition
 */
function assert(condition, testName, errorMessage = '') {
  if (condition) {
    console.log(`${colors.green}✓${colors.reset} ${testName}`);
    passed++;
  } else {
    console.log(`${colors.red}✗${colors.reset} ${testName}`);
    if (errorMessage) {
      console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    }
    failed++;
  }
}

/**
 * Test Suite
 */
async function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('SKF Installation Component Tests');
  console.log(`========================================${colors.reset}\n`);

  const projectRoot = path.join(__dirname, '..');

  // ============================================================
  // Test 1: Module.yaml Structure
  // ============================================================
  console.log(`${colors.yellow}Test Suite 1: Module Configuration${colors.reset}\n`);

  try {
    const moduleYamlPath = path.join(projectRoot, 'src/module.yaml');
    const moduleYaml = yaml.load(await fs.readFile(moduleYamlPath, 'utf8'));

    assert(moduleYaml.code === 'skf', 'module.yaml has correct code: skf');
    assert(typeof moduleYaml.name === 'string' && moduleYaml.name.length > 0, 'module.yaml has name');
    assert(typeof moduleYaml.description === 'string' && moduleYaml.description.length > 0, 'module.yaml has description');
    assert(typeof moduleYaml.default_selected === 'boolean', 'module.yaml has boolean default_selected');
  } catch (error) {
    assert(false, 'module.yaml loads and validates', error.message);
  }

  console.log('');

  // ============================================================
  // Test 2: SKF Agent YAML Structure
  // ============================================================
  console.log(`${colors.yellow}Test Suite 2: SKF Agent Structure${colors.reset}\n`);

  try {
    const skfAgentPath = path.join(projectRoot, 'src/agents/forger.agent.yaml');

    if (await pathExists(skfAgentPath)) {
      const skfAgent = yaml.load(await fs.readFile(skfAgentPath, 'utf8'));

      assert(skfAgent.agent !== undefined, 'forger.agent.yaml has agent root key');
      assert(skfAgent.agent.metadata !== undefined, 'SKF agent has metadata section');
      assert(skfAgent.agent.metadata.module === 'skf', 'SKF agent metadata has module: skf');
      assert(skfAgent.agent.metadata.id.includes('_bmad/skf/'), 'SKF agent id references _bmad/skf/ path');
      assert(skfAgent.agent.persona !== undefined, 'SKF agent has persona section');
      assert(skfAgent.agent.critical_actions !== undefined, 'SKF agent has critical_actions');
      assert(skfAgent.agent.menu !== undefined, 'SKF agent has menu');
      assert(
        Array.isArray(skfAgent.agent.menu) && skfAgent.agent.menu.length === 14,
        'SKF agent menu has 14 entries (12 workflows + 1 knowledge index + 1 status action)',
        `Found ${Array.isArray(skfAgent.agent.menu) ? skfAgent.agent.menu.length : 'non-array'}`,
      );

      // Verify no foreign module references
      const yamlContent = await fs.readFile(skfAgentPath, 'utf8');
      assert(!yamlContent.includes('module: tea'), 'SKF agent has no module: tea references');
      assert(!yamlContent.includes('module: bmm'), 'SKF agent has no module: bmm references');
    } else {
      assert(false, 'SKF agent YAML exists', 'src/agents/forger.agent.yaml not found');
    }
  } catch (error) {
    assert(false, 'SKF agent structure validates', error.message);
  }

  console.log('');

  // ============================================================
  // Test 3: Knowledge Base Structure
  // ============================================================
  console.log(`${colors.yellow}Test Suite 3: Knowledge Base${colors.reset}\n`);

  try {
    const skfIndexPath = path.join(projectRoot, 'src/knowledge/skf-knowledge-index.csv');

    if (await pathExists(skfIndexPath)) {
      const csvContent = await fs.readFile(skfIndexPath, 'utf8');
      const lines = csvContent.trim().split('\n');

      assert(lines.length >= 2, 'skf-knowledge-index.csv has header + at least 1 record', `Found ${lines.length} lines`);
      assert(lines[0].includes('id,name,description,tags,tier,fragment_file'), 'skf-knowledge-index.csv has correct header format');
    } else {
      assert(false, 'Knowledge index exists', 'src/knowledge/skf-knowledge-index.csv not found');
    }
  } catch (error) {
    assert(false, 'Knowledge base structure validates', error.message);
  }

  console.log('');

  // ============================================================
  // Test 4: Workflow Structure
  // ============================================================
  console.log(`${colors.yellow}Test Suite 4: Workflow Structure${colors.reset}\n`);

  const workflowNames = [
    'setup-forge',
    'analyze-source',
    'brief-skill',
    'create-skill',
    'quick-skill',
    'create-stack-skill',
    'verify-stack',
    'refine-architecture',
    'update-skill',
    'audit-skill',
    'test-skill',
    'export-skill',
  ];

  for (const workflowName of workflowNames) {
    const workflowPath = path.join(projectRoot, `src/workflows/${workflowName}/workflow.md`);

    if (await pathExists(workflowPath)) {
      const content = await fs.readFile(workflowPath, 'utf8');
      assert(content.length > 0, `${workflowName}/workflow.md exists`);
    } else {
      assert(false, `${workflowName}/workflow.md exists`, `src/workflows/${workflowName}/workflow.md not found`);
    }
  }

  console.log('');

  // ============================================================
  // Test 5: Step-File Chain and Data File Validation
  // ============================================================
  console.log(`${colors.yellow}Test Suite 5: Step-File and Data File Validation${colors.reset}\n`);

  const stepFileChains = {
    'setup-forge': {
      steps: [
        'step-01-detect-and-tier.md',
        'step-01b-ccc-index.md',
        'step-02-write-config.md',
        'step-03-auto-index.md',
        'step-04-report.md',
      ],
      data: ['tier-rules.md'],
    },
    'analyze-source': {
      steps: [
        'step-01-init.md',
        'step-01b-continue.md',
        'step-02-scan-project.md',
        'step-03-identify-units.md',
        'step-04-map-and-detect.md',
        'step-05-recommend.md',
        'step-06-generate-briefs.md',
      ],
      data: ['skill-brief-schema.md', 'unit-detection-heuristics.md'],
    },
    'brief-skill': {
      steps: [
        'step-01-gather-intent.md',
        'step-02-analyze-target.md',
        'step-03-scope-definition.md',
        'step-04-confirm-brief.md',
        'step-05-write-brief.md',
      ],
      data: ['scope-templates.md', 'skill-brief-schema.md'],
    },
    'create-skill': {
      steps: [
        'step-01-load-brief.md',
        'step-02-ecosystem-check.md',
        'step-02b-ccc-discover.md',
        'step-03-extract.md',
        'step-03b-fetch-temporal.md',
        'step-03c-fetch-docs.md',
        'step-04-enrich.md',
        'step-05-compile.md',
        'step-06-validate.md',
        'step-07-generate-artifacts.md',
        'step-08-report.md',
      ],
      data: [
        'compile-assembly-rules.md',
        'extraction-patterns.md',
        'extraction-patterns-tracing.md',
        'skill-sections.md',
        'source-resolution-protocols.md',
        'tier-degradation-rules.md',
      ],
    },
    'quick-skill': {
      steps: [
        'step-01-resolve-target.md',
        'step-02-ecosystem-check.md',
        'step-03-quick-extract.md',
        'step-04-compile.md',
        'step-05-validate.md',
        'step-06-write.md',
      ],
      data: ['registry-resolution.md', 'skill-template.md'],
    },
    'create-stack-skill': {
      steps: [
        'step-01-init.md',
        'step-02-detect-manifests.md',
        'step-03-rank-and-confirm.md',
        'step-04-parallel-extract.md',
        'step-05-detect-integrations.md',
        'step-06-compile-stack.md',
        'step-07-generate-output.md',
        'step-08-validate.md',
        'step-09-report.md',
      ],
      data: ['integration-patterns.md', 'manifest-patterns.md', 'stack-skill-template.md', 'compose-mode-rules.md'],
    },
    'update-skill': {
      steps: [
        'step-01-init.md',
        'step-02-detect-changes.md',
        'step-03-re-extract.md',
        'step-04-merge.md',
        'step-05-validate.md',
        'step-06-write.md',
        'step-07-report.md',
      ],
      data: ['manual-section-rules.md', 'merge-conflict-rules.md', 'remote-source-resolution.md'],
    },
    'audit-skill': {
      steps: [
        'step-01-init.md',
        'step-02-re-index.md',
        'step-03-structural-diff.md',
        'step-04-semantic-diff.md',
        'step-05-severity-classify.md',
        'step-06-report.md',
      ],
      data: ['drift-report-template.md', 'severity-rules.md'],
    },
    'test-skill': {
      steps: [
        'step-01-init.md',
        'step-02-detect-mode.md',
        'step-03-coverage-check.md',
        'step-04-coherence-check.md',
        'step-04b-external-validators.md',
        'step-05-score.md',
        'step-06-report.md',
      ],
      data: ['output-section-formats.md', 'scoring-rules.md', 'source-access-protocol.md'],
    },
    'verify-stack': {
      steps: [
        'step-01-init.md',
        'step-02-coverage.md',
        'step-03-integrations.md',
        'step-04-requirements.md',
        'step-05-synthesize.md',
        'step-06-report.md',
      ],
      data: ['coverage-patterns.md', 'feasibility-report-template.md', 'integration-verification-rules.md'],
    },
    'refine-architecture': {
      steps: [
        'step-01-init.md',
        'step-02-gap-analysis.md',
        'step-03-issue-detection.md',
        'step-04-improvements.md',
        'step-05-compile.md',
        'step-06-report.md',
      ],
      data: ['refinement-rules.md'],
    },
    'export-skill': {
      steps: [
        'step-01-load-skill.md',
        'step-02-package.md',
        'step-03-generate-snippet.md',
        'step-04-update-context.md',
        'step-05-token-report.md',
        'step-06-summary.md',
      ],
      data: ['managed-section-format.md', 'snippet-format.md'],
    },
  };

  for (const [workflow, files] of Object.entries(stepFileChains)) {
    for (const step of files.steps) {
      const stepPath = path.join(projectRoot, `src/workflows/${workflow}/steps-c/${step}`);
      const exists = await pathExists(stepPath);
      assert(exists, `${workflow}/steps-c/${step} exists`, `Missing step file: ${stepPath}`);
    }
    for (const dataFile of files.data) {
      const dataPath = path.join(projectRoot, `src/workflows/${workflow}/data/${dataFile}`);
      const exists = await pathExists(dataPath);
      assert(exists, `${workflow}/data/${dataFile} exists`, `Missing data file: ${dataPath}`);
    }
  }

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
    console.log(`${colors.green}✨ All installation component tests passed!${colors.reset}\n`);
    process.exit(0);
  } else {
    console.log(`${colors.red}❌ Some installation component tests failed${colors.reset}\n`);
    process.exit(1);
  }
}

// Run tests
runTests().catch((error) => {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
});
