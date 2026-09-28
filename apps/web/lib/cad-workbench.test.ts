import { describe, expect, it } from "vitest";
import { buildCadDependencyForest, buildCadWorkspaceRoots, buildDeliveryTree, cadWorkspaceKind, clampDockSplit, clampTrayHeight, clampTreeWidth, groupLayerFamilies, normalizedLayerName, wizardStepStates, xrefCandidateOptions } from "./cad-workbench";
import type { CadLayer, CadXrefDependency, IntakeFile } from "./contracts";

describe("CAD workbench projections", () => {
  it("builds a stable physical folder tree", () => {
    const files = [
      { id: "2", relative_path: "Проект/XREF/base.dwg" },
      { id: "1", relative_path: "Проект/head.dwg" },
    ] as IntakeFile[];
    const tree = buildDeliveryTree(files);
    expect(tree[0].label).toBe("Проект");
    expect(tree[0].relativePath).toBe("Проект");
    expect(tree[0].children.map((item) => item.label)).toEqual(["XREF", "head.dwg"]);
    expect(tree[0].children[0].children[0].file?.id).toBe("2");
    expect(tree[0].children[0].relativePath).toBe("Проект/XREF");
  });

  it("groups only normalized names with the same entity signature", () => {
    const base = { entity_types: { LINE: 2 }, name: "Кабель  связи" } as unknown as CadLayer;
    const same = { ...base, id: "2", name: "кабель-связи" } as CadLayer;
    const different = { ...base, id: "3", entity_types: { MTEXT: 2 } } as CadLayer;
    expect(normalizedLayerName("  Ёлки---новые ")).toBe("елки новые");
    expect([...groupLayerFamilies([base, same, different]).values()].map((items) => items.length).sort()).toEqual([1, 2]);
  });

  it("clamps the resizable bottom tray", () => {
    expect(clampTrayHeight(90, 900)).toBe(180);
    expect(clampTrayHeight(430, 900)).toBe(430);
    expect(clampTrayHeight(850, 900)).toBe(675);
  });

  it("clamps the bottom dock column split", () => {
    expect(clampDockSplit(120, 1400)).toBe(280);
    expect(clampDockSplit(620, 1400)).toBe(620);
    expect(clampDockSplit(1300, 1400)).toBe(1040);
  });

  it("clamps the resizable project tree", () => {
    expect(clampTreeWidth(120, 1400)).toBe(300);
    expect(clampTreeWidth(420, 1400)).toBe(420);
    expect(clampTreeWidth(900, 1400)).toBe(644);
  });

  it("projects resolved XREFs below their source documents", () => {
    const dependency = { id: "edge-1", source_asset_id: "head", referenced_asset_id: "base", reference_name: "base", status: "resolved" } as CadXrefDependency;
    const missing = { id: "edge-2", source_asset_id: "head", referenced_asset_id: null, reference_name: "missing", status: "missing" } as CadXrefDependency;
    const forest = buildCadDependencyForest([["head", "head.dwg"], ["base", "xref/base.dwg"]], [dependency, missing]);
    expect(forest).toHaveLength(1);
    expect(forest[0].assetId).toBe("head");
    expect(forest[0].children[0].assetId).toBe("base");
    expect(forest[0].children[0].via?.id).toBe("edge-1");
    expect(forest[0].unresolved[0].id).toBe("edge-2");
  });

  it("does not mark review and publication complete prematurely", () => {
    expect(wizardStepStates({ fileCount: 12, cadCount: 4, cadAnalyzed: false, openFindings: 2, reviewAccepted: false, published: false }))
      .toEqual(["complete", "current", "upcoming", "upcoming"]);
    expect(wizardStepStates({ fileCount: 12, cadCount: 4, cadAnalyzed: true, openFindings: 2, reviewAccepted: false, published: false }))
      .toEqual(["complete", "complete", "current", "upcoming"]);
    expect(wizardStepStates({ fileCount: 12, cadCount: 4, cadAnalyzed: true, openFindings: 0, reviewAccepted: false, published: false }))
      .toEqual(["complete", "complete", "current", "upcoming"]);
    expect(wizardStepStates({ fileCount: 12, cadCount: 4, cadAnalyzed: true, openFindings: 0, reviewAccepted: true, published: true }))
      .toEqual(["complete", "complete", "complete", "complete"]);
  });
  it("classifies semantic workspace roots from directory names", () => {
    expect(cadWorkspaceKind("Проектное решение/DWG/head.dwg")).toBe("project_solution");
    expect(cadWorkspaceKind("Исходные данные/base.dwg")).toBe("source_data");
    expect(cadWorkspaceKind("Архив/old.dwg")).toBe("archive");
  });

  it("builds semantic roots and repeats a shared target below both parents", () => {
    const dependencies = [{ id: "e1", source_asset_id: "a", referenced_asset_id: "shared", reference_name: "shared" }, { id: "e2", source_asset_id: "b", referenced_asset_id: "shared", reference_name: "shared" }] as CadXrefDependency[];
    const roots = buildCadWorkspaceRoots([["a", "Проектное решение/a.dwg"], ["b", "Проектное решение/b.dwg"], ["shared", "Исходные данные/shared.dwg"]], dependencies);
    expect(roots).toHaveLength(1);
    expect(roots[0].kind).toBe("project_solution");
    expect(roots[0].nodes.map((node) => node.children[0].assetId)).toEqual(["shared", "shared"]);
  });

  it("never offers a non-archive target to an archive source", () => {
    const xref = { source_relative_path: "Архив/head.dwg", matches: ["Архив/base.dwg", "Проектное решение/base.dwg"] } as CadXrefDependency;
    const files = [{ id: "archive", relative_path: "Архив/base.dwg", size_bytes: 10, source_modified_at: "2026-01-02T00:00:00Z", uploaded_at: "2026-01-03T00:00:00Z" }, { id: "project", relative_path: "Проектное решение/base.dwg", size_bytes: 10, source_modified_at: "2026-01-04T00:00:00Z", uploaded_at: "2026-01-05T00:00:00Z" }] as IntakeFile[];
    const options = xrefCandidateOptions(xref, files);
    expect(options.find((item) => item.file?.id === "archive")).toMatchObject({ compatible: true, recommended: true });
    expect(options.find((item) => item.file?.id === "project")).toMatchObject({ compatible: false, recommended: false });
  });
});
