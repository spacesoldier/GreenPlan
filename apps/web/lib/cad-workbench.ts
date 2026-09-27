import type { CadLayer, IntakeFile } from "./contracts";

export type DeliveryTreeNode = {
  id: string;
  label: string;
  kind: "folder" | "file";
  file?: IntakeFile;
  children: DeliveryTreeNode[];
};

export function buildDeliveryTree(files: IntakeFile[]): DeliveryTreeNode[] {
  const root: DeliveryTreeNode = { id: "root", label: "root", kind: "folder", children: [] };
  for (const file of [...files].sort((a, b) => a.relative_path.localeCompare(b.relative_path))) {
    const parts = file.relative_path.split("/").filter(Boolean);
    let parent = root;
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      const id = `${parent.id}/${part}`;
      let child = parent.children.find((item) => item.id === id);
      if (!child) {
        child = { id, label: part, kind: isFile ? "file" : "folder", file: isFile ? file : undefined, children: [] };
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
