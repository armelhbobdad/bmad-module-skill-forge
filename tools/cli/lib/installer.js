/**
 * SKF Installer - Core orchestrator
 * Copies SKF source files, installs skills to IDEs, creates folder structure.
 */

const path = require('node:path');
const fs = require('fs-extra');
const { spinner } = require('@clack/prompts');
const yaml = require('js-yaml');
const { installSkillsToIdes } = require('./ide-skills');
const { writeManifest } = require('./manifest');

class Installer {
  constructor() {
    // Resolve directories relative to this file (tools/cli/lib/ -> up 3 levels)
    const repoRoot = path.resolve(__dirname, '..', '..', '..');
    this.srcDir = path.join(repoRoot, 'src');
    this.docsDir = path.join(repoRoot, 'docs');
  }

  async install(config) {
    const { projectDir, skfFolder } = config;
    const skfDir = path.join(projectDir, skfFolder);
    const action = config._action || 'fresh';
    const s = spinner();

    // Handle update vs fresh for existing installation
    if (action === 'update' && (await fs.pathExists(skfDir))) {
      const configPath = path.join(skfDir, 'config.yaml');
      if (!config._savedConfigYaml && (await fs.pathExists(configPath))) {
        config._savedConfigYaml = await fs.readFile(configPath, 'utf8');
      }

      // On update, extract settings from saved config
      if (config._savedConfigYaml) {
        try {
          const savedData = yaml.load(config._savedConfigYaml);
          if (!config.ides && savedData.ides) config.ides = savedData.ides;
          if (!config.skills_output_folder && savedData.skills_output_folder) config.skills_output_folder = savedData.skills_output_folder;
          if (!config.forge_data_folder && savedData.forge_data_folder) config.forge_data_folder = savedData.forge_data_folder;
          if (config.install_learning == null && savedData.install_learning != null) config.install_learning = savedData.install_learning;
        } catch {
          /* ignore parse errors, defaults will apply */
        }
      }

      s.start('Updating SKF files...');
      await fs.remove(skfDir);
      s.stop('Old files cleared');
    } else if (action === 'fresh' && (await fs.pathExists(skfDir))) {
      s.start('Removing existing SKF installation...');
      await fs.remove(skfDir);
      s.stop('Old installation removed');
    }

    // Ensure parent directory exists (for _bmad/skf/)
    await fs.ensureDir(path.dirname(skfDir));

    // Step 1: Copy source files
    s.start('Copying SKF files...');
    try {
      await this.copySrcFiles(skfDir);
      s.stop('SKF files copied');
    } catch (error) {
      s.stop('Failed to copy SKF files');
      throw error;
    }

    // Step 2: Setup agent sidecar
    s.start('Setting up agent sidecar...');
    try {
      await this.setupSidecar(projectDir);
      s.stop('Agent sidecar initialized');
    } catch (error) {
      s.stop('Failed to setup sidecar');
      throw error;
    }

    // Step 2b: Update .gitignore
    await this.updateGitignore(projectDir);

    // Step 3: Write config.yaml
    s.start('Writing configuration...');
    try {
      await this.writeConfig(skfDir, config);
      s.stop('Configuration saved');
    } catch (error) {
      s.stop('Failed to write configuration');
      throw error;
    }

    // Step 4: Create output folders
    s.start('Creating project folders...');
    try {
      await this.createOutputFolders(projectDir, config);
      s.stop('Project folders created');
    } catch (error) {
      s.stop('Failed to create project folders');
      throw error;
    }

    // Step 5: Copy learning material (optional)
    if (config.install_learning !== false) {
      s.start('Copying learning & reference material...');
      try {
        await this.copyLearningMaterial(projectDir);
        s.stop('Learning material added to _skf-learn/');
      } catch (error) {
        s.stop('Failed to copy learning material');
        throw error;
      }
    }

    // Step 6: Install skills to selected IDEs
    let ideDirectories = [];
    const selectedIdes = config.ides || [];
    if (selectedIdes.length > 0 && !selectedIdes.every((ide) => ide === 'other')) {
      s.start('Installing skills to IDEs...');
      try {
        const ideResult = await installSkillsToIdes(projectDir, skfDir, selectedIdes);
        ideDirectories = ideResult.directories || [];
        if (ideResult.installed > 0) {
          s.stop(`Skills installed for ${ideResult.ides.join(', ')}`);
        } else {
          s.stop('No IDE skill installation needed');
        }
      } catch (error) {
        s.stop('Failed to install skills to IDEs');
        throw error;
      }
    }

    // Step 7: Write installation manifest
    s.start('Writing manifest...');
    try {
      const packageJson = require('../../../package.json');
      await writeManifest(projectDir, config, {
        version: packageJson.version,
        ideDirectories,
      });
      s.stop('Installation manifest saved');
    } catch (error) {
      s.stop('Failed to write manifest');
      throw error;
    }

    return { success: true, skfDir, projectDir };
  }

  /**
   * Copy src/ content into the target SKF directory.
   * Skill directories (skf-*) are copied flat alongside module-level resources.
   */
  async copySrcFiles(skfDir) {
    // Copy skill directories (skf-*) — each is a self-contained skill
    const srcEntries = await fs.readdir(this.srcDir, { withFileTypes: true });
    for (const entry of srcEntries) {
      if (entry.isDirectory() && entry.name.startsWith('skf-')) {
        await fs.copy(path.join(this.srcDir, entry.name), path.join(skfDir, entry.name));
      }
    }

    // Copy module-level resources
    for (const dir of ['knowledge', 'shared']) {
      const src = path.join(this.srcDir, dir);
      const dest = path.join(skfDir, dir);
      if (await fs.pathExists(src)) {
        await fs.copy(src, dest);
      }
    }

    // Copy module.yaml and module-help.csv
    for (const file of ['module.yaml', 'module-help.csv']) {
      const src = path.join(this.srcDir, file);
      if (await fs.pathExists(src)) {
        await fs.copy(src, path.join(skfDir, file));
      }
    }

    // Write VERSION file for SKF version resolution in installed projects
    const packageJson = require('../../../package.json');
    await fs.writeFile(path.join(skfDir, 'VERSION'), packageJson.version, 'utf8');
  }

  /**
   * Setup the ferris sidecar directory with template files.
   * Existing sidecar files are preserved (they contain user state).
   */
  async setupSidecar(projectDir) {
    const sidecarDir = path.join(projectDir, '_bmad', '_memory', 'forger-sidecar');
    await fs.ensureDir(sidecarDir);

    const forgerSrc = path.join(this.srcDir, 'forger');
    if (await fs.pathExists(forgerSrc)) {
      const files = await fs.readdir(forgerSrc);
      for (const file of files) {
        if (file.endsWith('.yaml') || file.endsWith('.yml')) {
          const dest = path.join(sidecarDir, file);
          // Don't overwrite existing sidecar files (preserves user state)
          if (!(await fs.pathExists(dest))) {
            await fs.copy(path.join(forgerSrc, file), dest);
          }
        }
      }
    }
  }

  async writeConfig(skfDir, config) {
    // On update, restore the user's existing config
    if (config._savedConfigYaml) {
      await fs.writeFile(path.join(skfDir, 'config.yaml'), config._savedConfigYaml, 'utf8');
      return;
    }

    // Get user name from git or system
    const getUserName = () => {
      try {
        const { execSync } = require('node:child_process');
        return execSync('git config user.name', { encoding: 'utf8' }).trim() || 'Developer';
      } catch {
        return 'Developer';
      }
    };

    const configData = {
      user_name: getUserName(),
      project_name: config.project_name || 'Untitled Project',
      communication_language: 'en',
      document_output_language: 'en',
      skills_output_folder: config.skills_output_folder || 'skills',
      forge_data_folder: config.forge_data_folder || 'forge-data',
      sidecar_path: '_bmad/_memory/forger-sidecar',
      skf_folder: config.skfFolder,
      ides: config.ides || [],
      install_learning: config.install_learning !== false,
    };

    const yamlStr = yaml.dump(configData, { lineWidth: -1 });
    await fs.writeFile(path.join(skfDir, 'config.yaml'), `# SKF Configuration - Generated by installer\n${yamlStr}`, 'utf8');
  }

  async createOutputFolders(projectDir, config) {
    const skillsFolder = config.skills_output_folder || 'skills';
    const forgeDataFolder = config.forge_data_folder || 'forge-data';

    for (const folder of [skillsFolder, forgeDataFolder]) {
      const folderPath = path.join(projectDir, folder);
      if (!(await fs.pathExists(folderPath))) {
        await fs.ensureDir(folderPath);
        await fs.writeFile(path.join(folderPath, '.gitkeep'), '# This file ensures the directory is tracked by git\n');
      }
    }
  }

  async updateGitignore(projectDir) {
    const gitignorePath = path.join(projectDir, '.gitignore');
    const entry = '_bmad/_memory/';

    try {
      if (await fs.pathExists(gitignorePath)) {
        const content = await fs.readFile(gitignorePath, 'utf8');
        // Check if entry already present (exact line match)
        const lines = content.split('\n');
        if (lines.some((line) => line.trim() === entry)) return;
        // Append with preceding newline if file doesn't end with one
        const prefix = content.endsWith('\n') ? '' : '\n';
        await fs.appendFile(gitignorePath, `${prefix}${entry}\n`, 'utf8');
      } else {
        await fs.writeFile(gitignorePath, `${entry}\n`, 'utf8');
      }
    } catch {
      // Non-critical — don't fail the install over .gitignore
    }
  }

  async copyLearningMaterial(projectDir) {
    const learnDir = path.join(projectDir, '_skf-learn');
    if (await fs.pathExists(this.docsDir)) {
      await fs.copy(this.docsDir, learnDir, {
        filter: (srcPath) => {
          // Skip website-specific files
          return !path.basename(srcPath).startsWith('404');
        },
      });
    }
  }
}

module.exports = { Installer };
