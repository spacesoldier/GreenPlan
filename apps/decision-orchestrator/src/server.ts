import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { classifyLayer, type ClassificationRequest } from "./classifier.js";
import { CAD_CATEGORIES } from "./policy.js";

const port = Number(process.env.PORT ?? "8000");
const host = process.env.HOST ?? "0.0.0.0";
const apiKey = process.env.ORCHESTRATOR_API_KEY ?? "greenplan_local_only";

function send(response: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}

async function readJson(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.from(chunk);
    size += buffer.length;
    if (size > 1_000_000) throw new Error("request body exceeds 1 MB");
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
}

function authorized(request: IncomingMessage): boolean {
  return !apiKey || request.headers.authorization === `Bearer ${apiKey}`;
}

async function runtimeHealth(): Promise<unknown> {
  const base = (process.env.LLM_RUNTIME_URL ?? "http://llm-runtime:8080/v1").replace(/\/v1\/?$/, "");
  const response = await fetch(`${base}/health`, { signal: AbortSignal.timeout(2_000) });
  if (!response.ok) throw new Error(`runtime health returned ${response.status}`);
  return response.json();
}

async function systemOne(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  const state = payload.state;
  const questions = payload.questions;
  if (!state || typeof state !== "object" || Array.isArray(state)) throw new Error("state must be an object");
  if (!questions || typeof questions !== "object" || Array.isArray(questions)) throw new Error("questions must be an object");
  const entries = Object.entries(questions as Record<string, unknown>);
  if (entries.length !== 1 || entries[0][0] !== "object_class") {
    throw new Error("transition endpoint currently supports only object_class");
  }
  const question = entries[0][1] as Record<string, unknown>;
  const criteria = question?.criteria;
  const allowed = criteria && typeof criteria === "object" && !Array.isArray(criteria)
    ? Object.keys(criteria).filter((key) => CAD_CATEGORIES.includes(key as never))
    : [...CAD_CATEGORIES];
  const result = await classifyLayer({
    featureSnapshot: state as Record<string, unknown>,
    allowedCategories: allowed,
  });
  const probabilities = Object.fromEntries([
    [result.category, result.confidence],
    ...result.alternatives.map((category, index) => [category, Math.max(0, result.confidence - (index + 1) * 0.15)]),
  ]);
  return { answers: { object_class: {
    choice: result.category,
    confidence: result.confidence,
    probabilities,
  } } };
}

const server = createServer(async (request, response) => {
  try {
    if (request.method === "GET" && request.url === "/health") {
      try {
        const runtime = await runtimeHealth();
        send(response, 200, { status: "ok", runtime });
      } catch (error) {
        send(response, 503, { status: "degraded", detail: String(error) });
      }
      return;
    }
    if (!authorized(request)) {
      send(response, 401, { error: "unauthorized" });
      return;
    }
    if (request.method === "POST" && request.url === "/v1/decisions/cad-layer") {
      const payload = await readJson(request);
      send(response, 200, await classifyLayer(payload as ClassificationRequest));
      return;
    }
    if (request.method === "POST" && request.url === "/v1/systemone") {
      send(response, 200, await systemOne(await readJson(request)));
      return;
    }
    send(response, 404, { error: "not_found" });
  } catch (error) {
    send(response, 400, { error: "invalid_or_failed_decision", detail: String(error) });
  }
});

server.listen(port, host, () => {
  console.log(`decision-orchestrator listening on ${host}:${port}`);
});

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
