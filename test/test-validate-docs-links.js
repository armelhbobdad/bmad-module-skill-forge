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

const { resolveConfig, run, blankCode, assetUrls, buildInputsStatus, checkLlmsIndex } = require('../tools/validate-docs-links.js');

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

  await testAsync('external, anchor-only, and non-.md targets are ignored', async () => {
    const { cfg } = fixture({
      docs: { 'a.md': '[a](https://x.test/y.md) [b](#frag) [c](./img.png) [d](mailto:a@b.c)' },
    });
    assert.deepStrictEqual((await runQuiet(cfg)).issues, []);
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
