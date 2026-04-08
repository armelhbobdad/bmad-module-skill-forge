'use strict';

/**
 * Deterministic Completeness Score Calculator
 *
 * Pure-function scoring script for the SKF test-skill workflow (step-05).
 * Implements the weight tables, skip conditions, and proportional redistribution
 * defined in scoring-rules.md.
 *
 * CLI: node compute-score.js '<JSON>'
 * Module: const { computeScore } = require('./compute-score');
 *
 * Input/output schemas documented in the plan and scoring-rules.md.
 */

// --- Weight Tables (from scoring-rules.md) ---

const CONTEXTUAL_WEIGHTS = {
  exportCoverage: 36,
  signatureAccuracy: 22,
  typeCoverage: 14,
  coherence: 18,
  externalValidation: 10,
};

const NAIVE_WEIGHTS = {
  exportCoverage: 45,
  signatureAccuracy: 25,
  typeCoverage: 20,
  coherence: 0,
  externalValidation: 10,
};

const CATEGORIES = ['exportCoverage', 'signatureAccuracy', 'typeCoverage', 'coherence', 'externalValidation'];

const DEFAULT_THRESHOLD = 80;

// --- Helpers ---

function round2(value) {
  return Math.round(value * 100) / 100;
}

function makeError(message) {
  return { error: message, code: 'INVALID_INPUT' };
}

// --- Validation ---

function validateInput(input) {
  if (!input || typeof input !== 'object') {
    return 'Input must be a JSON object';
  }

  if (!input.mode || !['contextual', 'naive'].includes(input.mode)) {
    return 'Missing or invalid required field: mode (must be "contextual" or "naive")';
  }

  const validTiers = ['Quick', 'Forge', 'Forge+', 'Deep'];
  if (!input.tier || !validTiers.includes(input.tier)) {
    return `Missing or invalid required field: tier (must be one of: ${validTiers.join(', ')})`;
  }

  if (!input.scores || typeof input.scores !== 'object') {
    return 'Missing required field: scores';
  }

  if (input.scores.exportCoverage === null || input.scores.exportCoverage === undefined) {
    return 'scores.exportCoverage is required and cannot be null';
  }

  if (
    input.threshold !== undefined &&
    input.threshold !== null &&
    (typeof input.threshold !== 'number' || input.threshold < 0 || input.threshold > 100)
  ) {
    return 'threshold must be a number between 0 and 100';
  }

  // Validate individual scores (0-100 or null)
  for (const cat of CATEGORIES) {
    const score = input.scores[cat];
    if (score !== null && score !== undefined) {
      if (typeof score !== 'number' || Number.isNaN(score)) {
        return `scores.${cat} must be a number or null, got: ${typeof score}`;
      }
      if (score < 0 || score > 100) {
        return `scores.${cat} must be between 0 and 100, got: ${score}`;
      }
    }
  }

  return null;
}

// --- Core Scoring Function ---

function computeScore(input) {
  // 1. Validate
  const validationError = validateInput(input);
  if (validationError) {
    return makeError(validationError);
  }

  const mode = input.mode;
  const tier = input.tier;
  const docsOnly = input.docsOnly === true;
  const state2 = input.state2 === true;
  const threshold = input.threshold !== undefined && input.threshold !== null ? input.threshold : DEFAULT_THRESHOLD;
  const scores = input.scores;

  // 2. Select base weight table
  const baseWeights = mode === 'naive' ? { ...NAIVE_WEIGHTS } : { ...CONTEXTUAL_WEIGHTS };

  // 3. Determine skip set
  const skipReasons = {};
  const skipSigType = tier === 'Quick' || docsOnly || state2;

  if (skipSigType) {
    const reasons = [];
    if (tier === 'Quick') reasons.push('Quick tier');
    if (docsOnly) reasons.push('docs-only mode');
    if (state2) reasons.push('State 2 (provenance-map)');
    const reason = reasons.join(' + ');
    skipReasons.signatureAccuracy = reason;
    skipReasons.typeCoverage = reason;
  }

  if (scores.externalValidation === null || scores.externalValidation === undefined) {
    skipReasons.externalValidation = 'No external validators available';
  }

  // Collect warnings (e.g., skipped category has a non-null score provided)
  const warnings = [];
  for (const cat of Object.keys(skipReasons)) {
    if (scores[cat] !== null && scores[cat] !== undefined) {
      warnings.push(`${cat} score provided (${scores[cat]}) but category is skipped — score ignored`);
    }
  }

  // Validate active categories have scores
  const skippedSet = new Set(Object.keys(skipReasons));
  for (const cat of CATEGORIES) {
    const isActive = !skippedSet.has(cat) && baseWeights[cat] > 0;
    const scoreMissing = scores[cat] === null || scores[cat] === undefined;
    if (isActive && scoreMissing) {
      return makeError(`Category ${cat} is active but score is null. Provide a numeric score or set the appropriate skip condition.`);
    }
  }

  // 4. Redistribute weights
  // Set skipped weights to 0
  const adjustedWeights = { ...baseWeights };
  for (const cat of Object.keys(skipReasons)) {
    adjustedWeights[cat] = 0;
  }

  // Compute sum of active weights (before redistribution)
  const sumActiveWeights = CATEGORIES.reduce((sum, cat) => sum + adjustedWeights[cat], 0);

  // Proportional redistribution to 100%
  const finalWeights = {};
  for (const cat of CATEGORIES) {
    if (adjustedWeights[cat] === 0) {
      finalWeights[cat] = 0;
    } else {
      finalWeights[cat] = round2((adjustedWeights[cat] / sumActiveWeights) * 100);
    }
  }

  // 5. Compute weighted scores
  const weightedScores = {};
  for (const cat of CATEGORIES) {
    if (finalWeights[cat] === 0) {
      weightedScores[cat] = 0;
    } else {
      weightedScores[cat] = round2((finalWeights[cat] / 100) * scores[cat]);
    }
  }

  // 6. Compute total
  const totalScore = round2(CATEGORIES.reduce((sum, cat) => sum + weightedScores[cat], 0));

  // Weight sum for verification
  const weightSum = round2(CATEGORIES.reduce((sum, cat) => sum + finalWeights[cat], 0));

  // 7. Determine result
  const result = totalScore >= threshold ? 'PASS' : 'FAIL';

  // 8. Build output
  const activeCategories = CATEGORIES.filter((cat) => finalWeights[cat] > 0);
  const skippedCategories = CATEGORIES.filter((cat) => skippedSet.has(cat) || baseWeights[cat] === 0);

  const output = {
    input: {
      mode,
      tier,
      docsOnly,
      state2,
      threshold,
      scores: { ...scores },
    },
    activeCategories,
    skippedCategories,
    skipReasons,
    weights: finalWeights,
    weightedScores,
    totalScore,
    threshold,
    result,
    weightSum,
  };

  if (warnings.length > 0) {
    output.warnings = warnings;
  }

  return output;
}

// --- CLI Entry Point ---

if (require.main === module) {
  const arg = process.argv[2];

  if (!arg) {
    console.error("Usage: node compute-score.js '<JSON>'");
    console.error(
      'Example: node compute-score.js \'{"mode":"contextual","tier":"Deep","scores":{"exportCoverage":92,"signatureAccuracy":85,"typeCoverage":100,"coherence":80,"externalValidation":78}}\'',
    );
    process.exit(1);
  }

  let input;
  try {
    input = JSON.parse(arg);
  } catch {
    console.log(JSON.stringify(makeError(`Invalid JSON: ${arg.slice(0, 100)}`), null, 2));
    process.exit(1);
  }

  const result = computeScore(input);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.error ? 1 : 0);
}

// --- Module Export ---

module.exports = { computeScore };
