import { statusLabel } from "../../shared/ui/i18n";
import { useState } from "react";
import { useApi, useCommunity, useNativeWallet } from "../../shared/api/hooks";
import { communityPath } from "../../shared/api/client";
import type { BatchView, ClaimView } from "../../shared/api/models";
import { useWallet } from "../../shared/blockchain/WalletProvider";
import {
  useTransactions,
  activeState,
} from "../../shared/blockchain/transactions";
import {
  Page,
  Card,
  QueryState,
  Empty,
  Notice,
  Field,
  Metric,
  Badge,
  Pagination,
} from "../../shared/ui/components";
import { kwh, units, date } from "../../shared/utils/format";
import { WalletPanel } from "../wallet/WalletPanel";
function Claims({ batch }: { batch: BatchView }) {
  const { id } = useCommunity(),
    native = useNativeWallet(),
    wallet = useWallet(),
    tx = useTransactions();
  const [offset, setOffset] = useState(0);
  const q = useApi<ClaimView[]>(
    `${communityPath(id)}/settlements/${batch.id}/claims?kind=1&limit=20&offset=${offset}`,
    true,
    true,
  );
  const [selected, setSelected] = useState("");
  const claim = q.data?.find((c) => c.id === selected);
  const canRetire =
    !!claim &&
    claim.retirement_eligible &&
    batch.status === "FINALIZED" &&
    claim.status !== "RETIRED";
  const required = claim ? BigInt(claim.energy_wh) * 10n ** 15n : 0n;
  return (
    <Card title="Consumo entregado y elegible">
      <QueryState query={q}>
        {q.data?.length ? (
          <>
            <Field label="Claim de consumo">
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Selecciona una evidencia</option>
                {q.data.map((c) => (
                  <option key={c.id} value={c.id}>
                    {kwh(c.energy_wh)} · {statusLabel(c.status)} · {c.id}
                  </option>
                ))}
              </select>
            </Field>
            {claim && (
              <>
                <dl className="detail-list">
                  <dt>Consumo a compensar</dt>
                  <dd>{kwh(claim.energy_wh)}</dd>
                  <dt>SUN a retirar</dt>
                  <dd>{units(required)} SUN</dd>
                  <dt>Nodo / medidor</dt>
                  <dd>
                    <code>{claim.node_id}</code> / <code>{claim.meter_id}</code>
                  </dd>
                  <dt>Estado</dt>
                  <dd>
                    <Badge value={claim.status} />
                  </dd>
                  <dt>Pago adicional ETH</dt>
                  <dd>0 ETH · solo gas</dd>
                </dl>
                {!canRetire && (
                  <Notice tone="warning">
                    Este claim no está habilitado para retiro. Se requiere
                    consumo entregado, lote finalizado y elegibilidad
                    confirmada.
                  </Notice>
                )}
                {native.data && required > BigInt(native.data.sun_units) && (
                  <Notice tone="warning">
                    No tienes suficientes SUN en tu wallet.
                  </Notice>
                )}
                <div className="actions">
                  <button
                    disabled={
                      !canRetire || !wallet.linked || activeState(tx.state)
                    }
                    onClick={() =>
                      void tx.begin({
                        action: "approve_retirement",
                        label: `Autorizar ${units(required)} SUN al contrato de liquidación para compensar consumo.`,
                        body: { amount_base_units: required.toString() },
                      })
                    }
                  >
                    1. Autorizar SUN
                  </button>
                  <button
                    className="primary"
                    disabled={
                      !canRetire ||
                      !wallet.linked ||
                      !native.data ||
                      required > BigInt(native.data.sun_units) ||
                      activeState(tx.state)
                    }
                    onClick={() =>
                      void tx.begin({
                        action: "retire",
                        label: `Retirar definitivamente ${units(required)} SUN contra ${kwh(claim.energy_wh)} de consumo entregado.`,
                        body: {
                          amount_base_units: String(claim.energy_wh),
                          claim_id: claim.chain_claim_id,
                          batch_id: batch.chain_batch_id,
                          node_id: claim.chain_node_id,
                          meter_id: claim.chain_meter_id,
                          proof: claim.proof,
                        },
                      })
                    }
                  >
                    2. Compensar consumo
                  </button>
                </div>
                <p className="fine-print">
                  Espera la confirmación de la autorización antes de compensar.
                  El contrato comprueba el allowance y la elegibilidad al
                  preparar la operación.
                </p>
              </>
            )}
          </>
        ) : (
          <Empty title="Sin consumo elegible en este lote" />
        )}
      </QueryState>
      <Pagination
        label="Páginas de consumo elegible"
        offset={offset}
        count={q.data?.length ?? 0}
        onChange={(value) => {
          setOffset(value);
          setSelected("");
        }}
      />
    </Card>
  );
}
export default function CompensationPage() {
  const { id } = useCommunity(),
    native = useNativeWallet();
  const [offset, setOffset] = useState(0);
  const batches = useApi<BatchView[]>(
    `${communityPath(id)}/settlements?status=FINALIZED&limit=20&offset=${offset}`,
    !!id,
  );
  const [chosen, setChosen] = useState("");
  const batch = batches.data?.find((b) => b.id === chosen);
  return (
    <Page
      title="Compensación energética"
      description="Retira SUN contra consumo comunitario entregado y aprobado por el protocolo."
    >
      <WalletPanel />
      <div className="metrics">
        <Metric
          label="SUN disponibles en wallet"
          value={native.data ? `${units(native.data.sun_units)} SUN` : "—"}
        />
      </div>
      <Notice>
        El retiro SUN es irreversible. No supone otro pago ETH y no modifica
        automáticamente la factura oficial de electricidad.
      </Notice>
      <Card title="Seleccionar intervalo finalizado">
        <QueryState query={batches}>
          {batches.data?.length ? (
            <Field label="Lote">
              <select
                value={chosen}
                onChange={(e) => setChosen(e.target.value)}
              >
                <option value="">Selecciona un intervalo</option>
                {batches.data.map((b) => (
                  <option key={b.id} value={b.id}>
                    {date(b.interval_start)} · {b.id}
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <Empty title="No hay lotes finalizados disponibles" />
          )}
        </QueryState>
        <Pagination
          label="Páginas de lotes finalizados"
          offset={offset}
          count={batches.data?.length ?? 0}
          onChange={(value) => {
            setOffset(value);
            setChosen("");
          }}
        />
      </Card>
      {batch && <Claims key={batch.id} batch={batch} />}
    </Page>
  );
}
