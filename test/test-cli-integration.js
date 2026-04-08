/**
 * CLI Integration Tests - Install/Update/Uninstall Flows
 *
 * End-to-end tests using temp directories to verify:
 * - Fresh install creates all expected files
 * - Update preserves config.yaml and replaces SKF files
 * - Uninstall removes all tracked files
 * - IDE skill installation for each target
 * - Manifest accuracy
 *
 * Usage: node test/test-cli-integration.js
 */

const path = require('node:path');
const os = require('node:os');
const fs = require('fs-extra');
const yaml = require('js-yaml');

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
 * Create a temp directory for a test case.
 */
async function makeTempDir(label) {
  const dir = path.join(os.tmpdir(), `skf-test-${label}-${Date.now()}`);
  await fs.ensureDir(dir);
  return dir;
}

/**
 * Suppress ora spinners, console.log, and stderr writes during install to keep test output clean.
 */
function suppressConsole() {
  const origLog = console.log;
  const origStdoutWrite = process.stdout.write;
  const origStderrWrite = process.stderr.write;
  console.log = () => {};
  process.stdout.write = () => true;
  process.stderr.write = () => true;
  return () => {
    console.log = origLog;
    process.stdout.write = origStdoutWrite;
    process.stderr.write = origStderrWrite;
  };
}

// ============================================================
// Test Suites
// ============================================================

async function testFreshInstall() {
  console.log(`${colors.yellow}Test Suite 1: Fresh Install${colors.reset}\n`);

  const projectDir = await makeTempDir('fresh');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'test-project',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: ['claude-code'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    const result = await installer.install(config);
    restore();

    assert(result.success === true, 'install returns success');

    // Verify SKF directory structure
    const skfDir = path.join(projectDir, '_bmad/skf');
    assert(await fs.pathExists(skfDir), 'SKF directory created');
    assert(await fs.pathExists(path.join(skfDir, 'knowledge')), 'knowledge/ directory created');
    assert(await fs.pathExists(path.join(skfDir, 'shared')), 'shared/ directory created');

    // Verify at least one skf-* skill directory was created
    const skfEntries = (await fs.readdir(skfDir)).filter((e) => e.startsWith('skf-'));
    assert(skfEntries.length > 0, `skill directories created (found ${skfEntries.length})`);

    // Verify config.yaml
    const configPath = path.join(skfDir, 'config.yaml');
    assert(await fs.pathExists(configPath), 'config.yaml created');
    const configContent = yaml.load(await fs.readFile(configPath, 'utf8'));
    assert(configContent.project_name === 'test-project', 'config.yaml has correct project_name');
    assert(configContent.skills_output_folder === 'skills', 'config.yaml has correct skills_output_folder');
    assert(Array.isArray(configContent.ides) && configContent.ides.includes('claude-code'), 'config.yaml has IDEs');

    // Verify skills installed to IDE directory (.claude/skills/)
    const claudeSkillsDir = path.join(projectDir, '.claude', 'skills');
    assert(await fs.pathExists(path.join(claudeSkillsDir, 'skf-forger', 'SKILL.md')), 'agent skill installed to .claude/skills/');
    assert(await fs.pathExists(path.join(claudeSkillsDir, 'skf-create-skill', 'SKILL.md')), 'workflow skill installed to .claude/skills/');
    assert(await fs.pathExists(path.join(claudeSkillsDir, 'knowledge')), 'knowledge/ installed to .claude/skills/');

    // Verify sidecar
    const sidecarDir = path.join(projectDir, '_bmad/_memory/forger-sidecar');
    assert(await fs.pathExists(sidecarDir), 'sidecar directory created');

    // Verify output folders
    assert(await fs.pathExists(path.join(projectDir, 'skills')), 'skills/ output folder created');
    assert(await fs.pathExists(path.join(projectDir, 'forge-data')), 'forge-data/ output folder created');
    assert(await fs.pathExists(path.join(projectDir, 'skills/.gitkeep')), 'skills/.gitkeep created');
    assert(await fs.pathExists(path.join(projectDir, 'forge-data/.gitkeep')), 'forge-data/.gitkeep created');

    // Verify learning material
    assert(await fs.pathExists(path.join(projectDir, '_skf-learn')), '_skf-learn/ directory created');

    // Verify manifest
    const manifestPath = path.join(projectDir, '_bmad/_config/skf-manifest.yaml');
    assert(await fs.pathExists(manifestPath), 'manifest created');
    const manifest = yaml.load(await fs.readFile(manifestPath, 'utf8'));
    assert(manifest.module === 'skf', 'manifest has module: skf');
    assert(manifest.action === 'fresh', 'manifest has action: fresh');
    assert(Array.isArray(manifest.files.skf) && manifest.files.skf.length > 0, 'manifest tracks SKF files');
    assert(Array.isArray(manifest.files.sidecar) && manifest.files.sidecar.length > 0, 'manifest tracks sidecar files');

    // Verify IDE skills
    const claudeSkillsDirManifest = path.join(projectDir, '.claude/skills');
    assert(await fs.pathExists(claudeSkillsDirManifest), '.claude/skills/ created');
    const skillEntries = await fs.readdir(claudeSkillsDirManifest);
    const agentSkills = skillEntries.filter((f) => f.startsWith('skf-') && f.includes('forger'));
    const workflowSkills = skillEntries.filter((f) => f.startsWith('skf-') && !f.includes('forger'));
    assert(agentSkills.length > 0, `agent skill directories installed (found ${agentSkills.length})`);
    assert(workflowSkills.length > 0, `workflow skill directories installed (found ${workflowSkills.length})`);

    // Verify manifest tracks IDE files
    assert(Array.isArray(manifest.files.ide_skills) && manifest.files.ide_skills.length > 0, 'manifest tracks IDE skill files');
  } catch (error) {
    assert(false, 'fresh install completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testUpdatePreservesConfig() {
  console.log(`${colors.yellow}Test Suite 2: Update Preserves Config${colors.reset}\n`);

  const projectDir = await makeTempDir('update');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Step 1: Fresh install
    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'original-name',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: ['cursor'],
      install_learning: false,
      _action: 'fresh',
    };

    let restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify initial config
    const skfDir = path.join(projectDir, '_bmad/skf');
    const configPath = path.join(skfDir, 'config.yaml');
    const origConfig = await fs.readFile(configPath, 'utf8');
    assert(origConfig.includes('original-name'), 'initial config has original project name');

    // Add a marker file to sidecar to verify it persists
    const sidecarMarker = path.join(projectDir, '_bmad/_memory/forger-sidecar/user-state.yaml');
    await fs.writeFile(sidecarMarker, 'custom: state\n', 'utf8');

    // Step 2: Update
    const updateConfig = {
      projectDir,
      skfFolder: '_bmad/skf',
      _action: 'update',
    };

    restore = suppressConsole();
    const result = await installer.install(updateConfig);
    restore();

    assert(result.success === true, 'update returns success');

    // Config should be preserved
    const updatedConfig = await fs.readFile(configPath, 'utf8');
    assert(updatedConfig.includes('original-name'), 'config.yaml preserved after update');

    // SKF files should still exist
    const skfDirsAfterUpdate = (await fs.readdir(skfDir)).filter((e) => e.startsWith('skf-'));
    assert(skfDirsAfterUpdate.length > 0, 'skill directories exist after update');
    assert(await fs.pathExists(path.join(skfDir, 'knowledge')), 'knowledge/ exists after update');

    // Sidecar user state should persist (sidecar files are not overwritten)
    assert(await fs.pathExists(sidecarMarker), 'sidecar user state preserved after update');

    // Manifest should reflect update action
    const manifestPath = path.join(projectDir, '_bmad/_config/skf-manifest.yaml');
    const manifest = yaml.load(await fs.readFile(manifestPath, 'utf8'));
    assert(manifest.action === 'update', 'manifest action is update');
  } catch (error) {
    assert(false, 'update flow completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testUninstallCleansUp() {
  console.log(`${colors.yellow}Test Suite 3: Uninstall Cleanup${colors.reset}\n`);

  const projectDir = await makeTempDir('uninstall');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../tools/cli/lib/manifest');
    const installer = new Installer();

    // Install first
    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'uninstall-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: ['claude-code', 'cursor'],
      install_learning: true,
      _action: 'fresh',
    };

    let restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify files exist before uninstall
    assert(await fs.pathExists(path.join(projectDir, '_bmad/skf')), 'SKF dir exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '_skf-learn')), '_skf-learn exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '.claude/skills')), '.claude/skills exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '.cursor/skills')), '.cursor/skills exists before uninstall');

    // Read manifest
    const manifest = await readManifest(projectDir);
    assert(manifest !== null, 'manifest exists before uninstall');

    // Simulate uninstall: remove all tracked files (mirrors uninstall.js logic without interactive prompt)
    restore = suppressConsole();

    // Remove IDE skill directories (directory-level cleanup, not file-by-file)
    for (const dir of manifest.directories || []) {
      const dirPath = path.join(projectDir, dir);
      if (await fs.pathExists(dirPath)) await fs.remove(dirPath);
      // Clean empty parent (e.g., .claude/ after removing .claude/skills)
      const parentDir = path.dirname(dirPath);
      if (await fs.pathExists(parentDir)) {
        const entries = await fs.readdir(parentDir);
        if (entries.length === 0) await fs.remove(parentDir);
      }
    }

    // Remove learning
    const learnDir = path.join(projectDir, '_skf-learn');
    if (await fs.pathExists(learnDir)) await fs.remove(learnDir);

    // Remove output scaffolding
    for (const file of manifest.files.output || []) {
      const fullPath = path.join(projectDir, file);
      if (await fs.pathExists(fullPath)) await fs.remove(fullPath);
    }
    for (const folder of [manifest.skills_output_folder, manifest.forge_data_folder]) {
      if (folder) {
        const dirPath = path.join(projectDir, folder);
        if (await fs.pathExists(dirPath)) {
          const entries = await fs.readdir(dirPath);
          if (entries.length === 0) await fs.remove(dirPath);
        }
      }
    }

    // Remove sidecar
    const sidecarDir = path.join(projectDir, '_bmad/_memory/forger-sidecar');
    if (await fs.pathExists(sidecarDir)) await fs.remove(sidecarDir);
    const memoryDir = path.join(projectDir, '_bmad/_memory');
    if (await fs.pathExists(memoryDir)) {
      const entries = await fs.readdir(memoryDir);
      if (entries.length === 0) await fs.remove(memoryDir);
    }

    // Remove SKF module
    const skfDir = path.join(projectDir, manifest.skf_folder);
    if (await fs.pathExists(skfDir)) await fs.remove(skfDir);

    // Remove manifest
    const manifestPath = path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE);
    if (await fs.pathExists(manifestPath)) await fs.remove(manifestPath);
    const configDir = path.join(projectDir, MANIFEST_DIR);
    if (await fs.pathExists(configDir)) {
      const entries = await fs.readdir(configDir);
      if (entries.length === 0) await fs.remove(configDir);
    }
    const bmadDir = path.join(projectDir, '_bmad');
    if (await fs.pathExists(bmadDir)) {
      const entries = await fs.readdir(bmadDir);
      if (entries.length === 0) await fs.remove(bmadDir);
    }

    restore();

    // Verify everything is cleaned up
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad/skf'))), 'SKF dir removed');
    assert(!(await fs.pathExists(path.join(projectDir, '_skf-learn'))), '_skf-learn removed');
    assert(!(await fs.pathExists(path.join(projectDir, '.claude/skills'))), '.claude/skills removed');
    assert(!(await fs.pathExists(path.join(projectDir, '.cursor/skills'))), '.cursor/skills removed');
    assert(!(await fs.pathExists(path.join(projectDir, 'skills'))), 'skills/ output folder removed');
    assert(!(await fs.pathExists(path.join(projectDir, 'forge-data'))), 'forge-data/ output folder removed');
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad'))), '_bmad/ cleaned up (empty)');
  } catch (error) {
    assert(false, 'uninstall flow completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testIdeCommandGeneration() {
  console.log(`${colors.yellow}Test Suite 4: IDE Skill Installation${colors.reset}\n`);

  const projectDir = await makeTempDir('ide-cmds');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Test with a subset of IDEs (claude-code and cursor represent the pattern)
    const testIdes = ['claude-code', 'cursor'];

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'ide-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: testIdes,
      install_learning: false,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify each IDE got skill directories (not command files)
    const ideSkillDirs = {
      'claude-code': '.claude/skills',
      cursor: '.cursor/skills',
    };

    for (const [ide, targetDir] of Object.entries(ideSkillDirs)) {
      const fullDir = path.join(projectDir, targetDir);
      const exists = await fs.pathExists(fullDir);
      assert(exists, `${ide}: ${targetDir}/ created`);

      if (exists) {
        const entries = await fs.readdir(fullDir);
        const skillDirs = entries.filter((e) => e.startsWith('skf-'));
        assert(skillDirs.length > 0, `${ide}: has skill directories`);
        assert(skillDirs.includes('skf-forger'), `${ide}: has skf-forger agent skill`);
        assert(skillDirs.includes('skf-create-skill'), `${ide}: has skf-create-skill workflow skill`);

        // Verify supporting resources copied alongside skills
        assert(entries.includes('knowledge'), `${ide}: has knowledge/ directory`);
        assert(entries.includes('shared'), `${ide}: has shared/ directory`);
      }
    }

    // Verify SKILL.md exists in agent skill directory
    const agentSkillMd = path.join(projectDir, '.claude/skills/skf-forger/SKILL.md');
    assert(await fs.pathExists(agentSkillMd), 'agent SKILL.md exists in .claude/skills/');

    // Verify a workflow skill has SKILL.md + workflow.md
    const workflowSkillDir = path.join(projectDir, '.claude/skills/skf-create-skill');
    assert(await fs.pathExists(path.join(workflowSkillDir, 'SKILL.md')), 'workflow has SKILL.md');
    assert(await fs.pathExists(path.join(workflowSkillDir, 'workflow.md')), 'workflow has workflow.md');

    // Verify relative paths resolve correctly: knowledge/ is sibling of skills
    const knowledgeDir = path.join(projectDir, '.claude/skills/knowledge');
    assert(await fs.pathExists(knowledgeDir), 'knowledge/ copied alongside skills for path resolution');
  } catch (error) {
    assert(false, 'IDE command generation completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testManifestAccuracy() {
  console.log(`${colors.yellow}Test Suite 5: Manifest Accuracy${colors.reset}\n`);

  const projectDir = await makeTempDir('manifest');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const { readManifest } = require('../tools/cli/lib/manifest');
    const installer = new Installer();

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'manifest-test',
      skills_output_folder: 'my-skills',
      forge_data_folder: 'my-forge',
      ides: ['claude-code'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const manifest = await readManifest(projectDir);
    assert(manifest !== null, 'manifest readable');

    // Verify every file in manifest actually exists on disk
    let allExist = true;
    let missingFiles = [];
    const allFiles = [
      ...manifest.files.skf,
      ...manifest.files.sidecar,
      ...manifest.files.ide_skills,
      ...manifest.files.learning,
      ...manifest.files.output,
    ];

    for (const file of allFiles) {
      if (!(await fs.pathExists(path.join(projectDir, file)))) {
        allExist = false;
        missingFiles.push(file);
      }
    }
    assert(allExist, `all ${allFiles.length} manifest files exist on disk`, missingFiles.join(', '));

    // Verify manifest metadata
    assert(manifest.skf_folder === '_bmad/skf', 'manifest has correct skf_folder');
    assert(manifest.skills_output_folder === 'my-skills', 'manifest has correct skills_output_folder');
    assert(manifest.forge_data_folder === 'my-forge', 'manifest has correct forge_data_folder');
    assert(typeof manifest.version === 'string' && manifest.version.length > 0, 'manifest has version');
    assert(typeof manifest.installed_at === 'string', 'manifest has installed_at timestamp');

    // Verify directories list
    assert(Array.isArray(manifest.directories), 'manifest has directories array');
    assert(manifest.directories.includes('_bmad/skf'), 'directories includes SKF folder');
    assert(manifest.directories.includes('_bmad/_memory/forger-sidecar'), 'directories includes sidecar');
  } catch (error) {
    assert(false, 'manifest accuracy test completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testFreshInstallWithoutLearning() {
  console.log(`${colors.yellow}Test Suite 6: Install Without Learning Material${colors.reset}\n`);

  const projectDir = await makeTempDir('no-learn');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'no-learn-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    assert(!(await fs.pathExists(path.join(projectDir, '_skf-learn'))), 'no _skf-learn when learning disabled');

    // Manifest should have empty learning files list
    const { readManifest } = require('../tools/cli/lib/manifest');
    const manifest = await readManifest(projectDir);
    assert(manifest.files.learning.length === 0, 'manifest has no learning files');
    assert(manifest.files.ide_skills.length === 0, 'manifest has no IDE skill files (no IDEs selected)');
  } catch (error) {
    assert(false, 'install without learning completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testGitignoreEntries() {
  console.log(`${colors.yellow}Test Suite 7: .gitignore Entries${colors.reset}\n`);

  // Case A: No .gitignore — creates one
  const dirA = await makeTempDir('gitignore-new');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    const config = {
      projectDir: dirA,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const giPath = path.join(dirA, '.gitignore');
    assert(await fs.pathExists(giPath), 'creates .gitignore when none exists');
    const content = await fs.readFile(giPath, 'utf8');
    assert(content.includes('_bmad/_memory/'), '.gitignore contains _bmad/_memory/');
  } catch (error) {
    assert(false, 'gitignore creation test', error.message);
  } finally {
    await fs.remove(dirA);
  }

  // Case B: Existing .gitignore without entry — appends
  const dirB = await makeTempDir('gitignore-append');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirB, '.gitignore'), 'node_modules/\n.env\n', 'utf8');
    const config = {
      projectDir: dirB,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const content = await fs.readFile(path.join(dirB, '.gitignore'), 'utf8');
    assert(content.includes('node_modules/'), 'preserves existing entries');
    assert(content.includes('_bmad/_memory/'), 'appends _bmad/_memory/ entry');
    const occurrences = content.split('_bmad/_memory/').length - 1;
    assert(occurrences === 1, 'entry appears exactly once');
  } catch (error) {
    assert(false, 'gitignore append test', error.message);
  } finally {
    await fs.remove(dirB);
  }

  // Case C: .gitignore already has entry — no duplicate
  const dirC = await makeTempDir('gitignore-dup');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirC, '.gitignore'), 'node_modules/\n_bmad/_memory/\n', 'utf8');
    const config = {
      projectDir: dirC,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const content = await fs.readFile(path.join(dirC, '.gitignore'), 'utf8');
    const occurrences = content.split('_bmad/_memory/').length - 1;
    assert(occurrences === 1, 'does not duplicate existing entry');
  } catch (error) {
    assert(false, 'gitignore no-duplicate test', error.message);
  } finally {
    await fs.remove(dirC);
  }

  // Case D: .gitignore without trailing newline — appends cleanly
  const dirD = await makeTempDir('gitignore-nonl');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirD, '.gitignore'), 'node_modules/', 'utf8');
    const config = {
      projectDir: dirD,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const content = await fs.readFile(path.join(dirD, '.gitignore'), 'utf8');
    assert(!content.includes('node_modules/_bmad'), 'entry on its own line (not appended to previous)');
    assert(content.includes('_bmad/_memory/'), 'entry present after no-newline file');
  } catch (error) {
    assert(false, 'gitignore no-trailing-newline test', error.message);
  } finally {
    await fs.remove(dirD);
  }

  console.log('');
}

// ============================================================
// Runner
// ============================================================

async function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('SKF CLI Integration Tests');
  console.log(`========================================${colors.reset}\n`);

  await testFreshInstall();
  await testUpdatePreservesConfig();
  await testUninstallCleansUp();
  await testIdeCommandGeneration();
  await testManifestAccuracy();
  await testFreshInstallWithoutLearning();
  await testGitignoreEntries();

  console.log(`${colors.cyan}========================================`);
  console.log('Test Results:');
  console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
  console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`========================================${colors.reset}\n`);

  if (failed === 0) {
    console.log(`${colors.green}✨ All CLI integration tests passed!${colors.reset}\n`);
    process.exit(0);
  } else {
    console.log(`${colors.red}❌ Some CLI integration tests failed${colors.reset}\n`);
    process.exit(1);
  }
}

runTests().catch((error) => {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
});
