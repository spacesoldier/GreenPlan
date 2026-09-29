import test from "node:test";
import assert from "node:assert/strict";

import { combineDecisions, needsSecondOpinion, validateDecision } from "./policy.js";

const allowed = ["utility.water.pipeline", "transport.road.carriageway", "unknown"] as const;

test("validator rejects output outside taxonomy", () => {
  assert.throws(() => validateDecision({
    category: "invented.category", confidence: 0.9, alternatives: [], abstained: false,
    rationale: "x", evidenceIds: [],
  }, allowed));
});

test("validator rejects invalid confidence", () => {
  assert.throws(() => validateDecision({
    category: "unknown", confidence: 2, alternatives: [], abstained: true,
    rationale: "x", evidenceIds: [],
  }, allowed));
});

test("high confidence known category skips second opinion", () => {
  assert.equal(needsSecondOpinion({ category: "transport.road.carriageway", confidence: 0.88, abstained: false }, 0.68, false), false);
});

test("unknown, low confidence and explicit request use second opinion", () => {
  assert.equal(needsSecondOpinion({ category: "unknown", confidence: 0.9, abstained: false }, 0.68, false), true);
  assert.equal(needsSecondOpinion({ category: "transport.road.carriageway", confidence: 0.4, abstained: false }, 0.68, false), true);
  assert.equal(needsSecondOpinion({ category: "transport.road.carriageway", confidence: 0.9, abstained: false }, 0.68, true), true);
});

test("model disagreement remains review-only", () => {
  const result = combineDecisions(
    { category: "transport.road.carriageway", confidence: 0.72, alternatives: [], abstained: false, rationale: "q", evidenceIds: [] },
    { category: "utility.water.pipeline", confidence: 0.81, alternatives: [], abstained: false, rationale: "g", evidenceIds: [] },
  );
  assert.equal(result.disagreement, true);
  assert.equal(result.abstained, true);
  assert.equal(result.reviewRequired, true);
});
