export const CAD_CATEGORIES = [
  "vegetation.tree",
  "vegetation.shrub",
  "vegetation.grass",
  "vegetation.mixed",
  "structure.building",
  "structure.wall.external",
  "structure.support",
  "structure.retaining_wall",
  "transport.road.carriageway",
  "transport.road.edge",
  "transport.road.curb",
  "transport.pedestrian.path_edge",
  "transport.tram.track_edge",
  "transport.cycleway.edge",
  "transport.ditch.edge",
  "utility.water.pipeline",
  "utility.drainage.pipeline",
  "utility.sewer.pipeline",
  "utility.heat.pipeline",
  "utility.gas.pipeline",
  "utility.power.cable",
  "utility.power.overhead",
  "utility.telecom.cable",
  "territory.work_boundary",
  "territory.visibility_zone",
  "territory.metro_technical_zone",
  "territory.sanitary_protection_zone",
  "territory.utility_protection_zone",
  "terrain.slope_toe",
  "terrain.groundwater_level",
  "terrain",
  "not_applicable",
  "unknown",
] as const;

export type CadCategory = (typeof CAD_CATEGORIES)[number];

export type ModelDecision = {
  category: CadCategory;
  confidence: number;
  alternatives: string[];
  abstained: boolean;
  rationale: string;
  evidenceIds: string[];
};

export type CombinedDecision = ModelDecision & {
  disagreement: boolean;
  reviewRequired: boolean;
};

function stringArray(value: unknown, name: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${name} must be a string array`);
  }
  return value;
}

export function validateDecision(
  raw: unknown,
  allowed: readonly string[] = CAD_CATEGORIES,
): ModelDecision {
  if (!raw || typeof raw !== "object") throw new Error("model decision must be an object");
  const value = raw as Record<string, unknown>;
  if (typeof value.category !== "string" || !allowed.includes(value.category)) {
    throw new Error(`category is outside allowed taxonomy: ${String(value.category)}`);
  }
  if (typeof value.confidence !== "number" || !Number.isFinite(value.confidence)
      || value.confidence < 0 || value.confidence > 1) {
    throw new Error("confidence must be between 0 and 1");
  }
  if (typeof value.abstained !== "boolean") throw new Error("abstained must be boolean");
  if (typeof value.rationale !== "string") throw new Error("rationale must be string");
  return {
    category: value.category as CadCategory,
    confidence: value.confidence,
    alternatives: stringArray(value.alternatives ?? [], "alternatives").slice(0, 3),
    abstained: value.abstained,
    rationale: value.rationale,
    evidenceIds: stringArray(value.evidenceIds ?? [], "evidenceIds"),
  };
}

export function needsSecondOpinion(
  decision: Pick<ModelDecision, "category" | "confidence" | "abstained">,
  threshold: number,
  explicitlyRequested: boolean,
): boolean {
  return explicitlyRequested || decision.abstained || decision.category === "unknown"
    || decision.confidence < threshold;
}

export function combineDecisions(primary: ModelDecision, secondary?: ModelDecision): CombinedDecision {
  if (!secondary) {
    return {
      ...primary,
      disagreement: false,
      reviewRequired: primary.abstained || primary.category === "unknown",
    };
  }
  const disagreement = primary.category !== secondary.category;
  if (disagreement) {
    return {
      ...primary,
      confidence: Math.min(primary.confidence, secondary.confidence),
      abstained: true,
      rationale: `Model disagreement. Qwen: ${primary.rationale} Gemma: ${secondary.rationale}`,
      evidenceIds: [...new Set([...primary.evidenceIds, ...secondary.evidenceIds])],
      disagreement: true,
      reviewRequired: true,
    };
  }
  return {
    ...primary,
    confidence: Math.max(primary.confidence, secondary.confidence),
    abstained: primary.abstained && secondary.abstained,
    rationale: `${primary.rationale} Independent second opinion agrees: ${secondary.rationale}`,
    evidenceIds: [...new Set([...primary.evidenceIds, ...secondary.evidenceIds])],
    disagreement: false,
    reviewRequired: primary.abstained && secondary.abstained,
  };
}
