# BMad Module Template

A template for creating BMad Method modules that can be published to npm and installed via the BMad installer.

## Quick Start

After creating a new repo from this template:

```bash
npm install
```

## Setup Checklist

### 1. Update package.json

Replace the placeholder values:

- `name`: Your package name (e.g., `@bmad-method/your-module`)
- `description`: What your module does
- `author`: Your name
- `repository.url`: Your git repository URL
- `keywords`: Add relevant search terms

### 2. Update this README.md

Remove these template instructions and add:
- What your module does
- How to use it
- Any specific configuration needed

### 3. Add your module content

All module content goes under `src/`:

```
src/
├── module.yaml       # Module metadata and install questions
├── agents/           # BMad agents
├── workflows/        # Agent workflows
└── tools/            # Small reusable tools
```

## Module Conventions

- **module.yaml**: Defines install questions and defaults
- **agents/**: All BMad agents go here
- **workflows/**: Agent workflows or direct-call workflows
- **tools/**: Small, single-purpose prompt files
- Use relative paths in all workflows/agents for portability

## Publishing to NPM

### First-time setup

1. Create an npm automation token at <https://www.npmjs.com/settings>/tokens
2. Add it as a GitHub secret named `NPM_TOKEN` in your repo settings:
   ```bash
   gh secret set NPM_TOKEN --repo YOUR-ORG/YOUR-REPO
   ```

### Release a new version

The module includes release scripts that handle versioning and publishing:

```bash
# Patch release (0.1.0 -> 0.1.1)
npm run release

# Minor release (0.1.0 -> 0.2.0)
npm run release:minor

# Major release (0.1.0 -> 1.0.0)
npm run release:major

# Prerelease (0.1.0 -> 0.1.1-0)
npm run release:prerelease
```

These scripts:
1. Update the version in package.json
2. Create a git tag
3. Push the tag to GitHub
4. Trigger the publish workflow which publishes to npm

### Manual tag release

You can also create tags manually:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Workflows

The module includes GitHub Actions workflows:

- **publish.yaml**: Automatically publishes to npm when a version tag is pushed
- **quality.yaml**: Runs linting and formatting checks
- **docs.yaml**: Builds documentation
- **discord.yaml**: Posts updates to Discord (configure if needed)

## Development

```bash
# Run linting
npm run lint

# Fix formatting
npm run format:fix

# Run tests
npm test
```

## Module Installation (for users)

Once published, users can install your module via the BMad Method installer or npm:

```bash
# Via BMad installer
npx bmad-method install

# Via npm
npm install your-module-name
```

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**Your Module Name** — Part of the [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD) ecosystem.

[![Contributors](https://contrib.rocks/image?repo=bmad-code-org/YOUR-REPO-NAME)](https://github.com/bmad-code-org/YOUR-REPO-NAME/graphs/contributors)

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for contributor information.
