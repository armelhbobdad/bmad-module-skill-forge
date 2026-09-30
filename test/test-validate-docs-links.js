/**
 * Tests for tools/validate-docs-links.js
 *
 * This tool is a REQUIRED status check, so a bug in it either blocks a
 * legitimate PR or waves a broken link through. Every behaviour below was
 * verified by hand once during development and pinned by nothing, which is the
 * gap these tests close.
 *
 * The tool is driven against throwaway fixture trees via its `--docs-dir` /
 * `--build-dir` overrides, so nothing here depends on the repo's own docs.
 */

const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  resolveConfig,
  run,
  blankCode,
  assetUrls,
  buildInputsStatus,
  checkLlmsIndex,
  checkBuilt,
  headingToAnchor,
  extractAnchors,
} = require('../tools/validate-docs-links.js');

let passed = 0;
let failed = 0;
const tmpRoots = [];

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`[32m✓[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`[31m✗[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`[32m✓[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`[31m✗[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

/**
 * Build a fixture tree.
 *
 * @param {{docs?: Record<string,string>, build?: Record<string,string>, root?: Record<string,string>}} spec - Files by relative path
 * @returns {{cfg: object, root: string}} Config pointed at the fixture
 */
function fixture(spec, flags = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vdl-'));
  tmpRoots.push(root);

  for (const [group, base] of [
    ['root', ''],
    ['docs', 'docs'],
    ['build', path.join('build', 'site')],
  ]) {
    for (const [rel, body] of Object.entries(spec[group] ?? {})) {
      const full = path.join(root, base, rel);
      fs.mkdirSync(path.dirname(full), { recursive: true });
      fs.writeFileSync(full, body);
    }
  }

  return { root, cfg: resolveConfig(['--project-root', root, ...flags]) };
}

/** Run the tool silently and return its result. */
function runQuiet(cfg) {
  return run(cfg, () => {});
}

/** A minimal built page. */
function page(body, canonical = 'https://example.com/base/') {
  return `<html><head><link rel="canonical" href="${canonical}"/></head><body>${body}</body></html>`;
}

async function main() {
  // --- source pass ------------------------------------------------------

  await testAsync('a relative .md target that does not exist is reported', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '[x](./missing.md)' } });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /link target does not exist/);
  });

  await testAsync('a relative .md target that exists is clean', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '[x](./b.md)', 'b.md': 'hi' } });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  await testAsync('a root-absolute target resolves against the REPO root, not docs/', async () => {
    // /docs/b.md is correct on both surfaces; /b.md is dead on GitHub.
    const good = fixture({ docs: { 'a.md': '[x](/docs/b.md)', 'b.md': 'hi' } });
    assert.deepStrictEqual((await runQuiet(good.cfg)).issues, [], 'valid /docs/ target should pass');

    const bad = fixture({ docs: { 'a.md': '[x](/b.md)', 'b.md': 'hi' } });
    const r = await runQuiet(bad.cfg);
    assert.strictEqual(r.issues.length, 1);
    assert.match(r.issues[0].detail, /repository root, so it is dead on GitHub/);
  });

  await testAsync('external targets are ignored', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': '[a](https://x.test/y.md#nope) [d](mailto:a@b.c) [e](//cdn.test/x.png)' },
    });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  await testAsync('a non-.md target is checked for existence too', async () => {
    const good = fixture({ docs: { 'a.md': '[c](./img.png) [d](./sub/)', 'img.png': 'png', 'sub/x.md': 'x' } });
    assert.deepStrictEqual((await runQuiet(good.cfg)).issues, []);

    const bad = fixture({ docs: { 'a.md': '[c](./img.png)' } });
    const r = await runQuiet(bad.cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /link target does not exist: \.\/img\.png/);
  });

  // --- anchors ------------------------------------------------------------

  await testAsync('a same-file anchor that matches a heading is clean', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '# Title\n\nSee [b](#title) and [top](#top) and [c](#).\n' } });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  await testAsync('a broken same-file anchor in a published page is reported', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '# Title\n\nSee [b](#titel).\n' } });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.strictEqual(r.issues[0].file, path.join('docs', 'a.md'));
    assert.match(r.issues[0].detail, /anchor matches no heading in this file: #titel/);
  });

  await testAsync('a broken same-file anchor in docs/_internal/ is reported', async () => {
    const { cfg } = fixture({ docs: { '_internal/RELEASING.md': '## Rollback playbook\n\n[r](#rollback)\n' } });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.strictEqual(r.issues[0].file, path.join('docs', '_internal', 'RELEASING.md'));
  });

  await testAsync('a broken cross-file anchor from CONTRIBUTING.md is reported', async () => {
    const release = '## Rollback playbook\n';
    const good = fixture({
      root: { 'CONTRIBUTING.md': '[r](docs/_internal/RELEASING.md#rollback-playbook)\n' },
      docs: { '_internal/RELEASING.md': release },
    });
    assert.deepStrictEqual((await runQuiet(good.cfg)).issues, []);

    const bad = fixture(
      {
        root: { 'CONTRIBUTING.md': '[r](docs/_internal/RELEASING.md#rollback)\n' },
        docs: { '_internal/RELEASING.md': release },
      },
      ['--strict'],
    );
    const r = await runQuiet(bad.cfg);
    assert.strictEqual(r.ok, false);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.strictEqual(r.issues[0].file, 'CONTRIBUTING.md');
    assert.match(r.issues[0].detail, /anchor matches no heading in docs[/\\]_internal[/\\]RELEASING\.md/);
  });

  await testAsync('a broken same-file anchor in CONTRIBUTING.md is reported', async () => {
    const { cfg } = fixture({
      root: { 'CONTRIBUTING.md': '## The pull request check\n\n[a](#the-pull-request-check) [b](#the-pr-check)\n' },
      docs: { 'a.md': 'x' },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /#the-pr-check/);
  });

  await testAsync('a missing file target in CONTRIBUTING.md is reported, a folder or LICENSE is not', async () => {
    const { cfg } = fixture({
      root: {
        'CONTRIBUTING.md': '[l](LICENSE) [g](.github/) [w](.github/workflows/quality.yaml) [k](src/knowledge/overview.md)\n',
        LICENSE: 'MIT',
        '.github/workflows/other.yaml': 'on: push',
      },
      docs: { 'a.md': 'x' },
    });
    const r = await runQuiet(cfg);
    assert.deepStrictEqual(
      r.issues.map((i) => i.detail),
      ['link target does not exist: .github/workflows/quality.yaml', 'link target does not exist: src/knowledge/overview.md'],
    );
  });

  await testAsync('README.md and changes/README.md are read, resolving from their own folder', async () => {
    const { cfg } = fixture({
      root: {
        'README.md': '## Verifying a skill\n\n[v](#verifying-a-skill) [x](#nope)\n',
        'changes/README.md': '[c](../CONTRIBUTING.md#the-pull-request-check) [w](#which-type)\n\n## Which type\n',
        'CONTRIBUTING.md': '## The check\n',
      },
      docs: { 'a.md': 'x' },
    });
    const r = await runQuiet(cfg);
    assert.deepStrictEqual(
      r.issues.map((i) => `${i.file}: ${i.detail}`),
      [
        'README.md: anchor matches no heading in this file: #nope',
        `${path.join('changes', 'README.md')}: anchor matches no heading in CONTRIBUTING.md: ../CONTRIBUTING.md#the-pull-request-check`,
      ],
    );
  });

  await testAsync('a root-absolute .md target has its anchor checked', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': '[w](/docs/b.md#pipeline-mode) [x](/docs/b.md#pipeline)', 'b.md': '## Pipeline mode\n' },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /\/docs\/b\.md#pipeline$/);
  });

  await testAsync('a doubled hyphen and a repeated heading resolve', async () => {
    const { cfg } = fixture({
      docs: {
        'a.md': [
          '## Scenario D \u2014 Tag exists but npm publish failed',
          '## Internal \u2014 not covered by semver',
          '## Cutting v1.0.0 under `--tag latest`',
          '## Step',
          '## Step',
          '',
          '[a](#scenario-d--tag-exists-but-npm-publish-failed) [b](#internal--not-covered-by-semver)',
          '[c](#cutting-v100-under---tag-latest) [d](#step) [e](#step-1) [f](#step-2)',
        ].join('\n'),
      },
    });
    const r = await runQuiet(cfg);
    assert.deepStrictEqual(
      r.issues.map((i) => i.detail),
      ['anchor matches no heading in this file: #step-2'],
    );
  });

  await testAsync('an anchor that matches only a # comment in a fenced block is reported', async () => {
    const { cfg } = fixture({
      docs: {
        'a.md': '## Rollback\n\n```bash\n# Flip latest back\nnpm dist-tag add x latest\n```\n\n[f](#flip-latest-back) [r](#rollback)\n',
      },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /#flip-latest-back/);
  });

  await testAsync('an anchor shown inside inline code is not checked', async () => {
    const { cfg } = fixture({ docs: { 'a.md': 'Write `[x](#anything)` to link a heading.\n' } });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  await testAsync('a percent-encoded anchor is decoded before matching', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '## Café\n\n[c](#caf%C3%A9) [d](#café)\n' } });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  // --- heading ids --------------------------------------------------------

  test('headingToAnchor keeps each space as a hyphen and drops punctuation', () => {
    assert.strictEqual(headingToAnchor('Scenario A: Greenfield + BMM Integration'), 'scenario-a-greenfield--bmm-integration');
    assert.strictEqual(headingToAnchor("Who's this for?"), 'whos-this-for');
    assert.strictEqual(headingToAnchor('Tips & Tricks'), 'tips--tricks');
    assert.strictEqual(headingToAnchor('tier_override: auto'), 'tier_override-auto');
    assert.strictEqual(headingToAnchor('Élan 🚀 résumé'), 'élan--résumé');
  });

  test('repeated headings take -1, -2 and skip an id an earlier heading took', () => {
    // github-slugger: Foo -> foo, Foo -> foo-1, "Foo 1" -> foo-1 is taken -> foo-1-1.
    const ids = [...extractAnchors('# Foo\n# Foo\n# Foo 1\n# Foo\n')];
    assert.deepStrictEqual(ids, ['foo', 'foo-1', 'foo-1-1', 'foo-2']);
  });

  test('extractAnchors skips fences, front matter and non-headings', () => {
    const ids = extractAnchors(
      [
        '---',
        '# a yaml comment',
        'title: Page',
        '---',
        '# Real',
        '#hashtag is a paragraph',
        '    # indented four spaces is code',
        '~~~',
        '# tilde fenced',
        '~~~',
        '   ### Three spaces is still a heading ###',
        '#',
      ].join('\n'),
    );
    assert.deepStrictEqual([...ids], ['real', 'three-spaces-is-still-a-heading', '']);
  });

  test('extractAnchors reads heading text the way a renderer does', () => {
    const ids = extractAnchors(
      [
        '## Run `_private_` and `a  b`',
        '## _Emphasis_ and __strong__ but snake_case stays',
        '## See [the guide](./guide.md#x) and ![logo](logo.png)',
        '## <span>Tagged</span> R&amp;D &#169;',
        '## Closing hashes ##',
        '## C# stays',
        '## An \\_escaped\\_ underscore and ` spaced `',
        '## CRLF line\r',
      ].join('\n'),
    );
    assert.deepStrictEqual(
      [...ids],
      [
        'run-_private_-and-a--b',
        'emphasis-and-strong-but-snake_case-stays',
        'see-the-guide-and-',
        'tagged-rd-',
        'closing-hashes',
        'c-stays',
        'an-_escaped_-underscore-and-spaced',
        'crlf-line',
      ],
    );
  });

  // github-slugger is what GitHub and Starlight run; compare against it when
  // it is installed (Astro brings it in as a dev dependency). The name sits in
  // a variable because this file is shared with a repository that does not
  // install it, and a literal specifier fails that repository's import lint.
  const SLUGGER_PACKAGE = 'github-slugger';
  let slugger = null;
  try {
    slugger = await import(SLUGGER_PACKAGE);
  } catch {
    console.log('- skipped: github-slugger parity (github-slugger is not installed)');
  }
  if (slugger) {
    test('headingToAnchor matches github-slugger on every character', () => {
      // Ranges where both use the same Unicode tables: Latin through Arabic,
      // punctuation, symbols and arrows, CJK punctuation and kana, and emoji.
      const exact = [
        [0x00_00, 0x08_6f],
        [0x20_00, 0x2b_ff],
        [0x30_00, 0x30_ff],
        [0x1_f0_00, 0x1_fa_ff],
      ];
      for (let cp = 0; cp <= 0x10_ff_ff; cp += 1) {
        if (cp >= 0xd8_00 && cp <= 0xdf_ff) {
          continue;
        }
        const char = String.fromCodePoint(cp);
        const ours = headingToAnchor(char);
        const theirs = slugger.slug(char);
        if (ours === theirs) {
          continue;
        }
        // Outside those ranges only a letter assigned after Unicode 13 may
        // differ: github-slugger drops it, this Node's tables keep it.
        const inExact = exact.some(([lo, hi]) => cp >= lo && cp <= hi);
        assert.ok(
          !inExact && theirs === '',
          `U+${cp.toString(16)}: ours ${JSON.stringify(ours)}, github-slugger ${JSON.stringify(theirs)}`,
        );
      }
    });

    test('extractAnchors matches github-slugger on repeated and mixed headings', () => {
      const headings = [
        'Scenario D \u2014 Tag exists',
        'Foo',
        'Foo',
        'Foo 1',
        'Tips & Tricks',
        'Headless / Automation',
        '\u2014 clear session \u2014',
      ];
      const expected = new slugger.default();
      assert.deepStrictEqual(
        [...extractAnchors(headings.map((h) => `## ${h}`).join('\n'))],
        headings.map((h) => expected.slug(h)),
      );
    });
  }

  test('validate-doc-links.js slugs headings with this module, not its own copy', () => {
    // Not every repository carrying this tool has the other checker.
    const checker = path.join(__dirname, '..', 'tools', 'validate-doc-links.js');
    if (!fs.existsSync(checker)) {
      return;
    }
    const source = fs.readFileSync(checker, 'utf8');
    assert.match(source, /\{ extractAnchors \} = require\('\.\/validate-docs-links\.js'\)/);
    assert.doesNotMatch(source, /function (headingToAnchor|extractAnchors)\b/);
  });

  // --- fenced / inline code --------------------------------------------

  await testAsync('a link shown inside a fence is not treated as real', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '```markdown\n[x](./nope.md)\n```\n' } });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  await testAsync('a link inside inline code is not treated as real', async () => {
    const { cfg } = fixture({ docs: { 'a.md': 'see `[x](./nope.md)` for the form' } });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
  });

  await testAsync('a real link on a line after a closed fence is still checked', async () => {
    const { cfg } = fixture({ docs: { 'a.md': '```\n[a](./ok.md)\n```\n\n[b](./nope.md)\n' } });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1);
    assert.match(r.issues[0].detail, /nope\.md/);
  });

  test('an unterminated fence blanks to end of file, never reverts to prose', () => {
    const out = blankCode('```\n[x](./nope.md)\n');
    assert.ok(!out.includes('nope.md'), `leaked past an unterminated fence: ${JSON.stringify(out)}`);
  });

  test('blankCode preserves line count so offsets stay usable', () => {
    const input = 'a\n```\nb\n```\nc';
    assert.strictEqual(blankCode(input).split('\n').length, input.split('\n').length);
  });

  test('a tilde fence closes only on tildes', () => {
    const out = blankCode('~~~\n[x](./nope.md)\n```\n[y](./also.md)\n~~~\n');
    assert.ok(!out.includes('nope.md'), 'tilde fence should blank its body');
    assert.ok(!out.includes('also.md'), 'a backtick fence must not close a tilde fence');
  });

  // --- built pass -------------------------------------------------------

  await testAsync('an href that resolves to nothing is reported', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: { 'index.html': page('<a href="/base/gone/">g</a>') },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /href resolves to nothing/);
  });

  await testAsync('the page-relative route regression is caught', async () => {
    // The defect that shipped: from /sub/, "./other/" means /sub/other/.
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: {
        'index.html': page(''),
        'sub/index.html': page('<a href="./other/">o</a>'),
        'other/index.html': page(''),
      },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /sub[/\\]other/);
  });

  await testAsync('src and srcset are resolved, not just href', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: {
        'index.html': page('<img src="/base/no.png"><img srcset="/base/no2.png 1x, /base/no3.png 2x">'),
      },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 3, JSON.stringify(r.issues));
    assert.ok(r.issues.every((i) => /^(src|srcset) resolves to nothing/.test(i.detail)));
  });

  test('assetUrls splits srcset candidates and ignores descriptors', () => {
    const refs = assetUrls('<img srcset="/a.png 1x, /b.png 2x">');
    assert.deepStrictEqual(
      refs.map((r) => r.url),
      ['/a.png', '/b.png'],
    );
  });

  test('assetUrls does not mistake srcset= for src=', () => {
    const refs = assetUrls('<img srcset="/a.png 1x">');
    assert.ok(!refs.some((r) => r.attr === 'src'), 'srcset must not match the src pattern');
  });

  await testAsync('base is read from the build artifact, not the environment', async () => {
    // Canonical says /base/; hrefs carry it. An env-derived base would differ.
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: { 'index.html': page('<a href="/base/ok/">o</a>'), 'ok/index.html': page('') },
    });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, [], 'base inference should make this clean');
  });

  await testAsync('an absolute href missing the base is reported', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: { 'index.html': page('<a href="/ok/">o</a>'), 'ok/index.html': page('') },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1);
    assert.match(r.issues[0].detail, /missing the base path/);
  });

  await testAsync('a same-page #fragment must match an id on the page', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: {
        'index.html': page(
          '<h1 id="_top">T</h1><h2 id="ok">Ok</h2><a href="#_top">t</a><a href="#ok">o</a><a href="#top">T</a><a href="#">e</a><a href="#gone">g</a>',
        ),
      },
    });
    const r = await runQuiet(cfg);
    assert.deepStrictEqual(
      r.issues.map((i) => i.detail),
      ['href matches no id on this page: #gone'],
    );
  });

  await testAsync('a #fragment on another page must match an id on that page', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: {
        'index.html': page('<a href="/base/ok/#sec">s</a><a href="/base/ok/#nope">n</a><a href="./ok/#sec">r</a>'),
        'ok/index.html': page('<h2 id="sec">Sec</h2>'),
      },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1, JSON.stringify(r.issues));
    assert.match(r.issues[0].detail, /href matches no id on ok[/\\]index\.html: \/base\/ok\/#nope/);
  });

  test('an id attribute is read only as a whole attribute, not a suffix', () => {
    const { cfg } = fixture({ build: { 'index.html': page('<div data-id="x"></div><a href="#x">x</a>') } });
    const issues = [];
    checkBuilt(cfg, '/base/', (file, detail) => issues.push(detail));
    assert.deepStrictEqual(issues, ['href matches no id on this page: #x']);
  });

  await testAsync('an href escaping the site root is reported, not resolved', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': 'x' },
      build: { 'index.html': page('<a href="../../etc/passwd">p</a>') },
    });
    const r = await runQuiet(cfg);
    assert.strictEqual(r.issues.length, 1);
    assert.match(r.issues[0].detail, /escapes the site root/);
  });

  // --- flags and reporting ---------------------------------------------

  await testAsync('--require-build fails on a missing build, without --strict', async () => {
    const { cfg } = fixture({ docs: { 'a.md': 'x' } }, ['--require-build']);
    const r = await runQuiet(cfg);
    assert.strictEqual(r.missingRequiredBuild, true);
    assert.strictEqual(r.ok, false, 'must fail independently of --strict');
  });

  await testAsync('without --require-build a missing build is advisory, and says so', async () => {
    const { cfg } = fixture({ docs: { 'a.md': 'x' } });
    const lines = [];
    const r = await run(cfg, (m) => lines.push(m));
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.haveBuild, false);
    const out = lines.join('\n');
    assert.ok(/DID NOT RUN/.test(out), 'a skipped built pass must not read as a full pass');
    assert.ok(!/All documentation links valid/.test(out));
  });

  await testAsync('--strict decides the exit only for real issues', async () => {
    const broken = { docs: { 'a.md': '[x](./missing.md)' } };
    assert.strictEqual((await runQuiet(fixture(broken).cfg)).ok, true, 'advisory by default');
    assert.strictEqual((await runQuiet(fixture(broken, ['--strict']).cfg)).ok, false, 'strict fails');
  });

  await testAsync('a clean tree with a build reports an unqualified pass', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': '[x](./b.md)', 'b.md': 'hi' },
      build: { 'index.html': page('') },
    });
    const lines = [];
    const r = await run(cfg, (m) => lines.push(m));
    assert.strictEqual(r.ok, true);
    assert.ok(/All documentation links valid/.test(lines.join('\n')));
  });

  // --- build-inputs freshness -------------------------------------------------

  test('a matching manifest reads match, and never claims freshness', () => {
    const { root, cfg } = fixture({ docs: { 'a.md': '# A\n' } });
    const crypto = require('node:crypto');
    const sha = crypto
      .createHash('sha1')
      .update(fs.readFileSync(path.join(root, 'docs', 'a.md')))
      .digest('hex');
    fs.mkdirSync(path.join(root, 'build'), { recursive: true });
    fs.writeFileSync(path.join(root, 'build', '.build-inputs.json'), JSON.stringify({ inputs: { 'docs/a.md': sha } }));
    assert.deepStrictEqual(buildInputsStatus(cfg), { state: 'match', changed: [] });
  });

  test('a changed or added input reads stale and names the files', () => {
    const { root, cfg } = fixture({ docs: { 'a.md': '# A\n', 'b.md': '# B\n' } });
    const crypto = require('node:crypto');
    const sha = crypto
      .createHash('sha1')
      .update(fs.readFileSync(path.join(root, 'docs', 'a.md')))
      .digest('hex');
    fs.mkdirSync(path.join(root, 'build'), { recursive: true });
    // Manifest knows a.md (stale hash lies about nothing) but predates b.md.
    fs.writeFileSync(
      path.join(root, 'build', '.build-inputs.json'),
      JSON.stringify({ inputs: { 'docs/a.md': sha, 'docs/gone.md': 'deadbeef' } }),
    );
    const status = buildInputsStatus(cfg);
    assert.strictEqual(status.state, 'stale');
    assert.deepStrictEqual(status.changed, ['docs/b.md', 'docs/gone.md']);
  });

  test('a missing or corrupt manifest reads missing, never stale', () => {
    const { cfg } = fixture({ docs: { 'a.md': '# A\n' } });
    assert.strictEqual(buildInputsStatus(cfg).state, 'missing');
    fs.mkdirSync(path.join(cfg.projectRoot, 'build'), { recursive: true });
    fs.writeFileSync(path.join(cfg.projectRoot, 'build', '.build-inputs.json'), 'not json');
    assert.strictEqual(buildInputsStatus(cfg).state, 'missing');
  });

  await testAsync('run() prints the definite STALE block when inputs changed', async () => {
    const lines = [];
    const { root, cfg } = fixture({
      docs: { 'a.md': '# A\n' },
      build: { 'index.html': page('<p>hi</p>') },
    });
    fs.mkdirSync(path.join(root, 'build'), { recursive: true });
    fs.writeFileSync(path.join(root, 'build', '.build-inputs.json'), JSON.stringify({ inputs: { 'docs/a.md': 'deadbeef' } }));
    await run(cfg, (m) => lines.push(m));
    const text = lines.join('\n');
    assert.match(text, /STALE BUILD: 1 input\(s\) changed/);
    assert.match(text, /docs\/a\.md/);
    assert.doesNotMatch(text, /may be cached/, 'the hedge yields to the definite block');
  });

  await testAsync('run() keeps the hedged note on a matching manifest', async () => {
    const crypto = require('node:crypto');
    const lines = [];
    const { root, cfg } = fixture({
      docs: { 'a.md': '# A\n' },
      build: { 'index.html': page('<p>hi</p>') },
    });
    const sha = crypto
      .createHash('sha1')
      .update(fs.readFileSync(path.join(root, 'docs', 'a.md')))
      .digest('hex');
    fs.mkdirSync(path.join(root, 'build'), { recursive: true });
    fs.writeFileSync(path.join(root, 'build', '.build-inputs.json'), JSON.stringify({ inputs: { 'docs/a.md': sha } }));
    await run(cfg, (m) => lines.push(m));
    const text = lines.join('\n');
    assert.doesNotMatch(text, /STALE BUILD/);
    assert.match(text, /may be cached/, 'a match never claims freshness');
  });

  // --- llms.txt route coverage -----------------------------------------------
  // This link class is not HTML, so the built pass never sees it; a deleted
  // page's index entry survived every check exactly this way.

  test('a live llms.txt route passes and an external link is skipped', () => {
    const { cfg } = fixture({
      build: {
        'llms.txt': 'Documentation: https://x.io/base\n\n- [Ok](https://x.io/base/ok/)\n- [Ext](https://github.com/o/r)\n',
        'ok/index.html': page('<p>ok</p>'),
      },
    });
    const issues = [];
    const checked = checkLlmsIndex(cfg, (file, detail) => issues.push({ file, detail }));
    assert.strictEqual(checked, 1, 'one site link checked; the external one skipped');
    assert.deepStrictEqual(issues, []);
  });

  test('a dead llms.txt route is a reported issue', () => {
    const { cfg } = fixture({
      build: {
        'llms.txt': 'Documentation: https://x.io/base\n\n- [Gone](https://x.io/base/gone/)\n',
      },
    });
    const issues = [];
    checkLlmsIndex(cfg, (file, detail) => issues.push({ file, detail }));
    assert.strictEqual(issues.length, 1);
    assert.ok(issues[0].detail.includes('https://x.io/base/gone/'), issues[0].detail);
  });

  test('a file target like llms-full.txt resolves as a file, not a route', () => {
    const { cfg } = fixture({
      build: {
        'llms.txt': 'Documentation: https://x.io/base\n\n- [Full](https://x.io/base/llms-full.txt)\n',
        'llms-full.txt': 'bundle\n',
      },
    });
    const issues = [];
    checkLlmsIndex(cfg, (file, detail) => issues.push({ file, detail }));
    assert.deepStrictEqual(issues, []);
  });

  test('no llms.txt or no Documentation header checks nothing and reports nothing', () => {
    const bare = fixture({ build: { 'index.html': page('<p>hi</p>') } });
    assert.strictEqual(
      checkLlmsIndex(bare.cfg, () => {
        throw new Error('no');
      }),
      0,
    );
    const headerless = fixture({ build: { 'llms.txt': '- [X](https://x.io/base/x/)\n' } });
    assert.strictEqual(
      checkLlmsIndex(headerless.cfg, () => {
        throw new Error('no');
      }),
      0,
    );
  });

  await testAsync('a dead llms.txt route fails a strict run end to end', async () => {
    const { cfg } = fixture(
      {
        docs: { 'a.md': '# A\n' },
        build: {
          'index.html': page('<p>hi</p>'),
          'llms.txt': 'Documentation: https://x.io/base\n\n- [Gone](https://x.io/base/gone/)\n',
        },
      },
      ['--strict'],
    );
    const result = await runQuiet(cfg);
    assert.strictEqual(result.ok, false);
    assert.ok(result.issues.some((issue) => issue.file === 'build/site/llms.txt'));
  });

  await testAsync('a missing docs dir raises rather than exiting the process', async () => {
    const cfg = resolveConfig(['--project-root', path.join(os.tmpdir(), 'vdl-does-not-exist')]);
    await assert.rejects(() => runQuiet(cfg), /docs\/ not found/);
  });

  for (const root of tmpRoots) {
    fs.rmSync(root, { recursive: true, force: true });
  }

  console.log(`\n  Passed: [32m${passed}[0m`);
  console.log(`  Failed: [31m${failed}[0m`);

  if (failed > 0) {
    process.exit(1);
  }
  console.log('[32mAll validate-docs-links tests passed![0m');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
