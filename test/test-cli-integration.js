/**
 * CLI Integration Tests - Install/Update/Uninstall Flows
 *
 * End-to-end tests using temp directories to verify:
 * - Fresh install creates all expected files
 * - Update preserves config.yaml and replaces SKF files
 * - Uninstall removes all tracked files
 * - IDE skill installation for each target
 * - Manifest accuracy
 * - The tool report (tools/cli/lib/tool-check.js), against stub tools on a
 *   PATH the test sets: each tool's version and status against its minimum,
 *   a stub that hangs, a stub in the project folder that never runs, .cmd
 *   shims on Windows, install and update returning (not exiting) so the
 *   update notice prints after them, and a run that prints no report
 *   leaving no probe running
 *
 * Usage: node test/test-cli-integration.js
 */

const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
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
    assert(configContent.output_folder === '_bmad-output', 'config.yaml has output_folder (inherited from core config)');
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

    // Verify a workflow skill has SKILL.md with Overview section (workflow.md consolidated into SKILL.md)
    const workflowSkillDir = path.join(projectDir, '.claude/skills/skf-create-skill');
    assert(await fs.pathExists(path.join(workflowSkillDir, 'SKILL.md')), 'workflow has SKILL.md');
    const workflowContent = await fs.readFile(path.join(workflowSkillDir, 'SKILL.md'), 'utf8');
    assert(workflowContent.includes('## Overview'), 'workflow SKILL.md has Overview section');

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
// Tool report (tools/cli/lib/tool-check.js)
// ============================================================

const IS_WINDOWS = process.platform === 'win32';
const TOOL_LIST = path.join(__dirname, '..', 'src', 'shared', 'tool-requirements.yaml');
// eslint-disable-next-line no-control-regex -- the report is colored with chalk
const ANSI = /\u001B\[\d+(?:;\d+)*m/g;

/**
 * A stub tool in `dir`: a shell script on POSIX, a .cmd batch file on
 * Windows. `out` lines are echoed whatever the arguments; `posix` and
 * `windows` replace the script body.
 */
async function writeStub(dir, name, { out = [], posix, windows } = {}) {
  await fs.ensureDir(dir);
  if (IS_WINDOWS) {
    const body = windows ?? out.map((line) => `echo ${line}`);
    await fs.writeFile(path.join(dir, `${name}.cmd`), ['@echo off', ...body, ''].join('\r\n'));
    return;
  }
  const file = path.join(dir, name);
  await fs.writeFile(file, ['#!/bin/sh', ...(posix ?? out.map((line) => `echo '${line}'`)), ''].join('\n'));
  await fs.chmod(file, 0o755);
}

/** process.env with PATH replaced (every spelling of its name, for Windows). */
function envWithPath(...dirs) {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (key.toUpperCase() !== 'PATH') env[key] = value;
  }
  env.PATH = dirs.join(path.delimiter);
  return env;
}

function byKey(rows) {
  return Object.fromEntries(rows.map((row) => [row.key, row]));
}

/** The status a found version has against the shipped minimum of `key`. */
function expectedStatus(list, key, version) {
  const { compareVersions } = require('../tools/cli/lib/version-check');
  const minimum = list.tools[key].minimum;
  return minimum && compareVersions(version, minimum.includes('.') ? minimum : `${minimum}.0`) ? 'upgrade' : 'ok';
}

/** A POSIX stub that writes its process id to `pidFile`, then hangs as that same process. */
async function writePidStub(dir, name, pidFile) {
  await writeStub(dir, name, { posix: [`echo $$ > '${pidFile}'`, 'exec /bin/sleep 30'] });
}

/** The process id a stub wrote to `pidFile`, or null when none is written within `ms`. */
async function readPid(pidFile, ms = 5000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    const text = await fs.readFile(pidFile, 'utf8').catch(() => '');
    if (/^\d+\n$/.test(text)) return Number(text.trim());
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return null;
}

/** True once process `pid` has ended (a zombie has ended too), polling for up to `ms`. POSIX only. */
async function processEnded(pid, ms = 3000) {
  const deadline = Date.now() + ms;
  for (;;) {
    const ps = spawnSync('ps', ['-o', 'stat=', '-p', String(pid)], { encoding: 'utf8' });
    if (ps.status !== 0 || ps.stdout.trim().startsWith('Z')) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

/** Kill a stub a failed check left running. */
function killStub(pid) {
  try {
    process.kill(pid, 'SIGKILL');
  } catch {
    // Already gone
  }
}

/**
 * A --require preload for a CLI run: the registry check answers `version`
 * with no network and, when SKF_TEST_SPAWN_LOG is set, each process the CLI
 * spawns is logged there as "<pid> <file>" the moment it starts.
 */
async function writeCliPreload(file, version) {
  await fs.writeFile(
    file,
    [
      "const fs = require('node:fs');",
      "const https = require('node:https');",
      "const childProcess = require('node:child_process');",
      "const { EventEmitter } = require('node:events');",
      'https.get = (url, options, callback) => {',
      '  const request = new EventEmitter();',
      '  request.destroy = () => {};',
      '  process.nextTick(() => {',
      '    const response = new EventEmitter();',
      '    response.statusCode = 200;',
      '    response.resume = () => {};',
      '    callback(response);',
      `    response.emit('data', JSON.stringify({ version: '${version}' }));`,
      "    response.emit('end');",
      '  });',
      '  return request;',
      '};',
      'const spawn = childProcess.spawn;',
      'childProcess.spawn = function (file, ...rest) {',
      '  const child = spawn.call(this, file, ...rest);',
      '  if (process.env.SKF_TEST_SPAWN_LOG && child.pid) {',
      String.raw`    fs.appendFileSync(process.env.SKF_TEST_SPAWN_LOG, child.pid + ' ' + file + '\n');`,
      '  }',
      '  return child;',
      '};',
      '',
    ].join('\n'),
  );
}

/** A folder of stub tools: every tool of the list but qmd, tessl and python3. */
async function writeToolStubs(dir) {
  await writeStub(dir, 'uv', {
    posix: [
      'case "$1" in',
      '  python) echo 3.12.4 ;;',
      String.raw`  tool) printf 'ruff v0.6.0\n- ruff\ncocoindex-code v0.2.41\n- ccc\n' ;;`,
      "  *) echo 'uv 0.12.15 (stub)' ;;",
      'esac',
    ],
    windows: [
      'if "%1"=="python" (echo 3.12.4& exit /b 0)',
      'if "%1"=="tool" (echo ruff v0.6.0& echo - ruff& echo cocoindex-code v0.2.41& echo - ccc& exit /b 0)',
      'echo uv 0.12.15 (stub)',
    ],
  });
  await writeStub(dir, 'git', { out: ['git version 1.9.5'] });
  await writeStub(dir, 'gh', { out: ['gh: no version here'] });
  await writeStub(dir, 'ast-grep', { out: ['ast-grep 0.1.0'] });
  await writeStub(dir, 'ccc', { posix: ['exit 0'], windows: ['exit /b 0'] });
  await writeStub(dir, 'skill-check', { out: ['skill-check 1.2.0'] });
}

async function testToolReport() {
  console.log(`${colors.yellow}Test Suite 8: Tool Report${colors.reset}\n`);

  const root = await makeTempDir('tools');
  try {
    const { checkTools, formatReport } = require('../tools/cli/lib/tool-check');
    const list = yaml.load(await fs.readFile(TOOL_LIST, 'utf8'));
    const stubs = path.join(root, 'stubs');
    await writeToolStubs(stubs);
    const project = path.join(root, 'project');
    await fs.ensureDir(project);

    const rows = await checkTools({ projectDir: project, env: envWithPath(stubs), timeoutMs: 10_000 });
    assert(
      rows.map((row) => row.key).join(',') === Object.keys(list.tools).join(','),
      'one row per tool, in the order of tool-requirements.yaml',
      rows.map((row) => row.key).join(','),
    );
    const found = byKey(rows);
    const check = (key, version, status, label) => {
      const row = found[key];
      const ok = row && row.version === version && row.status === status && (label === undefined || row.label === label);
      assert(ok, `${key}: ${version ?? '-'} ${label ?? status}`, JSON.stringify(row));
    };
    check('node', process.versions.node, expectedStatus(list, 'node', process.versions.node));
    check('python', '3.12.4', 'ok', 'ok');
    check('uv', '0.12.15', 'ok', 'ok');
    check('git', '1.9.5', 'upgrade', `upgrade to >= ${list.tools.git.minimum}`);
    check('gh_cli', null, 'unknown', 'installed, version unknown');
    check('ast_grep', '0.1.0', 'upgrade', `upgrade to >= ${list.tools.ast_grep.minimum}`);
    check('ccc', '0.2.41', 'ok', 'ok');
    check('qmd', null, 'optional', `optional, ${list.tools.qmd.tiers[0]} tier`);
    check('tessl', null, 'optional', 'optional, runs through npx');
    check('skill_check', '1.2.0', 'ok', 'ok');
    assert(found.ast_grep.hint === list.tools.ast_grep.upgrade, 'a tool below its minimum names its upgrade command');
    assert(found.qmd.hint === list.tools.qmd.install_url, 'a missing tier tool names its install page');
    assert(found.gh_cli.hint === undefined, 'a tool with no minimum and an unreadable version gets no upgrade line');

    const lines = formatReport(rows).map((line) => line.replaceAll(ANSI, ''));
    const astLine = lines.find((line) => line.includes('ast-grep'));
    assert(lines[0].trim() === 'Tools', 'the report opens with its heading', lines[0]);
    assert(
      /^ {4}ast-grep +0\.1\.0 +upgrade to >= \S+ +npm install -g @ast-grep\/cli@latest$/.test(astLine),
      'a report line holds the tool, its version, its status and how to upgrade',
      astLine,
    );

    // The project's copy of the list (the SKF version its workflows run) decides the minimums.
    const copy = path.join(project, '_bmad', 'skf', 'shared', 'tool-requirements.yaml');
    await fs.ensureDir(path.dirname(copy));
    await fs.writeFile(copy, 'schema_version: 1\ntools:\n  ast_grep:\n    minimum: "0.1"\n');
    const pinned = byKey(await checkTools({ projectDir: project, env: envWithPath(stubs), timeoutMs: 10_000 }));
    assert(pinned.ast_grep.status === 'ok', "the project's copy of the list sets the minimums", JSON.stringify(pinned.ast_grep));
    assert(pinned.git.status === 'ok', 'a tool the copy gives no minimum has none', JSON.stringify(pinned.git));
  } catch (error) {
    assert(false, 'tool report completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testToolReportHangingStub() {
  console.log(`${colors.yellow}Test Suite 9: Tool Report With a Tool That Hangs${colors.reset}\n`);

  const root = await makeTempDir('tools-hang');
  try {
    const { checkTools, startToolCheck } = require('../tools/cli/lib/tool-check');
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'ast-grep', {
      posix: ['exec /bin/sleep 30'],
      windows: [String.raw`"%SystemRoot%\System32\ping.exe" -n 30 127.0.0.1 >nul`],
    });
    const options = { projectDir: path.join(root, 'project'), env: envWithPath(stubs) };
    const started = Date.now();
    const rows = await checkTools(options);
    const elapsed = Date.now() - started;
    const astGrep = byKey(rows).ast_grep;
    assert(astGrep.status === 'unknown', 'a probe that hangs reads as version unknown', JSON.stringify(astGrep));
    assert(elapsed < 6000, `the report waits about 3 s for a tool that hangs, not 30 s (${elapsed} ms)`);

    const printed = [];
    const origLog = console.log;
    console.log = (...args) => printed.push(args.join(' '));
    let thrown = null;
    try {
      await startToolCheck({ ...options, timeoutMs: 500 })();
    } catch (error) {
      thrown = error;
    } finally {
      console.log = origLog;
    }
    assert(thrown === null, 'printing the report never throws', thrown && thrown.message);
    assert(printed.join('\n').includes('ast-grep'), 'the report still prints every tool');

    if (!IS_WINDOWS) {
      // A command that ends without the report stops the probes instead. The
      // probe timeout is long here, so only stop() can end the stub in time.
      const pidFile = path.join(root, 'qmd.pid');
      await writePidStub(path.join(root, 'hang'), 'qmd', pidFile);
      const report = startToolCheck({ ...options, env: envWithPath(path.join(root, 'hang')), timeoutMs: 60_000 });
      const pid = await readPid(pidFile);
      report.stop();
      assert(pid !== null && (await processEnded(pid)), 'stop() ends a probe still running, with no report', `pid ${pid}`);
      if (pid) killStub(pid);
      assert(report.stop() === undefined, 'stop() can be called again');
    }
  } catch (error) {
    assert(false, 'hanging stub test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testToolReportIgnoresProjectBinaries() {
  console.log(`${colors.yellow}Test Suite 10: Tool Report Never Runs a Binary in the Project${colors.reset}\n`);

  const root = await makeTempDir('tools-planted');
  try {
    const { checkTools, resolveOutsideProject } = require('../tools/cli/lib/tool-check');
    const project = path.join(root, 'project');
    const marker = path.join(root, 'planted-stub-ran');
    const planted = {
      posix: [`: > '${marker}'`, "echo 'ast-grep 9.9.9'"],
      windows: [`type nul > "${marker}"`, 'echo ast-grep 9.9.9'],
    };
    await writeStub(project, 'ast-grep', planted);
    await writeStub(path.join(project, 'node_modules', '.bin'), 'ast-grep', planted);
    const outside = path.join(root, 'outside');
    await writeStub(outside, 'ast-grep', { out: ['ast-grep 0.45.3'] });
    const dirs = [project, path.join(project, 'node_modules', '.bin'), 'bin'];
    if (!IS_WINDOWS) {
      // A PATH folder outside the project that links into it is the project's too.
      const linked = path.join(root, 'linked');
      await fs.symlink(path.join(project, 'node_modules', '.bin'), linked);
      dirs.unshift(linked);
    }
    const env = envWithPath(...dirs, outside);
    const rows = byKey(await checkTools({ projectDir: project, env, timeoutMs: 10_000 }));
    assert(rows.ast_grep.version === '0.45.3', 'the binary outside the project answers', JSON.stringify(rows.ast_grep));
    assert(!(await fs.pathExists(marker)), 'no stub in the project folder ran');
    const resolved = resolveOutsideProject('ast-grep', { env, projectDir: project });
    assert(resolved !== null && path.dirname(resolved) === outside, 'resolution skips the project and relative PATH entries', resolved);
    assert(
      resolveOutsideProject('ast-grep', { env: envWithPath(project), projectDir: project }) === null,
      'a binary only in the project is missing',
    );
  } catch (error) {
    assert(false, 'project-binary test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testToolReportWindowsShims() {
  console.log(`${colors.yellow}Test Suite 11: .cmd Shims Run Through cmd.exe${colors.reset}\n`);

  const { commandFor } = require('../tools/cli/lib/tool-check');
  const env = { ComSpec: String.raw`C:\Windows\system32\cmd.exe` };
  const shim = commandFor(String.raw`C:\npm\ast-grep.CMD`, ['--version'], 'win32', env);
  assert(
    JSON.stringify(shim) ===
      JSON.stringify({
        file: String.raw`C:\Windows\system32\cmd.exe`,
        args: ['/d', '/s', '/c', String.raw`""C:\npm\ast-grep.CMD" --version"`],
        options: { windowsVerbatimArguments: true },
      }),
    'a .cmd shim runs through cmd.exe with a fixed command line',
    JSON.stringify(shim),
  );
  assert(commandFor(String.raw`C:\100%\ast-grep.cmd`, ['--version'], 'win32', env) === null, 'a shim path cmd.exe would expand is not run');
  assert(commandFor(String.raw`C:\npm\ast-grep.bat`, ['a b'], 'win32', env) === null, 'an argument that is not a plain word is refused');
  const exe = commandFor(String.raw`C:\bin\uv.exe`, ['--version'], 'win32', env);
  assert(exe.file === String.raw`C:\bin\uv.exe` && exe.args[0] === '--version', 'an .exe runs as it is');
  assert(commandFor('/usr/bin/ast-grep', ['--version'], 'linux').file === '/usr/bin/ast-grep', 'POSIX binaries run as they are');

  if (IS_WINDOWS) {
    // Suite 8's stubs are .cmd files on Windows: a real run through cmd.exe.
    const root = await makeTempDir('tools-cmd');
    try {
      const { checkTools } = require('../tools/cli/lib/tool-check');
      await writeStub(root, 'ast-grep', { out: ['ast-grep 0.45.3'] });
      const rows = byKey(await checkTools({ projectDir: path.join(root, 'project'), env: envWithPath(root), timeoutMs: 10_000 }));
      assert(
        rows.ast_grep.version === '0.45.3' || rows.ast_grep.status === 'unknown',
        'a .cmd stub on PATH gives its version, or version unknown',
        JSON.stringify(rows.ast_grep),
      );
    } catch (error) {
      assert(false, '.cmd stub run never throws', error.stack);
    } finally {
      await fs.remove(root);
    }
  }

  console.log('');
}

async function testCompareVersions() {
  console.log(`${colors.yellow}Test Suite 12: compareVersions Reads x.y or x.y.z${colors.reset}\n`);

  const { compareVersions, findVersion } = require('../tools/cli/lib/version-check');
  const cases = [
    ['0.45', '0.45.3', true],
    ['ast-grep 0.42.2', '0.45.3', true],
    ['0.45.3', '0.45.3', false],
    ['0.46.0', '0.45.3', false],
    ['gh version 2.101.0 (2026-09-15)', '2.15', false],
    ['2.2.0', '3.0.0-rc.1', true],
    ['3.0.0-rc.1', '3.0.0', false],
    ['v2.9.0', '2.10.0', true],
    ['no version', '1.0', false],
  ];
  for (const [current, latest, newer] of cases) {
    assert(compareVersions(current, latest) === newer, `compareVersions('${current}', '${latest}') is ${newer}`);
  }
  assert(findVersion('qmd 2.8.3 (facd35e)') === '2.8.3' && findVersion('Usage: qmd') === null, 'findVersion takes the first x.y or x.y.z');

  console.log('');
}

/**
 * Run `fn` with console output collected, PATH set to `pathDirs` and
 * process.exit refused: each call is recorded in `exits`, since the action's
 * own catch may swallow the error the refusal throws.
 */
async function captureRun(fn, pathDirs) {
  const printed = [];
  const exits = [];
  const orig = { log: console.log, error: console.error, out: process.stdout.write, err: process.stderr.write, exit: process.exit };
  const origPath = process.env.PATH;
  console.log = (...args) => printed.push(args.join(' '));
  console.error = (...args) => printed.push(args.join(' '));
  process.stdout.write = () => true;
  process.stderr.write = () => true;
  process.exit = (code) => {
    exits.push(code);
    throw new Error(`process.exit(${code}) was called`);
  };
  process.env.PATH = pathDirs.join(path.delimiter);
  let thrown = null;
  try {
    await fn();
  } catch (error) {
    thrown = error;
  } finally {
    console.log = orig.log;
    console.error = orig.error;
    process.stdout.write = orig.out;
    process.stderr.write = orig.err;
    process.exit = orig.exit;
    process.env.PATH = origPath;
  }
  return { printed: printed.join('\n').replaceAll(ANSI, ''), thrown, exits };
}

async function testInstallAndUpdateReturn() {
  console.log(`${colors.yellow}Test Suite 13: Install and Update Return, So the Update Notice Prints${colors.reset}\n`);

  const root = await makeTempDir('returns');
  const origCwd = process.cwd();
  const { UI } = require('../tools/cli/lib/ui');
  const { Installer } = require('../tools/cli/lib/installer');
  const origPrompt = UI.prototype.promptInstall;
  const origSuccess = UI.prototype.displaySuccess;
  const origInstall = Installer.prototype.install;
  try {
    const installCommand = require('../tools/cli/commands/install');
    const updateCommand = require('../tools/cli/commands/update');
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'ast-grep', { out: ['ast-grep 0.1.0'] });
    const project = path.join(root, 'project');
    await fs.ensureDir(project);
    process.chdir(project);
    UI.prototype.displaySuccess = () => {};
    const config = {
      projectDir: project,
      skfFolder: '_bmad/skf',
      project_name: 'returns-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };

    UI.prototype.promptInstall = async () => config;
    process.exitCode = undefined;
    const installed = await captureRun(() => installCommand.action(), [stubs]);
    assert(
      installed.thrown === null && installed.exits.length === 0,
      'install returns instead of calling process.exit',
      `${installed.thrown && installed.thrown.message} exits: ${installed.exits}`,
    );
    assert(process.exitCode === undefined, 'a successful install leaves the exit code alone');
    assert(/\bTools\b/.test(installed.printed) && installed.printed.includes('ast-grep'), 'install prints the tool report');

    // On POSIX a qmd stub that hangs is still running when a run ends without
    // the report. Its probe's own 3 s timeout would end it too, so the checks
    // below wait well under 3 s.
    const hang = path.join(root, 'hang');
    const pidFile = path.join(root, 'qmd.pid');
    if (!IS_WINDOWS) await writePidStub(hang, 'qmd', pidFile);
    let probePid = null;
    const probeStarted = async () => {
      if (!IS_WINDOWS) probePid = await readPid(pidFile);
    };
    const probeStopped = async () => probePid !== null && (await processEnded(probePid, 1500));

    UI.prototype.promptInstall = async () => {
      await probeStarted();
      return { cancelled: true };
    };
    const cancelled = await captureRun(() => installCommand.action(), [stubs, hang]);
    assert(
      cancelled.thrown === null && cancelled.exits.length === 0 && process.exitCode === undefined,
      'a cancelled install returns with exit code 0',
    );
    assert(!/\bTools\b/.test(cancelled.printed), 'a cancelled install prints no tool report');
    if (!IS_WINDOWS) {
      assert(await probeStopped(), 'a cancelled install stops the probes still running', `pid ${probePid}`);
      if (probePid) killStub(probePid);
    }

    const updated = await captureRun(() => updateCommand.action(), [stubs]);
    assert(
      updated.thrown === null && updated.exits.length === 0,
      'update returns instead of calling process.exit',
      `${updated.thrown && updated.thrown.message} exits: ${updated.exits}`,
    );
    assert(process.exitCode === undefined, 'a successful update leaves the exit code alone');
    assert(updated.printed.includes('ast-grep'), 'update prints the tool report');

    await fs.remove(pidFile);
    probePid = null;
    Installer.prototype.install = async () => {
      await probeStarted();
      throw new Error('disk full');
    };
    const failed = await captureRun(() => updateCommand.action(), [stubs, hang]);
    assert(
      failed.thrown === null && failed.exits.length === 0 && process.exitCode === 1,
      'a failed update returns with exit code 1',
      failed.printed,
    );
    assert(!/\bTools\b/.test(failed.printed), 'a failed update prints no tool report');
    if (!IS_WINDOWS) {
      assert(await probeStopped(), 'a failed update stops the probes still running', `pid ${probePid}`);
      if (probePid) killStub(probePid);
    }
    process.exitCode = undefined;
  } catch (error) {
    assert(false, 'install and update return without error', error.stack);
  } finally {
    UI.prototype.promptInstall = origPrompt;
    UI.prototype.displaySuccess = origSuccess;
    Installer.prototype.install = origInstall;
    process.exitCode = undefined;
    process.chdir(origCwd);
    await fs.remove(root);
  }

  console.log('');
}

async function testCliPrintsReportAndNotice() {
  console.log(`${colors.yellow}Test Suite 14: The CLI Prints the Tool Report, Then the Update Notice${colors.reset}\n`);

  const root = await makeTempDir('cli-notice');
  try {
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'ast-grep', { out: ['ast-grep 0.1.0'] });
    // The registry check, answered here with a newer version: no network.
    const preload = path.join(root, 'fake-registry.js');
    await writeCliPreload(preload, '999.0.0');
    const project = path.join(root, 'project');
    await fs.ensureDir(project);
    const { Installer } = require('../tools/cli/lib/installer');
    const restore = suppressConsole();
    await new Installer().install({
      projectDir: project,
      skfFolder: '_bmad/skf',
      project_name: 'notice-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    });
    restore();

    const cli = path.join(__dirname, '..', 'tools', 'cli', 'skf-cli.js');
    for (const command of ['update', 'status']) {
      const run = spawnSync(process.execPath, ['--require', preload, cli, command], {
        cwd: project,
        env: envWithPath(stubs),
        encoding: 'utf8',
        timeout: 120_000,
      });
      const stdout = (run.stdout || '').replaceAll(ANSI, '');
      const stderr = (run.stderr || '').replaceAll(ANSI, '');
      assert(run.status === 0, `${command} exits 0`, `${run.status} ${run.error || ''} ${stderr}`);
      assert(/\n {2}Tools\n/.test(stdout) && /ast-grep +0\.1\.0 +upgrade to >= /.test(stdout), `${command} prints the tool report`, stdout);
      assert(stderr.includes('Update available') && stderr.includes('999.0.0'), `the update notice prints after ${command}`, stderr);
    }
  } catch (error) {
    assert(false, 'CLI report and notice test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testCliStopsProbesWithoutReport() {
  console.log(`${colors.yellow}Test Suite 15: A CLI Run That Prints No Tool Report Leaves No Probe Running${colors.reset}\n`);

  if (IS_WINDOWS) {
    // libuv's kill-on-close job object ends every child with the CLI on Windows.
    console.log(`${colors.dim}  skipped on Windows${colors.reset}\n`);
    return;
  }
  const root = await makeTempDir('cli-no-report');
  const left = [];
  try {
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'qmd', { posix: ['exec /bin/sleep 30'] });
    const qmd = path.join(stubs, 'qmd');
    const preload = path.join(root, 'cli-preload.js');
    await writeCliPreload(preload, '0.0.1');
    // update in a folder without SKF, and status where _bmad/skf is a file, which it cannot read.
    const bare = path.join(root, 'bare');
    const broken = path.join(root, 'broken');
    await fs.ensureDir(bare);
    await fs.outputFile(path.join(broken, '_bmad', 'skf'), 'not a folder\n');

    const cli = path.join(__dirname, '..', 'tools', 'cli', 'skf-cli.js');
    for (const [command, cwd, status] of [
      ['update', bare, 0],
      ['status', broken, 1],
    ]) {
      const log = path.join(root, `${command}-spawned.log`);
      const run = spawnSync(process.execPath, ['--require', preload, cli, command], {
        cwd,
        env: { ...envWithPath(stubs), SKF_TEST_SPAWN_LOG: log },
        encoding: 'utf8',
        timeout: 60_000,
      });
      assert(run.status === status, `${command} exits ${status}`, `${run.status} ${run.error || ''} ${run.stderr}`);
      const spawned = (await fs.readFile(log, 'utf8').catch(() => '')).split('\n');
      const pid = Number(spawned.find((line) => line.endsWith(` ${qmd}`))?.split(' ')[0]) || null;
      if (pid) left.push(pid);
      assert(pid !== null, `${command} starts the qmd probe`, spawned.join('\n'));
      assert(
        pid !== null && (await processEnded(pid)),
        `${command} stops the probe still running when it ends without the report`,
        `pid ${pid}`,
      );
    }
  } catch (error) {
    assert(false, 'CLI probe stop test completes without error', error.stack);
  } finally {
    for (const pid of left) killStub(pid);
    await fs.remove(root);
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
  await testToolReport();
  await testToolReportHangingStub();
  await testToolReportIgnoresProjectBinaries();
  await testToolReportWindowsShims();
  await testCompareVersions();
  await testInstallAndUpdateReturn();
  await testCliPrintsReportAndNotice();
  await testCliStopsProbesWithoutReport();

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
