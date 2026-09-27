import { describe, expect, it } from "vitest";
import { inspectFolderSelection, partitionProjectFiles, relativeUploadPath } from "./folder-selection";

describe("folder selection", () => {
  it("preserves the selected root and nested relative paths", () => {
    const files = [
      { name: "head.dwg", webkitRelativePath: "Старый Гай/head.dwg" },
      { name: "base.dwg", webkitRelativePath: "Старый Гай/00_Ссылки/base.dwg" },
    ];
    expect(inspectFolderSelection(files)).toEqual({
      valid: true, root: "Старый Гай", fileCount: 2, nestedFileCount: 1,
    });
    expect(relativeUploadPath(files[1])).toBe("Старый Гай/00_Ссылки/base.dwg");
  });

  it("rejects a plain multi-file picker pretending to be a folder", () => {
    expect(inspectFolderSelection([{ name: "a.dwg" }, { name: "b.dwg" }]).valid).toBe(false);
  });

  it("keeps CAD and spreadsheet formats and skips unrelated delivery files", () => {
    const result = partitionProjectFiles([
      { name: "plan.DWG" }, { name: "existing.dxf" }, { name: "plants.xlsm" },
      { name: "register.xlsb" }, { name: "table.ods" }, { name: "notes.pdf" }, { name: "photo.jpg" },
    ]);
    expect(result.supported.map((file) => file.name)).toEqual([
      "plan.DWG", "existing.dxf", "plants.xlsm", "register.xlsb", "table.ods",
    ]);
    expect(result.skipped.map((file) => file.name)).toEqual(["notes.pdf", "photo.jpg"]);
  });
});
