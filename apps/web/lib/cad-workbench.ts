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
