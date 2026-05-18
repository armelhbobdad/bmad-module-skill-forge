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
  // Test 2: SKF Agent Skill Structure
  // ============================================================
  console.log(`${colors.yellow}Test Suite 2: SKF Agent Structure${colors.reset}\n`);

  try {
    const agentSkillDir = path.join(projectRoot, 'src/skf-forger');
    const agentSkillMd = path.join(agentSkillDir, 'SKILL.md');
    const agentManifest = path.join(agentSkillDir, 'bmad-skill-manifest.yaml');

    assert(await pathExists(agentSkillMd), 'skf-forger/SKILL.md exists');
    assert(await pathExists(agentManifest), 'skf-forger/bmad-skill-manifest.yaml exists');

    if (await pathExists(agentManifest)) {
      const manifest = yaml.load(await fs.readFile(agentManifest, 'utf8'));

      assert(manifest.type === 'agent', 'Agent manifest has type: agent');
      assert(manifest.name === 'skf-forger', 'Agent manifest has name: skf-forger');
      assert(manifest.module === 'skf', 'Agent manifest has module: skf');
      assert(typeof manifest.displayName === 'string', 'Agent manifest has displayName');
      assert(typeof manifest.title === 'string', 'Agent manifest has title');
      assert(typeof manifest.icon === 'string', 'Agent manifest has icon');
    }

    if (await pathExists(agentSkillMd)) {
      const content = await fs.readFile(agentSkillMd, 'utf8');
      assert(content.includes('## Capabilities'), 'Agent SKILL.md has Capabilities section');
      assert(content.includes('## On Activation'), 'Agent SKILL.md has On Activation section');
      assert(content.includes('skf-setup'), 'Agent capabilities reference skf-setup');
      assert(content.includes('skf-create-skill'), 'Agent capabilities reference skf-create-skill');
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
    'setup',
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
    'rename-skill',
    'drop-skill',
  ];

  for (const workflowName of workflowNames) {
    const skillMdPath = path.join(projectRoot, `src/skf-${workflowName}/SKILL.md`);

    if (await pathExists(skillMdPath)) {
      const content = await fs.readFile(skillMdPath, 'utf8');
      const hasName = content.includes(`name: skf-${workflowName}`);
      assert(hasName, `${workflowName}/SKILL.md has correct name field`);
      const hasOverview = content.includes('## Overview');
      assert(hasOverview, `${workflowName}/SKILL.md has Overview section`);
    } else {
      assert(false, `${workflowName}/SKILL.md exists`, `src/skf-${workflowName}/SKILL.md not found`);
    }
  }

  console.log('');

  // ============================================================
  // Test 5: Step-File Chain and Resource File Validation
  // ============================================================
  console.log(`${colors.yellow}Test Suite 5: Step-File and Resource File Validation${colors.reset}\n`);

  const stepFileChains = {
    setup: {
      steps: ['detect-and-tier.md', 'ccc-index.md', 'write-config.md', 'auto-index.md', 'report.md', 'health-check.md'],
      references: ['tier-rules.md'],
    },
    'analyze-source': {
      steps: [
        'init.md',
        'continue.md',
        'scan-project.md',
        'identify-units.md',
        'map-and-detect.md',
        'recommend.md',
        'generate-briefs.md',
        'health-check.md',
      ],
      assets: ['skill-brief-schema.md'],
      references: ['unit-detection-heuristics.md'],
    },
    'brief-skill': {
      steps: ['gather-intent.md', 'analyze-target.md', 'scope-definition.md', 'confirm-brief.md', 'write-brief.md', 'health-check.md'],
      assets: ['scope-templates.md', 'skill-brief-schema.md'],
    },
    'create-skill': {
      steps: [
        'load-brief.md',
        'ecosystem-check.md',
        'sub/ccc-discover.md',
        'extract.md',
        'sub/fetch-temporal.md',
        'sub/fetch-docs.md',
        'component-extraction.md',
        'enrich.md',
        'compile.md',
        'validate.md',
        'generate-artifacts.md',
        'report.md',
        'health-check.md',
      ],
      assets: ['compile-assembly-rules.md', 'skill-sections.md'],
      references: [
        'extraction-patterns.md',
        'extraction-patterns-tracing.md',
        'source-resolution-protocols.md',
        'tier-degradation-rules.md',
      ],
    },
    'quick-skill': {
      steps: [
        'resolve-target.md',
        'ecosystem-check.md',
        'quick-extract.md',
        'compile.md',
        'write-and-validate.md',
        'finalize.md',
        'health-check.md',
      ],
      assets: ['skill-template.md'],
      references: ['registry-resolution.md'],
    },
    'create-stack-skill': {
      steps: [
        'init.md',
        'detect-manifests.md',
        'rank-and-confirm.md',
        'parallel-extract.md',
        'detect-integrations.md',
        'compile-stack.md',
        'generate-output.md',
        'validate.md',
        'report.md',
        'health-check.md',
      ],
      assets: ['stack-skill-template.md'],
      references: ['integration-patterns.md', 'manifest-patterns.md', 'compose-mode-rules.md'],
    },
    'update-skill': {
      steps: ['init.md', 'detect-changes.md', 're-extract.md', 'merge.md', 'validate.md', 'write.md', 'report.md', 'health-check.md'],
      references: ['manual-section-rules.md', 'merge-conflict-rules.md', 'remote-source-resolution.md'],
    },
    'audit-skill': {
      steps: ['init.md', 're-index.md', 'structural-diff.md', 'semantic-diff.md', 'severity-classify.md', 'report.md', 'health-check.md'],
      assets: ['drift-report-template.md'],
      references: ['severity-rules.md'],
    },
    'test-skill': {
      steps: [
        'init.md',
        'detect-mode.md',
        'coverage-check.md',
        'coherence-check.md',
        'external-validators.md',
        'score.md',
        'report.md',
        'health-check.md',
      ],
      assets: ['output-section-formats.md'],
      references: ['scoring-rules.md', 'source-access-protocol.md'],
    },
    'verify-stack': {
      steps: ['init.md', 'coverage.md', 'integrations.md', 'requirements.md', 'synthesize.md', 'report.md', 'health-check.md'],
      assets: ['feasibility-report-template.md'],
      references: ['coverage-patterns.md', 'integration-verification-rules.md'],
    },
    'refine-architecture': {
      steps: ['init.md', 'gap-analysis.md', 'issue-detection.md', 'improvements.md', 'compile.md', 'report.md', 'health-check.md'],
      references: ['refinement-rules.md'],
    },
    'export-skill': {
      steps: [
        'load-skill.md',
        'package.md',
        'generate-snippet.md',
        'update-context.md',
        'token-report.md',
        'summary.md',
        'health-check.md',
      ],
      assets: ['managed-section-format.md', 'snippet-format.md'],
    },
    'rename-skill': {
      steps: ['select.md', 'execute.md', 'report.md', 'health-check.md'],
    },
    'drop-skill': {
      steps: ['select.md', 'execute.md', 'report.md', 'health-check.md'],
    },
  };

  for (const [workflow, files] of Object.entries(stepFileChains)) {
    for (const step of files.steps) {
      const stepPath = path.join(projectRoot, `src/skf-${workflow}/references/${step}`);
      const exists = await pathExists(stepPath);
      assert(exists, `${workflow}/references/${step} exists`, `Missing step file: ${stepPath}`);
    }
    for (const refFile of files.references || []) {
      const refPath = path.join(projectRoot, `src/skf-${workflow}/references/${refFile}`);
      const exists = await pathExists(refPath);
      assert(exists, `${workflow}/references/${refFile} exists`, `Missing reference file: ${refPath}`);
    }
    for (const assetFile of files.assets || []) {
      const assetPath = path.join(projectRoot, `src/skf-${workflow}/assets/${assetFile}`);
      const exists = await pathExists(assetPath);
      assert(exists, `${workflow}/assets/${assetFile} exists`, `Missing asset file: ${assetPath}`);
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
