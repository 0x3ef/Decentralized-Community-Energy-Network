import { statusLabel } from "../../shared/ui/i18n";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTimelock } from "../../shared/blockchain/read-hooks";
import { useRoles } from "../../shared/blockchain/WalletProvider";
import {
  useTransactions,
  activeState,
} from "../../shared/blockchain/transactions";
import { useCommunity } from "../../shared/api/hooks";
import { api, communityPath } from "../../shared/api/client";
import type { Prepared } from "../../shared/api/models";
import {
  Page,
  Card,
  QueryState,
  Field,
  Form,
  Notice,
  Empty,
  Hash,
} from "../../shared/ui/components";
import { errorMessage, parseAmount } from "../../shared/utils/format";
import { WalletPanel } from "../wallet/WalletPanel";
import { useAuth } from "../auth/AuthProvider";
interface Plan {
  community: string;
  user: string;
  prepared: Prepared;
  action: string;
  description: string;
}
function loadPlans(): Plan[] {
  try {
    return JSON.parse(
      localStorage.getItem("solar.governance") ?? "[]",
    ) as Plan[];
  } catch {
    return [];
  }
}
function TimelockOperation({ plan }: { plan: Plan }) {
  const tx = useTransactions(),
    { id } = useCommunity();
  const p = plan.prepared;
  const ready = useTimelock(p);
  return (
    <Card title={plan.description}>
      <p>
        Dilación mínima: {p.delay_seconds} segundos. La programación no ejecuta
        la acción.
      </p>
      <Hash value={p.operation_id!} />
      <QueryState query={ready}>
        <p>
          {ready.data?.done
            ? "Operación ejecutada en cadena"
            : ready.data?.ready
              ? "La operación puede ejecutarse"
              : "Esperando programación o vencimiento del plazo"}
        </p>
      </QueryState>
      <div className="actions">
        <button
          disabled={activeState(tx.state) || ready.data?.done || ready.data?.pending}
          onClick={() =>
            void tx.begin({
              action: "governance_schedule",
              label: `Programar: ${plan.description}`,
              track: false,
              prepare: async () => ({
                ...p,
                ...p.schedule!,
                status: "AWAITING_USER_SIGNATURE",
              }),
            })
          }
        >
          Programar en timelock
        </button>
        <button
          className="primary"
          disabled={!ready.data?.ready || activeState(tx.state)}
          onClick={() =>
            void tx.begin({
              action: "governance_execute",
              label: `Ejecutar: ${plan.description}`,
              track: false,
              prepare: async () => {
                const refreshed = await ready.refetch();
                if (!refreshed.data?.ready)
                  throw new Error(
                    "El timelock todavía no permite ejecutar esta operación.",
                  );
                return {
                  ...p,
                  ...p.execute!,
                  status: "AWAITING_USER_SIGNATURE",
                };
              },
              syncPath:
                plan.action === "transition"
                  ? `${communityPath(id)}/governance/sync`
                  : undefined,
              after:
                plan.action === "transition"
                  ? (hash) =>
                      api(`${communityPath(id)}/governance/sync`, {
                        method: "POST",
                        body: { transaction_hash: hash },
                      })
                  : undefined,
            })
          }
        >
          Ejecutar acción autorizada
        </button>
      </div>
      <p className="fine-print">
        Después de ejecutar membresías o nodos, sincroniza su estado con el
        registro desde la pantalla correspondiente. La indexación puede requerir
        más bloques.
      </p>
    </Card>
  );
}
export default function GovernancePage() {
  const [params] = useSearchParams();
  const roles = useRoles(),
    { id, community } = useCommunity(),
    { user } = useAuth(),
    tx = useTransactions();
  const [action, setAction] = useState(
      params.get("action") === "finalize_batch" ? "finalize_batch" : "transition",
    ),
    [error, setError] = useState(""),
    [plans, setPlans] = useState<Plan[]>(loadPlans);
  async function prepare(data: FormData) {
    setError("");
    try {
      const body: Record<string, unknown> = {
        action,
        address:
          data.get("address") || "0x0000000000000000000000000000000000000000",
        status: Number(data.get("status") ?? 0),
        active: data.get("active") === "on",
      };
      if (data.get("node_id")) body.node_id = data.get("node_id");
      if (data.get("meter_id")) body.meter_id = data.get("meter_id");
      if (action === "finalize_batch") body.batch_id = data.get("batch_id");
      if (action === "price")
        body.price_wei_per_kwh = parseAmount(
          String(data.get("price")),
        ).toString();
      const prepared = await api<Prepared>(
        `${communityPath(id)}/governance/prepare`,
        { method: "POST", body },
      );
      if (prepared.timelock) {
        if (
          prepared.timelock.toLowerCase() !==
          String(import.meta.env.VITE_TIMELOCK_ADDRESS).toLowerCase()
        )
          throw new Error("El timelock no coincide con la configuración.");
        const next = [
          {
            community: id,
            user: user!.uid,
            prepared,
            action,
            description:
              action === "finalize_batch"
                ? `Finalizar lote ${String(body.batch_id)}`
                : `${action} · comunidad ${id}`,
          },
          ...plans,
        ];
        setPlans(next);
        localStorage.setItem("solar.governance", JSON.stringify(next));
      } else
        await tx.begin({
          action: `governance_${action}`,
          label: `Ejecutar acción de registro: ${action}`,
          body,
          track: false,
          prepare: async () => prepared,
          syncPath:
            action === "transition"
              ? `${communityPath(id)}/governance/sync`
              : undefined,
          after:
            action === "transition"
              ? (hash) =>
                  api(`${communityPath(id)}/governance/sync`, {
                    method: "POST",
                    body: { transaction_hash: hash },
                  })
              : undefined,
        });
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  return (
    <Page
      title="Gobernanza"
      description="Acciones del registro basadas en roles confirmados en cadena, con timelock cuando corresponde."
    >
      <WalletPanel />
      {!roles.data?.governance ? (
        <Card>
          <Empty title="Se requiere un rol autorizado">
            Conecta tu wallet verificada en la red configurada. La aplicación
            consulta los roles del registro y del timelock; una cuenta de
            usuario no concede autoridad.
          </Empty>
          {roles.error && (
            <Notice tone="warning">{errorMessage(roles.error)}</Notice>
          )}
        </Card>
      ) : (
        <>
          <Notice>
            La gobernanza usa roles y operaciones del contrato. El backend y la
            cadena vuelven a comprobar cada permiso.
          </Notice>
          <Card title="Preparar acción de gobernanza">
            <Form onSubmit={prepare}>
              <Field label="Acción">
                <select
                  value={action}
                  onChange={(e) => setAction(e.target.value)}
                >
                  <option value="transition">
                    Transición y operador de comunidad
                  </option>
                  <option value="membership">Estado de membresía</option>
                  <option value="node">Registrar nodo</option>
                  <option value="meter">Autorizar medidor</option>
                  <option value="finalize_batch">Finalizar lote energético</option>
                  <option
                    value="price"
                    disabled={community?.status !== "APPROVED"}
                  >
                    Precio de liquidación · requiere comunidad aprobada
                  </option>
                </select>
              </Field>
              {action === "finalize_batch" && (
                <>
                  <Field label="UUID del lote energético">
                    <input
                      name="batch_id"
                      defaultValue={params.get("batch") ?? ""}
                      required
                      pattern="[a-fA-F0-9-]{36}"
                    />
                  </Field>
                  <Notice>
                    Revisa el lote en Liquidación antes de aprobarlo. Debe estar
                    en revisión y haber terminado su período de impugnación.
                    Programa la operación y después ejecútala con la wallet de
                    gobernanza. Una vez finalizado, el worker tramita la emisión
                    SUN de los aportes elegibles sin exigir depósitos previos.
                  </Notice>
                </>
              )}
              {["transition", "membership"].includes(action) && (
                <Field label="Estado de destino">
                  <select name="status">
                    {(action === "transition"
                      ? [
                          "DRAFT",
                          "PROPOSED",
                          "UNDER_REVIEW",
                          "APPROVED",
                          "ACTIVE",
                          "SUSPENDED",
                          "REJECTED",
                          "ARCHIVED",
                        ]
                      : [
                          "NONE",
                          "PENDING",
                          "APPROVED",
                          "ACTIVE",
                          "SUSPENDED",
                          "REVOKED",
                        ]
                    ).map((s, i) => (
                      <option key={s} value={i}>
                        {statusLabel(s)}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {["transition", "membership", "node"].includes(action) && (
                <Field
                  label={
                    action === "transition"
                      ? "Wallet del operador"
                      : "Wallet del participante"
                  }
                >
                  <input name="address" pattern="0x[0-9a-fA-F]{40}" required />
                </Field>
              )}
              {["node", "meter"].includes(action) && (
                <Field label="UUID del nodo">
                  <input name="node_id" required pattern="[a-fA-F0-9-]{36}" />
                </Field>
              )}
              {action === "meter" && (
                <>
                  <Field label="UUID interno del dispositivo">
                    <input
                      name="meter_id"
                      required
                      pattern="[a-fA-F0-9-]{36}"
                    />
                  </Field>
                  <label className="check">
                    <input name="active" type="checkbox" defaultChecked />{" "}
                    Autorizar medidor
                  </label>
                </>
              )}
              {action === "price" && (
                <Field label="Precio ETH/kWh">
                  <input name="price" inputMode="decimal" required />
                </Field>
              )}
              {error && <Notice tone="warning">{error}</Notice>}
              <button className="primary" disabled={activeState(tx.state)}>
                Preparar para revisión
              </button>
            </Form>
          </Card>
          {plans
            .filter((p) => p.community === id && p.user === user?.uid)
            .map((p) => (
              <TimelockOperation key={p.prepared.operation_id} plan={p} />
            ))}
        </>
      )}
    </Page>
  );
}
