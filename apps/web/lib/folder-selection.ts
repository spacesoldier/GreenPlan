export type FolderFile = { name: string; webkitRelativePath?: string };

export type FolderSelection = {
  valid: boolean;
  root: string | null;
  fileCount: number;
  nestedFileCount: number;
};

export const SUPPORTED_PROJECT_EXTENSIONS = new Set([
  ".dwg", ".dxf",
  ".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm", ".csv", ".ods",
]);

export function isSupportedProjectFile(file: FolderFile): boolean {
  const dot = file.name.lastIndexOf(".");
  return dot >= 0 && SUPPORTED_PROJECT_EXTENSIONS.has(file.name.slice(dot).toLocaleLowerCase());
}

export function partitionProjectFiles<T extends FolderFile>(files: ArrayLike<T>): {
  supported: T[]; skipped: T[];
} {
  const values = Array.from(files);
  return {
    supported: values.filter(isSupportedProjectFile),
    skipped: values.filter((file) => !isSupportedProjectFile(file)),
  };
}

export function relativeUploadPath(file: FolderFile): string {
  return (file.webkitRelativePath || file.name).replace(/^\/+/, "");
}

export function inspectFolderSelection(files: ArrayLike<FolderFile>): FolderSelection {
  const values = Array.from(files);
  const relative = values.map((file) => file.webkitRelativePath || "").filter(Boolean);
  const roots = new Set(relative.map((path) => path.split("/")[0]).filter(Boolean));
  return {
    valid: values.length > 0 && relative.length === values.length && roots.size === 1,
    root: roots.size === 1 ? Array.from(roots)[0] : null,
    fileCount: values.length,
    nestedFileCount: relative.filter((path) => path.split("/").length > 2).length,
  };
}
