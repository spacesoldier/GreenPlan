import { ai, ax } from "@ax-llm/ax";
import { CAD_CATEGORIES, combineDecisions, needsSecondOpinion, validateDecision, } from "./policy.js";
const signatureDefinition = `
  featureSnapshot:string "JSON with allowlisted CAD layer observations",
  retrievedEvidence:string "JSON list of reviewed similar examples",
  allowedCategories:string "comma-separated taxonomy allowlist" ->
  category:class "vegetation.tree, vegetation.shrub, vegetation.grass, vegetation.mixed, structure.building, structure.wall.external, structure.support, structure.retaining_wall, transport.road.carriageway, transport.road.edge, transport.road.curb, transport.pedestrian.path_edge, transport.tram.track_edge, transport.cycleway.edge, transport.ditch.edge, utility.water.pipeline, utility.drainage.pipeline, utility.sewer.pipeline, utility.heat.pipeline, utility.gas.pipeline, utility.power.cable, utility.power.overhead, utility.telecom.cable, territory.work_boundary, territory.visibility_zone, territory.metro_technical_zone, territory.sanitary_protection_zone, territory.utility_protection_zone, terrain.slope_toe, terrain.groundwater_level, terrain, not_applicable, unknown",
  confidence:number "0 to 1",
  alternatives:string[] "up to three category codes",
  abstained:boolean "true when evidence is insufficient or mixed",
  rationale:string "short evidence-based explanation in Russian",
  evidenceIds:string[] "only identifiers present in retrieved evidence"
`;
const signature = ax(signatureDefinition);
const runtimeUrl = process.env.LLM_RUNTIME_URL ?? "http://llm-runtime:8080/v1";
const runtimeKey = process.env.LLM_RUNTIME_API_KEY ?? "greenplan_local_only";
function client(profile) {
    return ai({
        name: "openai-compatible",
        apiURL: runtimeUrl,
        apiKey: runtimeKey,
        config: {
            model: profile,
            maxTokens: Number(process.env.LLM_MAX_OUTPUT_TOKENS ?? "256"),
            temperature: 0.1,
        },
    });
}
async function runProfile(profile, request, allowed) {
    const raw = await signature.forward(client(profile), {
        featureSnapshot: `${JSON.stringify(request.featureSnapshot)}\n/no_think`,
        retrievedEvidence: JSON.stringify(request.retrievedEvidence ?? []),
        allowedCategories: allowed.join(", "),
    });
    return validateDecision(raw, allowed);
}
export async function classifyLayer(request) {
    if (!request.featureSnapshot || typeof request.featureSnapshot !== "object" || Array.isArray(request.featureSnapshot)) {
        throw new Error("featureSnapshot must be an object");
    }
    const requested = request.allowedCategories ?? [...CAD_CATEGORIES];
    const allowed = [...new Set(requested.filter((item) => CAD_CATEGORIES.includes(item)))];
    if (allowed.length === 0)
        throw new Error("allowedCategories does not contain a known category");
    const primaryProfile = request.primaryProfile ?? "cad-qwen";
    const primary = await runProfile(primaryProfile, request, allowed);
    const runs = [{ profile: primaryProfile, decision: primary }];
    let secondary;
    const threshold = Number(process.env.SECOND_OPINION_THRESHOLD ?? "0.68");
    if (primaryProfile === "cad-qwen" && needsSecondOpinion(primary, threshold, request.secondOpinion ?? false)) {
        secondary = await runProfile("cad-gemma", request, allowed);
        runs.push({ profile: "cad-gemma", decision: secondary });
    }
    return {
        ...combineDecisions(primary, secondary),
        providerRuns: runs,
        signatureVersion: "cad-layer-v1",
    };
}
