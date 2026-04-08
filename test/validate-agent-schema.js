/**
 * Agent & Manifest Schema Validator CLI
 *
 * Scans all *.agent.yaml and bmad-skill-manifest.yaml files under src/
 * and validates them against their respective Zod schemas.
 *
 * Usage: node tools/validate-agent-schema.js [project_root]
 * Exit codes: 0 = success, 1 = validation failures
 *
 * Optional argument:
 *   project_root - Directory to scan (defaults to BMAD repo root)
 */

const { glob } = require('glob');
const yaml = require('yaml');
const fs = require('node:fs');
const path = require('node:path');
const { validateAgentFile, validateManifestFile } = require('./schema/agent.js');

/**
 * Main validation routine
 * @param {string} [customProjectRoot] - Optional project root to scan (for testing)
 */
async function main(customProjectRoot) {
  console.log('🔍 Scanning for agent and manifest files...\n');

  // Determine project root: use custom path if provided, otherwise default to repo root
  const project_root = customProjectRoot || path.join(__dirname, '..');

  // Find all agent files and manifest files
  const [agentFiles, manifestFiles] = await Promise.all([
    glob('src/**/*.agent.yaml', { cwd: project_root, absolute: true }),
    glob('src/**/bmad-skill-manifest.yaml', { cwd: project_root, absolute: true }),
  ]);

  const totalFiles = agentFiles.length + manifestFiles.length;

  if (totalFiles === 0) {
    console.log('ℹ️  No agent or manifest files found. Skipping schema validation.\n');
    process.exit(0);
  }

  console.log(`Found ${agentFiles.length} agent file(s), ${manifestFiles.length} manifest file(s)\n`);

  const errors = [];

  // Validate agent files
  for (const filePath of agentFiles) {
    const relativePath = path.relative(process.cwd(), filePath);

    try {
      const fileContent = fs.readFileSync(filePath, 'utf8');
      const agentData = yaml.parse(fileContent);

      // Convert absolute path to relative src/ path for module detection
      const srcRelativePath = relativePath.startsWith('src/') ? relativePath : path.relative(project_root, filePath).replaceAll('\\', '/');

      const result = validateAgentFile(srcRelativePath, agentData);

      if (result.success) {
        console.log(`✅ ${relativePath}`);
      } else {
        errors.push({
          file: relativePath,
          issues: result.error.issues,
        });
      }
    } catch (error) {
      errors.push({
        file: relativePath,
        issues: [
          {
            code: 'parse_error',
            message: `Failed to parse YAML: ${error.message}`,
            path: [],
          },
        ],
      });
    }
  }

  // Validate manifest files
  for (const filePath of manifestFiles) {
    const relativePath = path.relative(process.cwd(), filePath);

    try {
      const fileContent = fs.readFileSync(filePath, 'utf8');
      const manifestData = yaml.parse(fileContent);

      const result = validateManifestFile(relativePath, manifestData);

      if (result.success) {
        console.log(`✅ ${relativePath}`);
      } else {
        errors.push({
          file: relativePath,
          issues: result.error.issues,
        });
      }
    } catch (error) {
      errors.push({
        file: relativePath,
        issues: [
          {
            code: 'parse_error',
            message: `Failed to parse YAML: ${error.message}`,
            path: [],
          },
        ],
      });
    }
  }

  // Report errors
  if (errors.length > 0) {
    console.log('\n❌ Validation failed for the following files:\n');

    for (const { file, issues } of errors) {
      console.log(`\n📄 ${file}`);
      for (const issue of issues) {
        const pathString = issue.path.length > 0 ? issue.path.join('.') : '(root)';
        console.log(`   Path: ${pathString}`);
        console.log(`   Error: ${issue.message}`);
        if (issue.code) {
          console.log(`   Code: ${issue.code}`);
        }
      }
    }

    console.log(`\n\n💥 ${errors.length} file(s) failed validation`);
    process.exit(1);
  }

  console.log(`\n✨ All ${totalFiles} file(s) passed validation!\n`);
  process.exit(0);
}

// Run with optional command-line argument for project root
const customProjectRoot = process.argv[2];
main(customProjectRoot).catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
