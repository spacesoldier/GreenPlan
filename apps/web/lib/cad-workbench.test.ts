import { describe, expect, it } from "vitest";
import { areAllCadLayersClassified, buildCadDependencyForest, buildCadWorkspaceRoots, buildDeliveryTree, cadCategoryGroups, cadCategoryLabel, cadCategoryOptions, cadWorkspaceKind, effectiveFindingSelection, hostPathParts, layerMatchesReviewMode, nextFindingSelection, clampDockSplit, clampTrayHeight, clampTreeWidth, groupLayerFamilies, normalizedLayerName, projectRelativePath, reviewableLayerSuggestionIds, newlyAssistantClassifiedSuggestionIds, toggleScopedSelection, wizardStepStates, xrefCandidateOptions } from "./cad-workbench";
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

  it("formats a host path without the delivery root", () => {
    expect(hostPathParts("Старый Гай/Проектное решение/DWG/head.dwg")).toEqual({ leading: ["Проектное решение"], folder: "DWG", file: "head.dwg" });
  });

  it("removes the delivery root from an inspector document path", () => {
    expect(projectRelativePath("Старый Гай/Проектное решение/DWG/head.dwg")).toBe("Проектное решение/DWG/head.dwg");
    expect(projectRelativePath("head.dwg")).toBe("head.dwg");
  });
  it("groups final classes by engineering meaning", () => {
    expect(cadCategoryGroups.map((group) => group.label)).toEqual([
      "Быстрый выбор", "Растительность", "Здания и сооружения", "Улицы и дорожки",
      "Инженерные сети — точный тип", "Границы и зоны", "Рельеф",
    ]);
    expect(cadCategoryOptions.find(([code]) => code === "utility.unknown")?.[1]).toContain("Инженерные сети");
  });

  it("presents machine category codes as readable labels", () => {
    expect(cadCategoryLabel("utility.unknown")).toBe("Инженерные сети · тип не уточнён");
    expect(cadCategoryLabel("utility.power.cable")).toBe("Силовой кабель");
    expect(cadCategoryLabel("custom.future.code")).toBe("custom.future.code");
  });


  it("keeps focus in the current file, then advances without jumping backwards", () => {
    const before = [
      { id: "previous", source_asset_id: "file-a", status: "open" },
      { id: "current", source_asset_id: "file-b", status: "open" },
      { id: "same-file", source_asset_id: "file-b", status: "open" },
      { id: "next", source_asset_id: "file-c", status: "open" },
    ];
    expect(nextFindingSelection(before, before.filter((item) => item.id !== "current"), "current")).toBe("same-file");
    expect(nextFindingSelection(before, before.filter((item) => !["current", "same-file"].includes(item.id)), "current")).toBe("next");
    expect(nextFindingSelection(before, before.filter((item) => item.source_asset_id === "file-a"), "next")).toBe("");
  });
  it("uses the first actionable finding when no row was explicitly selected", () => {
    const findings = [
      { id: "first", source_asset_id: "file-a", status: "open" },
      { id: "resolved", source_asset_id: "file-a", status: "accepted" },
      { id: "second", source_asset_id: "file-b", status: "rejected" },
    ];
    expect(effectiveFindingSelection(findings, "")).toBe("first");
    expect(effectiveFindingSelection(findings, "second")).toBe("second");
    expect(effectiveFindingSelection(findings, "resolved")).toBe("first");
  });


  it("allows accepted and rejected layer suggestions to be selected again", () => {
    const layers = [
      { suggestion_id: "pending", review_status: "pending" },
      { suggestion_id: "accepted", review_status: "accepted" },
      { suggestion_id: "rejected", review_status: "rejected" },
      { suggestion_id: "old", review_status: "superseded" },
    ] as CadLayer[];
    expect(reviewableLayerSuggestionIds(layers)).toEqual(["pending", "accepted", "rejected"]);
  });
  it("marks only non-empty documents with every layer classified as ready", () => {
    expect(areAllCadLayersClassified([])).toBe(false);
    expect(areAllCadLayersClassified([{ mapping_status: "confirmed" }, { mapping_status: "confirmed" }] as CadLayer[])).toBe(true);
    expect(areAllCadLayersClassified([{ mapping_status: "confirmed" }, { mapping_status: "candidate" }] as CadLayer[])).toBe(false);
  });
  it("selects or clears only the layers in the visible scope", () => {
    expect(toggleScopedSelection(["outside", "a"], ["a", "b"], true)).toEqual(["outside", "a", "b"]);
    expect(toggleScopedSelection(["outside", "a", "b"], ["a", "b"], false)).toEqual(["outside"]);
  });
  it("finds only fresh assistant confirmations for departure animation", () => {
    const previous = [
      { id: "layer-a", suggestion_id: "suggestion-a", mapping_status: "candidate", axis_results: {} },
      { id: "layer-b", suggestion_id: "suggestion-b", mapping_status: "confirmed", axis_results: {} },
    ] as CadLayer[];
    const next = [
      { id: "layer-a", suggestion_id: "new-suggestion-a", mapping_status: "confirmed", axis_results: { assistant_assigned: true } },
      { id: "layer-b", suggestion_id: "suggestion-b", mapping_status: "confirmed", axis_results: { assistant_assigned: true } },
    ] as CadLayer[];
    expect(newlyAssistantClassifiedSuggestionIds(previous, next)).toEqual(["suggestion-a"]);
  });
  it("filters unknown and engineer-reviewed layers without disabling reselection", () => {
    const unknown = { suggested_category: "unknown", review_status: "pending", mapping_status: "candidate" } as CadLayer;
    const suggested = { suggested_category: "utility.unknown", review_status: "pending", mapping_status: "candidate" } as CadLayer;
    const reviewed = { suggested_category: "utility.unknown", review_status: "accepted", mapping_status: "confirmed" } as CadLayer;
    expect(layerMatchesReviewMode(unknown, "unknown")).toBe(true);
    expect(layerMatchesReviewMode(suggested, "unknown")).toBe(true);
    expect(layerMatchesReviewMode(reviewed, "reviewed")).toBe(true);
    expect(layerMatchesReviewMode(suggested, "reviewed")).toBe(false);
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
