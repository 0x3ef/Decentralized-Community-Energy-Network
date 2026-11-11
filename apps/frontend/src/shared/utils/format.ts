import { formatUnits, parseUnits } from "viem";
export function units(
  value: string | bigint | null | undefined,
  decimals = 18,
  maximum = 6,
): string {
  if (value == null) return "—";
  const amount = BigInt(value);
  const exact = formatUnits(amount, decimals);
  const [whole, fraction = ""] = exact.split(".");
  const short = fraction.slice(0, maximum).replace(/0+$/, "");
  if (amount > 0n && BigInt(whole) === 0n && !short)
    return `<0,${"0".repeat(maximum - 1)}1`;
  return BigInt(whole).toLocaleString("es-CO") + (short ? `,${short}` : "");
}
export const eth = (value?: string | null) => `${units(value)} ETH`;
export const kwh = (value?: number | null) =>
  value == null ? "—" : `${units(BigInt(value), 3, 3)} kWh`;
export const exactUnits = (value: string, decimals = 18) =>
  formatUnits(BigInt(value), decimals);
export function parseAmount(value: string, decimals = 18) {
  if (!/^\d+(?:[.,]\d+)?$/.test(value.trim()))
    throw new Error("Introduce un importe positivo sin separadores de miles.");
  const normalized = value.trim().replace(",", ".");
  if ((normalized.split(".")[1]?.length ?? 0) > decimals)
    throw new Error(`El importe admite hasta ${decimals} decimales.`);
  const amount = parseUnits(normalized, decimals);
  if (amount >= 2n ** 256n)
    throw new Error("El importe supera el límite del contrato.");
  if (amount <= 0n) throw new Error("El importe debe ser mayor que cero.");
  return amount;
}
export const short = (v?: string | null) =>
  v ? `${v.slice(0, 6)}…${v.slice(-4)}` : "—";
export const date = (v?: string | null) =>
  v
    ? new Intl.DateTimeFormat("es-CO", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "America/Bogota",
      }).format(new Date(v))
    : "—";
export const errorMessage = (e: unknown) =>
  e instanceof Error ? e.message : "No se pudo completar la operación.";
