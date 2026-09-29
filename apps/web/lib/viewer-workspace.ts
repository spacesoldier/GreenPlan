import type { CadLayer, SceneLayer, SceneRoot, SceneSource } from "./contracts";

export const rootGroupLabels: Record<SceneRoot["workspace_kind"], string> = {
  project_solution: "Проектное решение",
  source_data: "Исходные данные",
  archive: "Архив",
  other: "Прочие материалы",
};

const rootGroupOrder: SceneRoot["workspace_kind"][] = [
  "project_solution", "source_data", "archive", "other",
];

export function groupSceneRoots(roots: SceneRoot[]): Array<{ kind: SceneRoot["workspace_kind"]; label: string; roots: SceneRoot[] }> {
  return rootGroupOrder.flatMap((kind) => {
    const values = roots.filter((root) => root.workspace_kind === kind);
    return values.length ? [{ kind, label: rootGroupLabels[kind], roots: values }] : [];
  });
}

function normalized(value: string): string {
  return value.toLocaleLowerCase().replaceAll("ё", "е").replace(/[^a-zа-я0-9]+/gi, " ").trim();
}

export function sceneLayerSource(layer: SceneLayer, sources: SceneSource[]): SceneSource | undefined {
  if (layer.source_asset_id) {
    const exact = sources.find((source) => source.asset_id === layer.source_asset_id);
    if (exact) return exact;
  }
  const prefix = layer.title.split("$0$")[0];
  return sources.find((source) => source.relation === "xref" && normalized(source.block_name || "") === normalized(prefix))
    ?? sources.find((source) => source.relation === "root");
}

export function matchCadLayer(layer: SceneLayer, candidates: CadLayer[]): CadLayer | undefined {
  const name = normalized(layer.source_layer_name || layer.title.split("$0$").at(-1) || layer.title);
  const exact = candidates.find((candidate) => candidate.source_asset_id === layer.source_asset_id && normalized(candidate.name) === name);
  if (exact) return exact;
  const byName = candidates.filter((candidate) => normalized(candidate.name) === name);
  return byName.length === 1 ? byName[0] : undefined;
}

export function rootScopedTileIdentity(modelId: string, rootId: string | null, visibleFingerprint = "all"): string {
  return `${modelId}@${rootId || "legacy"}@${visibleFingerprint}`;
}
