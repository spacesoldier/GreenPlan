export async function domainJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/domain${path}`, { cache: "no-store", ...init });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? `HTTP ${response.status}`);
  }
  return body as T;
}

export function formatBytes(value: number): string {
  if (!value) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ"];
  const rank = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** rank).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} ${units[rank]}`;
}
