/**
 * Deterministic Completeness Score Tests
 *
 * Validates compute-score.js against all conditional branches:
 * - Weight table selection (contextual vs naive)
 * - Tier-based category skipping (Quick, Forge, Deep)
 * - External validation availability
 * - Docs-only and State 2 modes
 * - Proportional weight redistribution
 * - Boundary conditions and error handling
 *
 * Usage: node test/test-compute-score.js
 */

const path = require('node:path');
const { computeScore } = require(path.join(__dirname, '..', 'src', 'skf-test-skill', 'scripts', 'compute-score.js'));

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
    console.log(`${colors.green}\u2713${colors.reset} ${testName}`);
    passed++;
  } else {
    console.log(`${colors.red}\u2717${colors.reset} ${testName}`);
    if (errorMessage) {
      console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    }
    failed++;
  }
}

function assertScore(result, expectedTotal, expectedResult, label) {
  assert(!result.error, `${label}: no error`, result.error || '');
  assert(result.totalScore === expectedTotal, `${label}: totalScore = ${expectedTotal}`, `got ${result.totalScore}`);
  assert(result.result === expectedResult, `${label}: result = ${expectedResult}`, `got ${result.result}`);
  assert(result.weightSum >= 99.99 && result.weightSum <= 100.01, `${label}: weightSum in [99.99, 100.01]`, `got ${result.weightSum}`);
}

function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('SKF Compute Score Tests');
  console.log(`========================================${colors.reset}\n`);

  // ============================================================
  // Suite A: All categories active (contextual + Deep + both validators)
  // ============================================================
  console.log(`${colors.yellow}Suite A: All categories active (contextual + Deep + both)${colors.reset}\n`);

  const suiteA = computeScore({
    mode: 'contextual',
    tier: 'Deep',
    scores: {
      exportCoverage: 92,
      signatureAccuracy: 85,
      typeCoverage: 100,
      coherence: 80,
      externalValidation: 78,
    },
  });

  // Weights: 36, 22, 14, 18, 10
  // Weighted: 92*0.36=33.12, 85*0.22=18.7, 100*0.14=14, 80*0.18=14.4, 78*0.10=7.8
  // Total: 33.12 + 18.7 + 14 + 14.4 + 7.8 = 88.02
  assertScore(suiteA, 88.02, 'PASS', 'Suite A');
  assert(suiteA.activeCategories.length === 5, 'Suite A: 5 active categories', `got ${suiteA.activeCategories.length}`);
  assert(suiteA.skippedCategories.length === 0, 'Suite A: 0 skipped categories', `got ${suiteA.skippedCategories.length}`);
  assert(suiteA.weights.exportCoverage === 36, 'Suite A: exportCoverage weight = 36', `got ${suiteA.weights.exportCoverage}`);
  assert(suiteA.weights.coherence === 18, 'Suite A: coherence weight = 18', `got ${suiteA.weights.coherence}`);

  // ============================================================
  // Suite B: Naive mode (no coherence)
  // ============================================================
  console.log(`\n${colors.yellow}Suite B: Naive mode (no coherence)${colors.reset}\n`);

  const suiteB = computeScore({
    mode: 'naive',
    tier: 'Forge',
    scores: {
      exportCoverage: 90,
      signatureAccuracy: 80,
      typeCoverage: 75,
      coherence: null,
      externalValidation: 85,
    },
  });

  // Naive weights: 45, 25, 20, 0, 10
  // Weighted: 90*0.45=40.5, 80*0.25=20, 75*0.20=15, 0, 85*0.10=8.5
  // Total: 40.5 + 20 + 15 + 0 + 8.5 = 84
  assertScore(suiteB, 84, 'PASS', 'Suite B');
  assert(suiteB.weights.coherence === 0, 'Suite B: coherence weight = 0', `got ${suiteB.weights.coherence}`);
  assert(suiteB.skippedCategories.includes('coherence'), 'Suite B: coherence in skippedCategories');

  // ============================================================
  // Suite C: Quick tier (no sig/type, contextual)
  // ============================================================
  console.log(`\n${colors.yellow}Suite C: Quick tier (contextual, no sig/type)${colors.reset}\n`);

  const suiteC = computeScore({
    mode: 'contextual',
    tier: 'Quick',
    scores: {
      exportCoverage: 85,
      signatureAccuracy: null,
      typeCoverage: null,
      coherence: 70,
      externalValidation: 90,
    },
  });

  // Base: 36, 22(skip), 14(skip), 18, 10. Active sum = 64
  // Redistributed: export=36/64*100=56.25, coherence=18/64*100=28.125->28.13, extVal=10/64*100=15.625->15.63
  // weightSum check: 56.25 + 28.13 + 15.63 = 100.01 (rounding)
  // Weighted: 85*0.5625=47.81, 70*0.2813=19.69, 90*0.1563=14.07
  // Total: 47.81 + 19.69 + 14.07 = 81.57 (with rounding)
  assert(!suiteC.error, 'Suite C: no error', suiteC.error || '');
  assert(suiteC.result === 'PASS', 'Suite C: result = PASS', `got ${suiteC.result}`);
  assert(suiteC.activeCategories.length === 3, 'Suite C: 3 active categories', `got ${suiteC.activeCategories.length}`);
  assert(suiteC.weights.signatureAccuracy === 0, 'Suite C: sig weight = 0', `got ${suiteC.weights.signatureAccuracy}`);
  assert(suiteC.weights.typeCoverage === 0, 'Suite C: type weight = 0', `got ${suiteC.weights.typeCoverage}`);
  assert(suiteC.weights.exportCoverage === 56.25, 'Suite C: export weight = 56.25', `got ${suiteC.weights.exportCoverage}`);
  assert(
    suiteC.skipReasons.signatureAccuracy === 'Quick tier',
    'Suite C: sig skip reason = Quick tier',
    `got ${suiteC.skipReasons.signatureAccuracy}`,
  );
  assert(suiteC.weightSum >= 99.99 && suiteC.weightSum <= 100.01, 'Suite C: weightSum in [99.99, 100.01]', `got ${suiteC.weightSum}`);

  // ============================================================
  // Suite D: No external validators (contextual + Deep)
  // ============================================================
  console.log(`\n${colors.yellow}Suite D: No external validators${colors.reset}\n`);

  const suiteD = computeScore({
    mode: 'contextual',
    tier: 'Deep',
    scores: {
      exportCoverage: 80,
      signatureAccuracy: 70,
      typeCoverage: 60,
      coherence: 75,
      externalValidation: null,
    },
  });

  // Base: 36, 22, 14, 18, 10(skip). Active sum = 90
  // Redistributed: export=36/90*100=40, sig=22/90*100=24.44, type=14/90*100=15.56, coherence=18/90*100=20
  // Weighted: 80*0.40=32, 70*0.2444=17.11, 60*0.1556=9.34, 75*0.20=15
  // Total: 32 + 17.11 + 9.34 + 15 = 73.45 (approx with rounding)
  assert(!suiteD.error, 'Suite D: no error', suiteD.error || '');
  assert(suiteD.result === 'FAIL', 'Suite D: result = FAIL', `got ${suiteD.result}`);
  assert(suiteD.weights.externalValidation === 0, 'Suite D: extVal weight = 0', `got ${suiteD.weights.externalValidation}`);
  assert(suiteD.weights.exportCoverage === 40, 'Suite D: export weight = 40', `got ${suiteD.weights.exportCoverage}`);
  assert(suiteD.weights.coherence === 20, 'Suite D: coherence weight = 20', `got ${suiteD.weights.coherence}`);
  assert(suiteD.weightSum >= 99.99 && suiteD.weightSum <= 100.01, 'Suite D: weightSum in [99.99, 100.01]', `got ${suiteD.weightSum}`);

  // ============================================================
  // Suite E: Triple skip — naive + Quick + no ext-val (export only)
  // ============================================================
  console.log(`\n${colors.yellow}Suite E: Triple skip (naive + Quick + no ext-val)${colors.reset}\n`);

  const suiteE = computeScore({
    mode: 'naive',
    tier: 'Quick',
    scores: {
      exportCoverage: 95,
      signatureAccuracy: null,
      typeCoverage: null,
      coherence: null,
      externalValidation: null,
    },
  });

  // Naive base: 45, 25, 20, 0, 10
  // Skip sig(25), type(20), extVal(10). Active: export(45). Sum=45
  // Redistributed: export=45/45*100=100
  // Weighted: 95*1.0=95
  // Total: 95
  assertScore(suiteE, 95, 'PASS', 'Suite E');
  assert(suiteE.activeCategories.length === 1, 'Suite E: 1 active category', `got ${suiteE.activeCategories.length}`);
  assert(suiteE.activeCategories[0] === 'exportCoverage', 'Suite E: only exportCoverage active');
  assert(suiteE.weights.exportCoverage === 100, 'Suite E: export weight = 100', `got ${suiteE.weights.exportCoverage}`);

  // ============================================================
  // Suite F: Docs-only mode
  // ============================================================
  console.log(`\n${colors.yellow}Suite F: Docs-only mode${colors.reset}\n`);

  const suiteF = computeScore({
    mode: 'contextual',
    tier: 'Quick',
    docsOnly: true,
    scores: {
      exportCoverage: 88,
      signatureAccuracy: null,
      typeCoverage: null,
      coherence: 65,
      externalValidation: 72,
    },
  });

  // Same skip as Quick (sig+type). docsOnly=true is redundant with Quick but valid.
  // Base: 36, 22(skip), 14(skip), 18, 10. Active sum=64
  // Redistributed: export=56.25, coherence=28.13, extVal=15.63
  // Weighted: 88*0.5625=49.5, 65*0.2813=18.28, 72*0.1563=11.25
  // Total: ~79.03
  assert(!suiteF.error, 'Suite F: no error', suiteF.error || '');
  assert(suiteF.result === 'FAIL', 'Suite F: result = FAIL (< 80)', `got ${suiteF.result}`);
  assert(suiteF.skipReasons.signatureAccuracy.includes('Quick tier'), 'Suite F: sig skip reason includes Quick tier');
  assert(suiteF.skipReasons.signatureAccuracy.includes('docs-only'), 'Suite F: sig skip reason includes docs-only');
  assert(suiteF.weightSum >= 99.99 && suiteF.weightSum <= 100.01, 'Suite F: weightSum in [99.99, 100.01]', `got ${suiteF.weightSum}`);

  // ============================================================
  // Suite G: State 2 mode (Deep tier but sig/type skipped)
  // ============================================================
  console.log(`\n${colors.yellow}Suite G: State 2 mode (Deep tier, sig/type skipped)${colors.reset}\n`);

  const suiteG = computeScore({
    mode: 'contextual',
    tier: 'Deep',
    state2: true,
    scores: {
      exportCoverage: 90,
      signatureAccuracy: null,
      typeCoverage: null,
      coherence: 85,
      externalValidation: 80,
    },
  });

  // state2=true skips sig+type even though tier is Deep
  // Base: 36, 22(skip), 14(skip), 18, 10. Active sum=64
  // Redistributed: export=56.25, coherence=28.13, extVal=15.63
  // Weighted: 90*0.5625=50.63, 85*0.2813=23.91, 80*0.1563=12.5
  // Total: ~87.04
  assert(!suiteG.error, 'Suite G: no error', suiteG.error || '');
  assert(suiteG.result === 'PASS', 'Suite G: result = PASS', `got ${suiteG.result}`);
  assert(
    suiteG.skipReasons.signatureAccuracy === 'State 2 (provenance-map)',
    'Suite G: sig skip reason = State 2',
    `got ${suiteG.skipReasons.signatureAccuracy}`,
  );
  assert(suiteG.weights.signatureAccuracy === 0, 'Suite G: sig weight = 0', `got ${suiteG.weights.signatureAccuracy}`);
  assert(suiteG.weightSum >= 99.99 && suiteG.weightSum <= 100.01, 'Suite G: weightSum in [99.99, 100.01]', `got ${suiteG.weightSum}`);

  // ============================================================
  // Suite H: Custom threshold = 90 (same scores as A, now FAIL)
  // ============================================================
  console.log(`\n${colors.yellow}Suite H: Custom threshold = 90${colors.reset}\n`);

  const suiteH = computeScore({
    mode: 'contextual',
    tier: 'Deep',
    threshold: 90,
    scores: {
      exportCoverage: 92,
      signatureAccuracy: 85,
      typeCoverage: 100,
      coherence: 80,
      externalValidation: 78,
    },
  });

  assertScore(suiteH, 88.02, 'FAIL', 'Suite H');
  assert(suiteH.threshold === 90, 'Suite H: threshold = 90', `got ${suiteH.threshold}`);

  // ============================================================
  // Suite I: Boundary — score exactly at threshold (PASS)
  // ============================================================
  console.log(`\n${colors.yellow}Suite I: Boundary — score equals threshold${colors.reset}\n`);

  const suiteI = computeScore({
    mode: 'naive',
    tier: 'Forge',
    threshold: 84,
    scores: {
      exportCoverage: 90,
      signatureAccuracy: 80,
      typeCoverage: 75,
      coherence: null,
      externalValidation: 85,
    },
  });

  // Same as Suite B: total = 84.00, threshold = 84
  assertScore(suiteI, 84, 'PASS', 'Suite I');

  // ============================================================
  // Suite J: Boundary — score below threshold (FAIL)
  // ============================================================
  console.log(`\n${colors.yellow}Suite J: Boundary — score below threshold${colors.reset}\n`);

  const suiteJ = computeScore({
    mode: 'naive',
    tier: 'Forge',
    threshold: 84.01,
    scores: {
      exportCoverage: 90,
      signatureAccuracy: 80,
      typeCoverage: 75,
      coherence: null,
      externalValidation: 85,
    },
  });

  // Total: 84.00, threshold: 84.01 → FAIL
  assertScore(suiteJ, 84, 'FAIL', 'Suite J');

  // ============================================================
  // Suite K: Forge+ tier (same scoring as Forge)
  // ============================================================
  console.log(`\n${colors.yellow}Suite K: Forge+ tier (same as Forge)${colors.reset}\n`);

  const suiteK = computeScore({
    mode: 'contextual',
    tier: 'Forge+',
    scores: {
      exportCoverage: 92,
      signatureAccuracy: 85,
      typeCoverage: 100,
      coherence: 80,
      externalValidation: 78,
    },
  });

  // Identical to Suite A — Forge+ uses same weights as Forge/Deep
  assertScore(suiteK, 88.02, 'PASS', 'Suite K');

  // ============================================================
  // Suite L: Error — missing mode
  // ============================================================
  console.log(`\n${colors.yellow}Suite L: Error cases${colors.reset}\n`);

  const suiteL1 = computeScore({});
  assert(!!suiteL1.error, 'Suite L1: missing mode returns error');
  assert(suiteL1.code === 'INVALID_INPUT', 'Suite L1: error code = INVALID_INPUT', `got ${suiteL1.code}`);

  const suiteL2 = computeScore({ mode: 'contextual', tier: 'Deep', scores: { exportCoverage: null } });
  assert(!!suiteL2.error, 'Suite L2: null exportCoverage returns error');

  const suiteL3 = computeScore({ mode: 'invalid', tier: 'Deep', scores: { exportCoverage: 90 } });
  assert(!!suiteL3.error, 'Suite L3: invalid mode returns error');

  const suiteL4 = computeScore({ mode: 'contextual', tier: 'Unknown', scores: { exportCoverage: 90 } });
  assert(!!suiteL4.error, 'Suite L4: invalid tier returns error');

  // ============================================================
  // Suite M: Error — active category with null score
  // ============================================================
  console.log(`\n${colors.yellow}Suite M: Active category with null score${colors.reset}\n`);

  const suiteM = computeScore({
    mode: 'contextual',
    tier: 'Deep',
    scores: {
      exportCoverage: 90,
      signatureAccuracy: 85,
      typeCoverage: 100,
      coherence: null, // null but contextual mode needs it
      externalValidation: 78,
    },
  });

  assert(!!suiteM.error, 'Suite M: null coherence in contextual mode returns error');
  assert(suiteM.error.includes('coherence'), 'Suite M: error mentions coherence', `got: ${suiteM.error}`);

  // ============================================================
  // Suite N: Warning — skipped category with provided score
  // ============================================================
  console.log(`\n${colors.yellow}Suite N: Skipped category with provided score (warning)${colors.reset}\n`);

  const suiteN = computeScore({
    mode: 'contextual',
    tier: 'Quick',
    scores: {
      exportCoverage: 85,
      signatureAccuracy: 90, // provided but will be skipped
      typeCoverage: null,
      coherence: 70,
      externalValidation: 80,
    },
  });

  assert(!suiteN.error, 'Suite N: no error (warning only)', suiteN.error || '');
  assert(suiteN.warnings && suiteN.warnings.length > 0, 'Suite N: has warnings');
  assert(
    suiteN.weights.signatureAccuracy === 0,
    'Suite N: sig weight = 0 despite score provided',
    `got ${suiteN.weights.signatureAccuracy}`,
  );

  // ============================================================
  // Suite O: Input echo verification
  // ============================================================
  console.log(`\n${colors.yellow}Suite O: Input echo verification${colors.reset}\n`);

  const inputO = {
    mode: 'naive',
    tier: 'Quick',
    docsOnly: true,
    state2: false,
    threshold: 75,
    scores: {
      exportCoverage: 80,
      signatureAccuracy: null,
      typeCoverage: null,
      coherence: null,
      externalValidation: null,
    },
  };
  const suiteO = computeScore(inputO);

  assert(!suiteO.error, 'Suite O: no error', suiteO.error || '');
  assert(suiteO.input.mode === 'naive', 'Suite O: input echo mode = naive');
  assert(suiteO.input.tier === 'Quick', 'Suite O: input echo tier = Quick');
  assert(suiteO.input.docsOnly === true, 'Suite O: input echo docsOnly = true');
  assert(suiteO.input.threshold === 75, 'Suite O: input echo threshold = 75');

  // ============================================================
  // Summary
  // ============================================================
  console.log(`\n${colors.cyan}========================================`);
  console.log(`Results: ${passed} passed, ${failed} failed`);
  console.log(`========================================${colors.reset}\n`);

  process.exit(failed > 0 ? 1 : 0);
}

runTests();
