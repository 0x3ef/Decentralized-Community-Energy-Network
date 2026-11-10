import { decodeFunctionData, type Abi, type Address } from "viem";
import vaultAbi from "./NativeSettlementVault.json";
import sunAbi from "./SUNToken.json";
import settlementAbi from "./CommunitySettlement.json";
import type { NativeWallet, Prepared } from "../api/models";
export function validateNativeCall(
  prepared: Prepared,
  action: string,
  body: Record<string, unknown>,
  native: NativeWallet,
  address: Address,
) {
  const c = native.contracts,
    approval = action.startsWith("approve"),
    retire = action === "retire";
  const expected = approval
    ? c.sun_address
    : retire
      ? c.settlement_address
      : c.vault_address;
  if (prepared.to.toLowerCase() !== expected.toLowerCase())
    throw new Error(
      "El contrato de destino no coincide con el despliegue verificado.",
    );
  const decoded = decodeFunctionData({
    abi: (approval ? sunAbi : retire ? settlementAbi : vaultAbi) as Abi,
    data: prepared.data as `0x${string}`,
  });
  const names: Record<string, string> = {
    deposit: "deposit",
    withdraw: "withdraw",
    withdraw_earnings: "withdrawEarnings",
    approve_sun: "approve",
    approve_retirement: "approve",
    escrow_sun: "depositSUN",
    withdraw_sun: "withdrawSUN",
    execute: "execute",
    cancel: "cancel",
    retire: "retire",
  };
  if (decoded.functionName !== names[action])
    throw new Error(
      "La llamada preparada no corresponde a la operación solicitada.",
    );
  const args = decoded.args ?? [],
    amount = BigInt(String(body.amount_base_units ?? "0"));
  if (BigInt(prepared.value) !== (action === "deposit" ? amount : 0n))
    throw new Error("El valor ETH no coincide con el importe revisado.");
  if (action === "deposit" && args[0] !== BigInt(native.price_wei_per_kwh))
    throw new Error(
      "El precio cambió. Actualiza los balances y prepara otra vez.",
    );
  if (
    ["withdraw", "withdraw_earnings", "escrow_sun", "withdraw_sun"].includes(
      action,
    ) &&
    args[0] !== amount
  )
    throw new Error("El importe del contrato no coincide con el solicitado.");
  if (
    ["withdraw", "withdraw_earnings"].includes(action) &&
    String(args[1]).toLowerCase() !== address.toLowerCase()
  )
    throw new Error("La retirada debe enviarse a tu wallet.");
  if (approval) {
    const spender =
      action === "approve_retirement" ? c.settlement_address : c.vault_address;
    if (
      String(args[0]).toLowerCase() !== spender.toLowerCase() ||
      args[1] !== amount
    )
      throw new Error("El límite o contrato autorizado para SUN no coincide.");
  }
  if (retire) {
    const expectedArgs = [
      body.batch_id,
      body.claim_id,
      body.node_id,
      body.meter_id,
      amount,
      body.proof,
    ];
    if (
      JSON.stringify(args, (_, v) =>
        typeof v === "bigint" ? v.toString() : v,
      ).toLowerCase() !==
      JSON.stringify(expectedArgs, (_, v) =>
        typeof v === "bigint" ? v.toString() : v,
      ).toLowerCase()
    )
      throw new Error(
        "La prueba de consumo no coincide con la compensación revisada.",
      );
  }
}
