import { describe, it, expect } from "vitest";
import { units, parseAmount, kwh, eth } from "../shared/utils/format";
describe("exact accounting units", () => {
  it("preserves integers beyond Number.MAX_SAFE_INTEGER", () => {
    expect(parseAmount("123456789,123456789123456789")).toBe(
      123456789123456789123456789n,
    );
    expect(units("123456789123456789123456789", 18, 18)).toBe(
      "123.456.789,123456789123456789",
    );
  });
  it("keeps unavailable data separate from zero", () => {
    expect(eth()).toBe("— ETH");
    expect(eth("0")).toBe("0 ETH");
    expect(kwh(undefined)).toBe("—");
    expect(kwh(0)).toBe("0 kWh");
  });
  it("does not round a positive wei balance to zero", () => {
    expect(units("1")).toBe("<0,000001");
    expect(units("1000000000000000")).toBe("0,001");
  });
  it("maps whole Wh to kWh exactly", () => {
    expect(kwh(12345)).toBe("12,345 kWh");
  });
  it.each([
    "1e5",
    "-1",
    "0",
    "1,000.1",
    "NaN",
    "Infinity",
    "0.0000000000000000001",
  ])("rejects invalid amount %s", (value) => {
    expect(() => parseAmount(value)).toThrow();
  });
});

import {
  measurementValue,
  measurementIsStale,
} from "../shared/utils/telemetry";
it("does not substitute signed grid power for household consumption", () => {
  const payload = { data: { active_power_w: -300, grid_export_power_w: 300 } };
  expect(measurementValue(payload, "consumption_power_w")).toBe("—");
  expect(measurementValue(payload, "active_power_w")).toBe("-300");
});
it("marks missing or old telemetry stale", () => {
  expect(measurementIsStale(undefined)).toBe(true);
  expect(
    measurementIsStale(
      "2026-01-01T00:00:00Z",
      Date.parse("2026-01-01T00:03:00Z"),
    ),
  ).toBe(true);
});
