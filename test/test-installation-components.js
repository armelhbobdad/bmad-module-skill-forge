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

const os = require('node:os');
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

/**
 * The string keys of one [table] in a TOML file: enough for the flat
 * `key = "basic string"` metadata a customize.toml [agent] block holds.
 */
function readTomlTable(text, table) {
  const values = {};
  let inTable = false;
  for (const line of text.split(/\r?\n/)) {
    const header = /^\s*\[([^\]]+)\]\s*(?:#.*)?$/.exec(line);
    if (header) {
      inTable = header[1].trim() === table;
      continue;
    }
    const pair = inTable ? /^\s*([\w-]+)\s*=\s*("(?:[^"\\]|\\.)*")\s*(?:#.*)?$/.exec(line) : null;
    if (pair) values[pair[1]] = JSON.parse(pair[2]);
  }
  return values;
}

// skf-forger's [agent] block: the metadata a BMAD Method install reads.
const AGENT_KEYS = ['code', 'name', 'title', 'icon', 'description'];

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

    // The agent roster a BMAD Method install writes to _bmad/config.toml as
    // [agents.<code>]: one entry, the same values as skf-forger's [agent] block.
    const agents = Array.isArray(moduleYaml.agents) ? moduleYaml.agents : [];
    assert(
      agents.length === 1 && agents[0].code === 'skf-forger',
      'module.yaml agents list has one entry, skf-forger',
      JSON.stringify(moduleYaml.agents),
    );
    const agentBlock = readTomlTable(await fs.readFile(path.join(projectRoot, 'src/skf-forger/customize.toml'), 'utf8'), 'agent');
    for (const key of AGENT_KEYS) {
      assert(
        typeof agentBlock[key] === 'string' && agents[0]?.[key] === agentBlock[key],
        `module.yaml agents entry ${key} matches skf-forger/customize.toml [agent]`,
        `module.yaml: ${JSON.stringify(agents[0]?.[key])}, customize.toml: ${JSON.stringify(agentBlock[key])}`,
      );
    }
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

      // customize.toml's [agent] block mirrors the manifest. A BMAD Method
      // install counts a skill as an agent only when its customize.toml has
      // an [agent] section at the start of a line.
      const customizePath = path.join(agentSkillDir, 'customize.toml');
      assert(await pathExists(customizePath), 'skf-forger/customize.toml exists');
      const customize = (await pathExists(customizePath)) ? await fs.readFile(customizePath, 'utf8') : '';
      assert(/^\[agent\]/m.test(customize), 'skf-forger/customize.toml has an [agent] section');
      const agentBlock = readTomlTable(customize, 'agent');
      const mirrored = {
        code: manifest.name,
        name: manifest.displayName,
        title: manifest.title,
        icon: manifest.icon,
        description: manifest.role,
      };
      for (const key of AGENT_KEYS) {
        assert(
          agentBlock[key] === mirrored[key],
          `customize.toml [agent] ${key} matches bmad-skill-manifest.yaml`,
          `customize.toml: ${JSON.stringify(agentBlock[key])}, manifest: ${JSON.stringify(mirrored[key])}`,
        );
      }
      assert(
        agentBlock.agent_type === 'stateless',
        'customize.toml [agent] agent_type is stateless',
        JSON.stringify(agentBlock.agent_type),
      );
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
        'entry-points-by-hand.md',
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
      steps: ['init.md', 'detect-changes.md', 're-extract.md', 'merge.md', 'write.md', 'report.md', 'health-check.md'],
      references: ['manual-section-rules.md'],
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
  // Test 6: Installer Config Generation (health_check_repo)
  // ============================================================
  console.log(`${colors.yellow}Test Suite 6: Installer Config Generation${colors.reset}\n`);

  try {
    const { Installer } = require('../tools/cli/lib/installer.js');
    const installer = new Installer();

    const moduleYaml = yaml.load(await fs.readFile(path.join(projectRoot, 'src/module.yaml'), 'utf8'));
    const expectedRepo = moduleYaml.health_check_repo.default;
    assert(typeof expectedRepo === 'string' && expectedRepo.length > 0, 'module.yaml declares health_check_repo default');

    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'skf-config-test-'));
    try {
      // Fresh install: generated config carries the module.yaml default
      await installer.writeConfig(tmpDir, { skfFolder: '_bmad/skf' });
      const freshConfig = yaml.load(await fs.readFile(path.join(tmpDir, 'config.yaml'), 'utf8'));
      assert(
        freshConfig.health_check_repo === expectedRepo,
        'fresh config.yaml contains health_check_repo with module.yaml default',
        `Expected ${expectedRepo}, got ${freshConfig.health_check_repo}`,
      );

      // Update path: key injected into a saved config that lacks it
      const legacyYaml = '# SKF Configuration - Generated by installer\nuser_name: Dev\nproject_name: Legacy\n';
      await installer.writeConfig(tmpDir, { skfFolder: '_bmad/skf', _savedConfigYaml: legacyYaml });
      const migratedText = await fs.readFile(path.join(tmpDir, 'config.yaml'), 'utf8');
      const migratedConfig = yaml.load(migratedText);
      assert(
        migratedConfig.health_check_repo === expectedRepo,
        'update injects health_check_repo into saved config lacking it',
        `Expected ${expectedRepo}, got ${migratedConfig.health_check_repo}`,
      );
      assert(
        migratedText.startsWith(legacyYaml),
        'update preserves original saved config text byte-for-byte',
        'Saved config text was rewritten',
      );

      // Update path: existing (customized) value left untouched
      const customYaml = '# SKF Configuration - Generated by installer\nuser_name: Dev\nhealth_check_repo: my-org/my-fork\n';
      await installer.writeConfig(tmpDir, { skfFolder: '_bmad/skf', _savedConfigYaml: customYaml });
      const customText = await fs.readFile(path.join(tmpDir, 'config.yaml'), 'utf8');
      assert(
        customText === customYaml,
        'update leaves saved config with existing health_check_repo untouched',
        'Saved config text was modified',
      );

      // Update path: saved config without trailing newline gets the key on its own line
      const noNewlineYaml = '# SKF Configuration - Generated by installer\nuser_name: Dev\nproject_name: Legacy';
      await installer.writeConfig(tmpDir, { skfFolder: '_bmad/skf', _savedConfigYaml: noNewlineYaml });
      const noNewlineText = await fs.readFile(path.join(tmpDir, 'config.yaml'), 'utf8');
      const noNewlineConfig = yaml.load(noNewlineText);
      assert(
        noNewlineConfig.health_check_repo === expectedRepo,
        'update injects health_check_repo into saved config lacking trailing newline',
        `Expected ${expectedRepo}, got ${noNewlineConfig.health_check_repo}`,
      );
      assert(
        noNewlineText.startsWith(`${noNewlineYaml}\nhealth_check_repo: `),
        'update appends key without gluing to the last line',
        'Injected key was glued onto the last saved line',
      );

      // Update path: top-level array doc restored verbatim, no injection
      const arrayYaml = '- alpha\n- beta\n';
      await installer.writeConfig(tmpDir, { skfFolder: '_bmad/skf', _savedConfigYaml: arrayYaml });
      const arrayText = await fs.readFile(path.join(tmpDir, 'config.yaml'), 'utf8');
      assert(
        arrayText === arrayYaml,
        'update restores top-level array config verbatim without injection',
        'Array-shaped saved config was modified',
      );

      // Update path: bare-scalar doc restored verbatim, no injection
      const scalarYaml = 'just a bare scalar\n';
      await installer.writeConfig(tmpDir, { skfFolder: '_bmad/skf', _savedConfigYaml: scalarYaml });
      const scalarText = await fs.readFile(path.join(tmpDir, 'config.yaml'), 'utf8');
      assert(
        scalarText === scalarYaml,
        'update restores bare-scalar config verbatim without injection',
        'Scalar-shaped saved config was modified',
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  } catch (error) {
    assert(false, 'installer config generation validates', error.message);
  }

  console.log('');

  // ============================================================
  // Test 7: Paths Resolve in the Installed Layout
  // ============================================================
  // An installed project has _bmad/skf/ and no src/ tree. Install the module
  // into a temp project with the installer's own copy routine, then resolve
  // what the step files point at against that layout rather than against src/.
  console.log(`${colors.yellow}Test Suite 7: Paths Resolve in the Installed Layout${colors.reset}\n`);

  try {
    const { Installer } = require('../tools/cli/lib/installer.js');
    const { findSrcPathRefs, PAIR_SCAN_EXTENSIONS } = require('../tools/validate-file-refs.js');

    const INSTALLED = '{project-root}/_bmad/skf/';
    const DEV = '{project-root}/src/';
    const PROJECT_ROOT_PATH = /\{project-root\}\/[^\s'"<>})\]`]+/g;
    const RUNTIME_PART = /[{*]/;

    const walkFiles = async (dir) => {
      const out = [];
      for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) out.push(...(await walkFiles(full)));
        else if (entry.isFile()) out.push(full);
      }
      return out;
    };
    // Every string leaf of a frontmatter value
    const stringLeaves = (value) => {
      if (typeof value === 'string') return [value];
      if (Array.isArray(value)) return value.flatMap((item) => stringLeaves(item));
      if (value && typeof value === 'object') return Object.values(value).flatMap((item) => stringLeaves(item));
      return [];
    };

    const tmpProject = await fs.mkdtemp(path.join(os.tmpdir(), 'skf-install-layout-'));
    try {
      const skfDir = path.join(tmpProject, '_bmad', 'skf');
      await new Installer().copySrcFiles(skfDir);
      const inProject = (ref) => path.join(tmpProject, ...ref.slice('{project-root}/'.length).split('/'));
      const relTo = (file) => path.relative(tmpProject, file).split(path.sep).join('/');
      const files = await walkFiles(skfDir);

      assert(!(await pathExists(path.join(tmpProject, 'src'))), 'installed project has no src/ tree');

      const probeFailures = [];
      const valueFailures = [];
      const probeKeys = new Set();
      for (const file of files.filter((f) => f.endsWith('.md'))) {
        const rel = relTo(file);
        const match = (await fs.readFile(file, 'utf8')).match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
        if (!match) continue;
        let fm;
        try {
          fm = yaml.load(match[1]);
        } catch (error) {
          valueFailures.push(`${rel}: frontmatter does not parse: ${error.message.split('\n')[0]}`);
          continue;
        }
        if (!fm || typeof fm !== 'object') continue;

        for (const [key, value] of Object.entries(fm)) {
          if (key.endsWith('ProbeOrder')) {
            probeKeys.add(`${rel}#${key}`);
            const suffix = typeof value?.[0] === 'string' && value[0].startsWith(INSTALLED) ? value[0].slice(INSTALLED.length) : null;
            if (!Array.isArray(value) || value.length !== 2 || suffix === null || value[1] !== DEV + suffix) {
              probeFailures.push(`${rel} ${key}: not [${INSTALLED}<path>, ${DEV}<path>]: ${JSON.stringify(value)}`);
            } else if (!(await pathExists(inProject(value[0])))) {
              probeFailures.push(`${rel} ${key}: missing when installed: ${value[0]}`);
            } else if (!(await pathExists(path.join(projectRoot, 'src', ...suffix.split('/'))))) {
              probeFailures.push(`${rel} ${key}: missing in the dev checkout: ${value[1]}`);
            }
            continue;
          }
          for (const leaf of stringLeaves(value)) {
            for (const [ref] of leaf.matchAll(PROJECT_ROOT_PATH)) {
              const clean = ref.replace(/[.,;:]+$/, '');
              if (RUNTIME_PART.test(clean.slice('{project-root}/'.length))) continue;
              if (!(await pathExists(inProject(clean)))) valueFailures.push(`${rel} ${key}: ${clean}`);
            }
          }
        }
      }

      assert(probeKeys.size > 0, `found *ProbeOrder lists to check (${probeKeys.size})`);
      assert(
        probeKeys.has('_bmad/skf/skf-create-skill/references/validate.md#descriptionGuardProtocolProbeOrder') &&
          probeKeys.has('_bmad/skf/skf-update-skill/references/write.md#descriptionGuardProtocolProbeOrder'),
        'both description-guard callers resolve the protocol by probe order',
      );
      assert(probeFailures.length === 0, 'every *ProbeOrder is [installed, src] and resolves when installed', probeFailures.join('\n  '));
      assert(
        valueFailures.length === 0,
        'every other {project-root}/ frontmatter path resolves when installed',
        valueFailures.join('\n  '),
      );

      // Every paired {project-root}/src/<path> in any shipped file, fenced code
      // included, has an installed twin the installer actually ships.
      const twinFailures = [];
      let pairedCount = 0;
      for (const file of files.filter((f) => PAIR_SCAN_EXTENSIONS.has(path.extname(f)))) {
        for (const ref of findSrcPathRefs(await fs.readFile(file, 'utf8'))) {
          if (!ref.paired || RUNTIME_PART.test(ref.path)) continue;
          pairedCount++;
          if (!(await pathExists(path.join(skfDir, ...ref.path.split('/'))))) {
            twinFailures.push(`${relTo(file)}:${ref.line} ${INSTALLED}${ref.path}`);
          }
        }
      }
      assert(pairedCount > 0, `found paired src/ paths to check (${pairedCount})`);
      assert(twinFailures.length === 0, 'every installed twin of a src/ path exists when installed', twinFailures.join('\n  '));
    } finally {
      await fs.rm(tmpProject, { recursive: true, force: true });
    }
  } catch (error) {
    assert(false, 'installed-layout path resolution runs', error.message);
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
