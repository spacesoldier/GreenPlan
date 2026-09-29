import { describe, expect, it } from "vitest";
import { groupSceneRoots, matchCadLayer, rootScopedTileIdentity, sceneLayerSource } from "./viewer-workspace";
import type { CadLayer, SceneLayer, SceneRoot, SceneSource } from "./contracts";

const root = (id: string, kind: SceneRoot["workspace_kind"]): SceneRoot => ({
  id, path: `${kind}/${id}.dwg`, title: `${id}.dwg`, role: "reference_context", workspace_kind: kind, feature_count: 1,
});

it("groups roots in engineering workspace order", () => {
  const groups = groupSceneRoots([root("archive", "archive"), root("design", "project_solution"), root("source", "source_data")]);
  expect(groups.map((group) => group.kind)).toEqual(["project_solution", "source_data", "archive"]);
});

it("resolves xref source from embedded layer prefix", () => {
  const layer = { id: "one", title: "BASE$0$Теплосеть", source_layer_name: "Теплосеть" } as SceneLayer;
  const sources = [
    { path: "plan.dwg", title: "plan.dwg", relation: "root", provenance_status: "exact" },
    { path: "base.dwg", title: "base.dwg", relation: "xref", block_name: "BASE", provenance_status: "inferred" },
  ] as SceneSource[];
  expect(sceneLayerSource(layer, sources)?.path).toBe("base.dwg");
});

it("matches a unique original CAD layer and scopes tile identity by root", () => {
  const layer = { id: "one", title: "BASE$0$Теплосеть", source_layer_name: "Теплосеть" } as SceneLayer;
  const candidate = { id: "cad", suggestion_id: "suggestion", source_asset_id: "source", name: "теплосеть" } as CadLayer;
  expect(matchCadLayer(layer, [candidate])?.suggestion_id).toBe("suggestion");
  expect(rootScopedTileIdentity("model", "root-a")).not.toBe(rootScopedTileIdentity("model", "root-b"));
});
