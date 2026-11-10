// Domain-to-view mapping: never derive household load from signed grid power.
export function measurementValue(
  payload: Record<string, unknown> | undefined,
  key: string,
): string {
  const data = payload?.data;
  if (!data || typeof data !== "object") return "—";
  const value = (data as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("es-CO", { maximumFractionDigits: 3 })
    : typeof value === "string" && /^\d+(\.\d+)?$/.test(value)
      ? value.replace(".", ",")
      : "—";
}
export function measurementIsStale(at: string | undefined, now = Date.now()) {
  return !at || now - new Date(at).getTime() > 120_000;
}
