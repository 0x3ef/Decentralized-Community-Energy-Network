import { useState } from "react";
import { useNativeWallet, useApi, useCommunity } from "../../shared/api/hooks";
import { communityPath } from "../../shared/api/client";
import type { ParticipantStatement } from "../../shared/api/models";
import { useWallet } from "../../shared/blockchain/WalletProvider";
import {
  useTransactions,
  activeState,
} from "../../shared/blockchain/transactions";
import { Page, Card, Form, Field, Notice } from "../../shared/ui/components";
import { parseAmount, errorMessage, eth } from "../../shared/utils/format";
import { WalletPanel } from "./WalletPanel";
const actions = [
  ["deposit", "Depositar ETH"],
  ["withdraw", "Retirar ETH disponible"],
  ["withdraw_earnings", "Retirar ingresos de productor"],
  ["approve_sun", "Autorizar SUN para depósito"],
  ["escrow_sun", "Depositar SUN"],
  ["withdraw_sun", "Retirar SUN disponibles"],
] as const;
export default function DepositsPage() {
  const native = useNativeWallet(),
    wallet = useWallet(),
    tx = useTransactions(),
    { id } = useCommunity();
  const statement = useApi<ParticipantStatement>(
    `${communityPath(id)}/settlement-statement`,
    !!id,
  );
  const [action, setAction] = useState<string>("deposit"),
    [error, setError] = useState("");
  return (
    <Page
      title="Depósitos y retiros"
      description="Gestiona fondos del protocolo con una firma explícita y confirmación en cadena."
    >
      <WalletPanel balances />
      <div className="two-col">
        <Card title="Nueva operación">
          <Form
            onSubmit={async (data) => {
              setError("");
              try {
                if (!native.data)
                  throw new Error(
                    "Espera a que se consulten los balances confirmados.",
                  );
                const amount = parseAmount(String(data.get("amount")));
                const n = native.data;
                const maximum: Record<string, bigint> = {
                  withdraw: BigInt(n.available_wei),
                  withdraw_earnings: BigInt(n.earnings_wei),
                  escrow_sun: BigInt(n.sun_units),
                  withdraw_sun: BigInt(n.escrow_sun_units),
                };
                if (maximum[action] !== undefined && amount > maximum[action])
                  throw new Error(
                    "El importe supera el saldo disponible no reservado.",
                  );
                if (action === "deposit" && amount >= BigInt(n.wallet_wei))
                  throw new Error("Deja ETH en tu wallet para cubrir el gas.");
                await tx.begin({
                  action,
                  label: `${actions.find((a) => a[0] === action)?.[1]} · ${data.get("amount")} ${action.includes("sun") ? "SUN" : "ETH"}`,
                  body: { amount_base_units: amount.toString() },
                });
              } catch (e) {
                setError(errorMessage(e));
              }
            }}
          >
            <Field label="Operación">
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                {actions.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label={`Importe (${action.includes("sun") ? "SUN" : "ETH"})`}
              hint="Hasta 18 decimales. Usa coma o punto decimal, sin separadores de miles."
            >
              <input
                name="amount"
                inputMode="decimal"
                required
                placeholder="0,01"
              />
            </Field>
            {action === "escrow_sun" && (
              <Notice>
                Primero autoriza el importe exacto de SUN para el vault; espera
                su confirmación y después deposítalo. La autorización no mueve
                tokens.
              </Notice>
            )}
            {action === "approve_sun" && (
              <Notice>
                La autorización permite al vault transferir únicamente el
                importe introducido. Confirma el contrato y el límite en
                MetaMask.
              </Notice>
            )}
            {error && <Notice tone="warning">{error}</Notice>}
            <button
              className="primary"
              disabled={
                !wallet.linked ||
                wallet.address?.toLowerCase() !==
                  native.data?.address.toLowerCase() ||
                wallet.chainId !== wallet.expectedChain ||
                !native.data ||
                activeState(tx.state)
              }
            >
              Revisar operación
            </button>
          </Form>
        </Card>
        <Card title="Tus fondos, con claridad">
          <dl className="detail-list">
            <dt>ETH en wallet</dt>
            <dd>Permanece bajo control de tu wallet.</dd>
            <dt>Depósito disponible</dt>
            <dd>Fondos confirmados que el protocolo puede reservar.</dd>
            <dt>ETH reservado</dt>
            <dd>No se puede retirar mientras garantiza una asignación.</dd>
            <dt>Ingresos de productor</dt>
            <dd>ETH ganado por liquidaciones confirmadas.</dd>
            <dt>Ingresos ya retirados</dt>
            <dd>{eth(statement.data?.withdrawn_earnings_wei)}</dd>
          </dl>
          <Notice>
            Sepolia ETH y Anvil ETH son activos de prueba sin valor monetario
            real. El saldo de tu wallet no es tu depósito en el vault.
          </Notice>
          <p className="fine-print">
            Las retiradas seguras pueden seguir disponibles aunque la comunidad
            esté suspendida; el contrato decide si están permitidas.
          </p>
        </Card>
      </div>
    </Page>
  );
}
