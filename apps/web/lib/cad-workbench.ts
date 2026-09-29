import type { CadLayer, CadXrefDependency, IntakeFile } from "./contracts";

export type DeliveryTreeNode = {
  id: string;
  relativePath: string;
  label: string;
  kind: "folder" | "file";
  file?: IntakeFile;
  children: DeliveryTreeNode[];
};

export type CadDocumentTreeNode = {
  assetId: string;
  path: string;
  via: CadXrefDependency | null;
  children: CadDocumentTreeNode[];
  unresolved: CadXrefDependency[];
  cycle: boolean;
};

export type CadWorkspaceKind = "project_solution" | "source_data" | "archive" | "survey" | "other";

export type CadWorkspaceRoot = {
  kind: CadWorkspaceKind;
  label: string;
  nodes: CadDocumentTreeNode[];
};

export type HostPathParts = { leading: string[]; folder: string; file: string };

export function projectRelativePath(path: string): string {
  const parts = path.replaceAll("\\", "/").split("/").filter(Boolean);
  return (parts.length > 1 ? parts.slice(1) : parts).join("/");
}

export const cadCategoryLabels: Record<string, string> = {
  "vegetation.tree": "Дерево", "vegetation.shrub": "Кустарник",
  "vegetation.grass": "Газон и травянистая растительность", "vegetation.mixed": "Смешанные зелёные насаждения",
  "structure.building": "Здание", "structure.wall.external": "Наружная стена",
  "structure.support": "Опора или мачта", "structure.retaining_wall": "Подпорная стенка",
  "transport.road.carriageway": "Проезжая часть", "transport.road.edge": "Край проезжей части",
  "transport.road.curb": "Бортовой камень", "transport.pedestrian.path_edge": "Край тротуара или дорожки",
  "transport.tram.track_edge": "Край трамвайного полотна", "transport.cycleway.edge": "Край велодорожки",
  "transport.ditch.edge": "Бровка канавы",
  "utility.unknown": "Инженерные сети · тип не уточнён",
  "utility.water.pipeline": "Водопровод", "utility.drainage.pipeline": "Дренаж или водосток",
  "utility.sewer.pipeline": "Канализация", "utility.heat.pipeline": "Тепловая сеть",
  "utility.gas.pipeline": "Газопровод", "utility.power.cable": "Силовой кабель",
  "utility.power.overhead": "Воздушная линия", "utility.telecom.cable": "Кабель связи",
  "territory.work_boundary": "Граница работ", "territory.visibility_zone": "Зона видимости",
  "territory.metro_technical_zone": "Техническая зона метро",
  "territory.sanitary_protection_zone": "Санитарно-защитная зона",
  "territory.utility_protection_zone": "Охранная зона сети",
  "terrain.slope_toe": "Подошва откоса", "terrain.groundwater_level": "Уровень грунтовых вод",
  terrain: "Рельеф", not_applicable: "Служебное / неприменимо", unknown: "Не определено",
  "unknown.constraint": "Неопознанное ограничение",
};

function categoryOptions(...codes: string[]): [string, string][] {
  return codes.map((code) => [code, cadCategoryLabels[code]]);
}

export const cadCategoryGroups = [
  { label: "Быстрый выбор", options: categoryOptions("unknown", "not_applicable", "utility.unknown") },
  { label: "Растительность", options: categoryOptions("vegetation.tree", "vegetation.shrub", "vegetation.grass", "vegetation.mixed") },
  { label: "Здания и сооружения", options: categoryOptions("structure.building", "structure.wall.external", "structure.support", "structure.retaining_wall") },
  { label: "Улицы и дорожки", options: categoryOptions("transport.road.carriageway", "transport.road.edge", "transport.road.curb", "transport.pedestrian.path_edge", "transport.tram.track_edge", "transport.cycleway.edge", "transport.ditch.edge") },
  { label: "Инженерные сети — точный тип", options: categoryOptions("utility.water.pipeline", "utility.drainage.pipeline", "utility.sewer.pipeline", "utility.heat.pipeline", "utility.gas.pipeline", "utility.power.cable", "utility.power.overhead", "utility.telecom.cable") },
  { label: "Границы и зоны", options: categoryOptions("territory.work_boundary", "territory.visibility_zone", "territory.metro_technical_zone", "territory.sanitary_protection_zone", "territory.utility_protection_zone") },
  { label: "Рельеф", options: categoryOptions("terrain", "terrain.slope_toe", "terrain.groundwater_level") },
];

export const cadCategoryOptions = cadCategoryGroups.flatMap((group) => group.options);

export function cadCategoryLabel(code: string): string {
  return cadCategoryLabels[code] || code;
}

export function hostPathParts(path: string): HostPathParts {
  const parts = path.replaceAll("\\", "/").split("/").filter(Boolean).slice(1);
  const file = parts.pop() || "";
  const folder = parts.pop() || "";
  return { leading: parts, folder, file };
}

export type FindingSelectionItem = { id: string; source_asset_id: string | null; status: string };

export function effectiveFindingSelection(
  items: FindingSelectionItem[],
  selectedId: string,
): string {
  const active = items.filter((item) => ["open", "rejected"].includes(item.status));
  return active.some((item) => item.id === selectedId) ? selectedId : active[0]?.id || "";
}

export function nextFindingSelection(
  before: FindingSelectionItem[],
  after: FindingSelectionItem[],
  removedId: string,
): string {
  const active = (items: FindingSelectionItem[]) => items.filter((item) => ["open", "rejected"].includes(item.status));
  const previous = active(before);
  const remaining = active(after);
  const current = previous.find((item) => item.id === removedId);
  if (!current) return remaining[0]?.id || "";
  const sourceKey = (item: FindingSelectionItem) => item.source_asset_id || "project";
  const currentSource = sourceKey(current);
  const sameSource = remaining.find((item) => sourceKey(item) === currentSource);
  if (sameSource) return sameSource.id;
  const sourceOrder = [...new Set(previous.map(sourceKey))];
  const currentSourceIndex = sourceOrder.indexOf(currentSource);
  for (const source of sourceOrder.slice(currentSourceIndex + 1)) {
    const next = remaining.find((item) => sourceKey(item) === source);
    if (next) return next.id;
  }
  const knownSources = new Set(sourceOrder);
  return remaining.find((item) => !knownSources.has(sourceKey(item)))?.id || "";
}

export type XrefCandidateOption = {
  path: string;
  file: IntakeFile | undefined;
  kind: CadWorkspaceKind;
  compatible: boolean;
  recommended: boolean;
  recommendationReason: string | null;
};

const workspaceLabels: Record<CadWorkspaceKind, string> = {
  project_solution: "Проектное решение",
  source_data: "Исходные данные",
  archive: "Архивы",
  survey: "Обследования и ведомости",
  other: "Прочие CAD-материалы",
};

export function cadWorkspaceKind(path: string): CadWorkspaceKind {
  const parts = path.replaceAll("\\", "/").split("/").slice(0, -1).map((part) => part.toLocaleLowerCase().replaceAll("ё", "е"));
  if (parts.some((part) => /архив|archive/.test(part))) return "archive";
  if (parts.some((part) => /проектн|решени|project/.test(part))) return "project_solution";
  if (parts.some((part) => /исходн|source/.test(part))) return "source_data";
  if (parts.some((part) => /обслед|ведомост|инвентар/.test(part))) return "survey";
  return "other";
}

export function xrefCandidateOptions(
  xref: CadXrefDependency,
  files: IntakeFile[],
): XrefCandidateOption[] {
  const sourceKind = cadWorkspaceKind(xref.source_relative_path);
  const options: XrefCandidateOption[] = xref.matches.map((path) => {
    const kind = cadWorkspaceKind(path);
    return {
      path,
      file: files.find((item) => item.relative_path === path),
      kind,
      compatible: sourceKind !== "archive" || kind === "archive",
      recommended: false,
      recommendationReason: null,
    };
  });
  const compatible = options.filter((item) => item.compatible && item.file);
  const sameKind = compatible.filter((item) => item.kind === sourceKind);
  const preferred = sameKind.length ? sameKind : compatible;
  if (preferred.length === 1) {
    preferred[0].recommended = true;
    preferred[0].recommendationReason = sameKind.length ? "та же смысловая ветка" : "единственный допустимый кандидат";
    return options;
  }
  if (preferred.length > 1 && preferred.every((item) => item.file?.size_bytes === preferred[0].file?.size_bytes)) {
    const dated = preferred.filter((item) => item.file?.source_modified_at);
    if (dated.length === preferred.length) {
      const ordered = [...dated].sort((left, right) => Date.parse(right.file!.source_modified_at!) - Date.parse(left.file!.source_modified_at!));
      if (Date.parse(ordered[0].file!.source_modified_at!) > Date.parse(ordered[1].file!.source_modified_at!)) {
        ordered[0].recommended = true;
        ordered[0].recommendationReason = "одинаковый размер, наиболее свежая дата файла";
      }
    }
  }
  return options;
}

export function buildDeliveryTree(files: IntakeFile[]): DeliveryTreeNode[] {
  const root: DeliveryTreeNode = { id: "root", relativePath: "", label: "root", kind: "folder", children: [] };
  for (const file of [...files].sort((a, b) => a.relative_path.localeCompare(b.relative_path))) {
    const parts = file.relative_path.split("/").filter(Boolean);
    let parent = root;
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      const id = `${parent.id}/${part}`;
      let child = parent.children.find((item) => item.id === id);
      if (!child) {
        child = { id, relativePath: parts.slice(0, index + 1).join("/"), label: part, kind: isFile ? "file" : "folder", file: isFile ? file : undefined, children: [] };
        parent.children.push(child);
      }
      parent = child;
    });
  }
  const sortNodes = (nodes: DeliveryTreeNode[]) => {
    nodes.sort((a, b) => a.kind === b.kind ? a.label.localeCompare(b.label) : a.kind === "folder" ? -1 : 1);
    nodes.forEach((node) => sortNodes(node.children));
  };
  sortNodes(root.children);
  return root.children;
}

export function normalizedLayerName(name: string): string {
  return name.toLocaleLowerCase().replaceAll("ё", "е").replace(/[^a-zа-я0-9]+/gi, " ").trim();
}

export function layerFamilyKey(layer: CadLayer): string {
  const signature = Object.keys(layer.entity_types).sort().join(",");
  return `${normalizedLayerName(layer.name)}|${signature}`;
}

export function groupLayerFamilies(layers: CadLayer[]): Map<string, CadLayer[]> {
  return layers.reduce((groups, layer) => {
    const key = layerFamilyKey(layer);
    const values = groups.get(key) || [];
    values.push(layer); groups.set(key, values);
    return groups;
  }, new Map<string, CadLayer[]>());
}


export function reviewableLayerSuggestionIds(layers: CadLayer[]): string[] {
  return layers
    .filter((layer) => layer.review_status !== "superseded")
    .map((layer) => layer.suggestion_id);
}

export function areAllCadLayersClassified(layers: Pick<CadLayer, "mapping_status">[]): boolean {
  return layers.length > 0 && layers.every((layer) => layer.mapping_status === "confirmed");
}

export function toggleScopedSelection(currentIds: string[], scopeIds: string[], selected: boolean): string[] {
  const scope = new Set(scopeIds);
  if (selected) return Array.from(new Set([...currentIds, ...scopeIds]));
  return currentIds.filter((id) => !scope.has(id));
}

export function newlyAssistantClassifiedSuggestionIds(previous: CadLayer[], next: CadLayer[]): string[] {
  const previousByLayer = new Map(previous.map((layer) => [layer.id, layer]));
  return next.flatMap((layer) => {
    const before = previousByLayer.get(layer.id);
    const becameConfirmed = before && before.mapping_status !== "confirmed" && layer.mapping_status === "confirmed";
    return becameConfirmed && layer.axis_results.assistant_assigned ? [before.suggestion_id] : [];
  });
}

export type LayerReviewMode = "all" | "unknown" | "reviewed";

export function layerMatchesReviewMode(layer: CadLayer, mode: LayerReviewMode): boolean {
  if (mode === "unknown") return layer.mapping_status !== "confirmed";
  if (mode === "reviewed") return layer.mapping_status === "confirmed";
  return true;
}
export function clampTrayHeight(value: number, viewportHeight: number): number {
  return Math.round(Math.min(Math.max(value, 180), Math.max(180, viewportHeight * 0.75)));
}

export function clampDockSplit(value: number, viewportWidth: number): number {
  return Math.round(Math.min(Math.max(value, 280), Math.max(280, viewportWidth - 360)));
}

export function clampTreeWidth(value: number, viewportWidth: number): number {
  return Math.round(Math.min(Math.max(value, 300), Math.max(300, viewportWidth * 0.46)));
}

export function buildCadDependencyForest(
  documents: Array<[string, string]>,
  dependencies: CadXrefDependency[],
): CadDocumentTreeNode[] {
  const paths = new Map(documents);
  const outgoing = new Map<string, CadXrefDependency[]>();
  const incoming = new Set<string>();
  for (const dependency of dependencies) {
    const values = outgoing.get(dependency.source_asset_id) || [];
    values.push(dependency);
    outgoing.set(dependency.source_asset_id, values);
    if (dependency.referenced_asset_id && paths.has(dependency.referenced_asset_id)) incoming.add(dependency.referenced_asset_id);
  }
  const sortEdges = (edges: CadXrefDependency[]) => [...edges].sort((left, right) => left.reference_name.localeCompare(right.reference_name));
  const visit = (assetId: string, via: CadXrefDependency | null, ancestors: Set<string>): CadDocumentTreeNode => {
    const cycle = ancestors.has(assetId);
    const path = paths.get(assetId) || via?.target_relative_path || assetId;
    if (cycle) return { assetId, path, via, children: [], unresolved: [], cycle: true };
    const nextAncestors = new Set(ancestors).add(assetId);
    const edges = sortEdges(outgoing.get(assetId) || []);
    return {
      assetId, path, via,
      children: edges.filter((edge) => edge.referenced_asset_id && paths.has(edge.referenced_asset_id))
        .map((edge) => visit(edge.referenced_asset_id!, edge, nextAncestors)),
      unresolved: edges.filter((edge) => !edge.referenced_asset_id || !paths.has(edge.referenced_asset_id)),
      cycle: false,
    };
  };
  const forest = documents.filter(([assetId]) => !incoming.has(assetId))
    .map(([assetId]) => visit(assetId, null, new Set()));
  const represented = new Set<string>();
  const collect = (node: CadDocumentTreeNode) => { represented.add(node.assetId); node.children.forEach(collect); };
  forest.forEach(collect);
  for (const [assetId] of documents) if (!represented.has(assetId)) forest.push(visit(assetId, null, new Set()));
  return forest;
}

export function buildCadWorkspaceRoots(
  documents: Array<[string, string]>,
  dependencies: CadXrefDependency[],
): CadWorkspaceRoot[] {
  const groups = new Map<CadWorkspaceKind, CadDocumentTreeNode[]>();
  for (const node of buildCadDependencyForest(documents, dependencies)) {
    const kind = cadWorkspaceKind(node.path);
    const values = groups.get(kind) || [];
    values.push(node);
    groups.set(kind, values);
  }
  const order: CadWorkspaceKind[] = ["project_solution", "source_data", "survey", "archive", "other"];
  return order.filter((kind) => groups.has(kind)).map((kind) => ({
    kind, label: workspaceLabels[kind],
    nodes: (groups.get(kind) || []).sort((left, right) => left.path.localeCompare(right.path)),
  }));
}

export function wizardStepStates(input: {
  fileCount: number;
  cadCount: number;
  cadAnalyzed: boolean;
  openFindings: number;
  reviewAccepted: boolean;
  published: boolean;
}): Array<"complete" | "current" | "upcoming"> {
  const materialDone = input.fileCount > 0;
  const cadDone = input.cadCount > 0 && input.cadAnalyzed;
  const reviewDone = cadDone && input.reviewAccepted;
  if (input.published) return ["complete", "complete", "complete", "complete"];
  return [
    materialDone ? "complete" : "current",
    cadDone ? "complete" : materialDone ? "current" : "upcoming",
    reviewDone ? "complete" : cadDone ? "current" : "upcoming",
    reviewDone ? "current" : "upcoming",
  ];
}
