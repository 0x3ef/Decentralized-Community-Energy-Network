import { it, expect } from "vitest";
import { encodeFunctionData, type Abi } from "viem";
import { validateNativeCall } from "../shared/blockchain/validate";
import vault from "../shared/blockchain/NativeSettlementVault.json";
import sun from "../shared/blockchain/SUNToken.json";
import type { NativeWallet, Prepared } from "../shared/api/models";
const address = "0x1111111111111111111111111111111111111111",
  v = "0x2222222222222222222222222222222222222222",
  s = "0x3333333333333333333333333333333333333333",
  settlement = "0x4444444444444444444444444444444444444444";
const native = {
  contracts: {
    vault_address: v,
    sun_address: s,
    settlement_address: settlement,
  },
  price_wei_per_kwh: "1000",
} as NativeWallet;
const prepared = {
  to: v,
  value: "2000",
  data: encodeFunctionData({
    abi: vault as Abi,
    functionName: "deposit",
    args: [1000n],
  }),
} as Prepared;
it("validates the deposit contract, amount and governed price", () => {
  expect(() =>
    validateNativeCall(
      prepared,
      "deposit",
      { amount_base_units: "2000" },
      native,
      address,
    ),
  ).not.toThrow();
  expect(() =>
    validateNativeCall(
      { ...prepared, value: "3000" },
      "deposit",
      { amount_base_units: "2000" },
      native,
      address,
    ),
  ).toThrow("valor ETH");
  expect(() =>
    validateNativeCall(
      { ...prepared, to: s },
      "deposit",
      { amount_base_units: "2000" },
      native,
      address,
    ),
  ).toThrow("destino");
});
it("rejects approval to an unrelated spender or a larger allowance", () => {
  const data = encodeFunctionData({
    abi: sun as Abi,
    functionName: "approve",
    args: [settlement, 999n],
  });
  expect(() =>
    validateNativeCall(
      { ...prepared, to: s, value: "0", data },
      "approve_sun",
      { amount_base_units: "100" },
      native,
      address,
    ),
  ).toThrow("autorizado");
});
it("rejects a withdrawal to someone else", () => {
  const data = encodeFunctionData({
    abi: vault as Abi,
    functionName: "withdraw",
    args: [100n, s],
  });
  expect(() =>
    validateNativeCall(
      { ...prepared, value: "0", data },
      "withdraw",
      { amount_base_units: "100" },
      native,
      address,
    ),
  ).toThrow("tu wallet");
});
