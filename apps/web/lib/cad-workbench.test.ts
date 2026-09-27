import { describe, expect, it } from "vitest";
import { buildDeliveryTree, groupLayerFamilies, normalizedLayerName } from "./cad-workbench";
import type { CadLayer, IntakeFile } from "./contracts";

describe("CAD workbench projections", () => {
  it("builds a stable physical folder tree", () => {
    const files = [
      { id: "2", relative_path: "Проект/XREF/base.dwg" },
      { id: "1", relative_path: "Проект/head.dwg" },
    ] as IntakeFile[];
    const tree = buildDeliveryTree(files);
    expect(tree[0].label).toBe("Проект");
    expect(tree[0].children.map((item) => item.label)).toEqual(["XREF", "head.dwg"]);
    expect(tree[0].children[0].children[0].file?.id).toBe("2");
  });

  it("groups only normalized names with the same entity signature", () => {
    const base = { entity_types: { LINE: 2 }, name: "Кабель  связи" } as unknown as CadLayer;
    const same = { ...base, id: "2", name: "кабель-связи" } as CadLayer;
    const different = { ...base, id: "3", entity_types: { MTEXT: 2 } } as CadLayer;
    expect(normalizedLayerName("  Ёлки---новые ")).toBe("елки новые");
    expect([...groupLayerFamilies([base, same, different]).values()].map((items) => items.length).sort()).toEqual([1, 2]);
  });
});
