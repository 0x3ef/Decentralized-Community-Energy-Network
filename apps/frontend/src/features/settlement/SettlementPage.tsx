import { statusLabel } from "../../shared/ui/i18n";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi, useCommunity, useAction } from "../../shared/api/hooks";
import { communityPath, api } from "../../shared/api/client";
import type {
  BatchView,
  AllocationView,
  ClaimView,
  ParticipantStatement,
  Policy,
  Operation,
  FundingView,
} from "../../shared/api/models";
import { useRoles } from "../../shared/blockchain/WalletProvider";
import {
  Page,
  Card,
  Metric,
  QueryState,
  Empty,
  Badge,
  Notice,
  Field,
  Form,
  Hash,
  Pagination,
} from "../../shared/ui/components";
import { eth, kwh, date, errorMessage } from "../../shared/utils/format";
export function Statement() {
  const { id } = useCommunity();
  const q = useApi<ParticipantStatement>(
    `${communityPath(id)}/settlement-statement`,
    !!id,
    true,
  );
  return (
    <Card title="Mi estado de cuenta">
      <QueryState query={q}>
        {q.data && (
          <>
            <div className="metrics">
              <Metric
                label="Depósito disponible"
                value={eth(q.data.available_wei)}
              />
              <Metric
                label="ETH reservado"
                value={eth(q.data.reserved_wei)}
                tone="amber"
              />
              <Metric
                label="Ingresos reclamables"
                value={eth(q.data.claimable_wei)}
              />
              <Metric
                label="Obligación no liquidada"
                value={eth(q.data.unsettled_due_wei)}
                tone="blue"
              />
            </div>
            <dl className="detail-list">
              <dt>Derecho de productor liquidado</dt>
              <dd>{eth(q.data.settled_entitlement_wei)}</dd>
              <dt>Ingresos ya retirados</dt>
              <dd>{eth(q.data.withdrawn_earnings_wei)}</dd>
              <dt>Consumo compensado</dt>
              <dd>{kwh(q.data.retired_wh)}</dd>
              <dt>Bloque de referencia</dt>
              <dd>{q.data.block_number}</dd>
            </dl>
          </>
        )}
      </QueryState>
    </Card>
  );
}
export default function SettlementPage() {
  const { id, community } = useCommunity();
  const [offset, setOffset] = useState(0),
    [status, setStatus] = useState("");
  const batches = useApi<BatchView[]>(
      `${communityPath(id)}/settlements?limit=20&offset=${offset}${status ? `&status=${status}` : ""}`,
      !!id,
      true,
    ),
    roles = useRoles(),
    policy = useApi<Policy>(`${communityPath(id)}/settlement-policy`, !!id);
  const calculate = useAction<BatchView>(
    `${communityPath(id)}/settlements/calculate`,
  );
  return (
    <Page
      title="Liquidación comunitaria"
      description="La asignación distribuye energía; la liquidación paga obligaciones; el retiro SUN compensa consumo."
    >
      {!id ? (
        <Card>
          <Empty title="Selecciona una comunidad autorizada" />
        </Card>
      ) : (
        <>
          <div className="toolbar">
            <div>
              <strong>{community?.name}</strong>
              <p>
                {community?.interval_seconds
                  ? `${community.interval_seconds / 60} min por intervalo`
                  : ""}{" "}
                ·{" "}
                {policy.data
                  ? `${eth(policy.data.price_wei_per_kwh)}/kWh`
                  : "Precio no disponible"}
              </p>
            </div>
            <Field label="Estado">
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">Todos</option>
                {[
                  "PREPARED",
                  "SUBMITTED",
                  "CHALLENGEABLE",
                  "FINALIZED",
                  "RECONCILIATION_REQUIRED",
                  "REJECTED",
                ].map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Statement />
          <Card title="Intervalos de la comunidad">
            <QueryState query={batches}>
              {batches.data?.length ? (
                <div className="table-wrap">
                  <table>
                    <caption>
                      Historial comunitario; las asignaciones personales se
                      consultan dentro de cada intervalo.
                    </caption>
                    <thead>
                      <tr>
                        <th>Intervalo</th>
                        <th>Inyección</th>
                        <th>Consumo elegible</th>
                        <th>Asignada</th>
                        <th>No asignada</th>
                        <th>Sin compensar</th>
                        <th>Total ETH</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batches.data.map((b) => (
                        <tr key={b.id}>
                          <td>
                            <Link to={`/liquidacion/${b.id}`}>
                              {date(b.interval_start)}
                            </Link>
                          </td>
                          <td>{kwh(b.injection_wh)}</td>
                          <td>{kwh(b.consumption_wh)}</td>
                          <td>{kwh(b.allocated_wh)}</td>
                          <td>{kwh(b.unallocated_wh)}</td>
                          <td>{kwh(b.uncompensated_wh)}</td>
                          <td>{eth(b.total_due_wei)}</td>
                          <td>
                            <Badge value={b.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="Sin intervalos de liquidación" />
              )}
            </QueryState>
            <div className="pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset((v) => Math.max(0, v - 20))}
              >
                Anterior
              </button>
              <span>Página {offset / 20 + 1}</span>
              <button
                disabled={(batches.data?.length ?? 0) < 20}
                onClick={() => setOffset((v) => v + 20)}
              >
                Siguiente
              </button>
            </div>
          </Card>
          {roles.data?.operator && (
            <Card title="Operación de liquidación">
              <Form
                onSubmit={async (data) => {
                  try {
                    await calculate.mutateAsync({
                      interval_start: new Date(
                        String(data.get("start")) + "Z",
                      ).toISOString(),
                    });
                  } catch {
                    /* mutation error shown */
                  }
                }}
              >
                <Field
                  label="Inicio de intervalo (UTC)"
                  hint="Debe coincidir con el límite de la política y terminar antes del margen de verificación."
                >
                  <input name="start" type="datetime-local" required />
                </Field>
                <button className="primary" disabled={calculate.isPending}>
                  Calcular intervalo verificado
                </button>
                {calculate.error && (
                  <Notice tone="warning">
                    {errorMessage(calculate.error)}
                  </Notice>
                )}
                {calculate.data && (
                  <Link to={`/liquidacion/${calculate.data.id}`}>
                    Ver lote preparado
                  </Link>
                )}
              </Form>
            </Card>
          )}
          <Notice>
            Los contratos evitan pagos duplicados. El marketplace nativo no está
            habilitado en este despliegue. La compensación SUN no genera un
            segundo pago ETH.
          </Notice>
        </>
      )}
    </Page>
  );
}
function Funding({ allocation }: { allocation: AllocationView }) {
  const { id } = useCommunity();
  const [open, setOpen] = useState(false);
  const q = useApi<FundingView>(
    `${communityPath(id)}/allocations/${allocation.id}/funding`,
    open,
  );
  return (
    <>
      <button className="text-button" onClick={() => setOpen(!open)}>
        {open ? "Ocultar" : "Ver fondos"}
      </button>
      {open && (
        <QueryState query={q}>
          {q.data && (
            <dl className="detail-list">
              <dt>Estado</dt>
              <dd>
                <Badge value={q.data.status} />
              </dd>
              <dt>Obligación</dt>
              <dd>{eth(q.data.due_wei)}</dd>
              <dt>ETH disponible propio</dt>
              <dd>{eth(q.data.available_wei)}</dd>
              <dt>SUN requeridos (unidades base)</dt>
              <dd>{q.data.required_sun_units}</dd>
              <dt>Bloque confirmado</dt>
              <dd>{q.data.confirmed_block ?? "—"}</dd>
            </dl>
          )}
        </QueryState>
      )}
    </>
  );
}
function OperatorJobs({ batch }: { batch: BatchView }) {
  const { id } = useCommunity(),
    roles = useRoles();
  const q = useApi<Operation[]>(
    `${communityPath(id)}/settlements/${batch.id}/operations`,
    !!roles.data?.operator,
    true,
  );
  const reconcile = useAction(
    `${communityPath(id)}/settlements/${batch.id}/reconcile`,
  );
  const [error, setError] = useState("");
  if (!roles.data?.operator) return null;
  async function retry(job: string) {
    try {
      await api(
        `${communityPath(id)}/settlements/${batch.id}/jobs/${job}/retry`,
        { method: "POST" },
      );
      await q.refetch();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  return (
    <Card title="Operaciones del lote · operador">
      <button
        onClick={() => reconcile.mutate({})}
        disabled={reconcile.isPending}
      >
        Conciliar estado con la cadena
      </button>
      {(error || reconcile.error) && (
        <Notice tone="warning">{error || errorMessage(reconcile.error)}</Notice>
      )}
      <QueryState query={q}>
        {q.data?.length ? (
          <ul className="plain-list">
            {q.data.map((job) => (
              <li key={job.job_id}>
                <div>
                  <strong>{job.action}</strong>
                  <p>
                    {job.attempts} intentos ·{" "}
                    {job.last_error ?? "Sin error reportado"}
                  </p>
                  {job.transaction_hash && (
                    <Hash value={job.transaction_hash} />
                  )}
                </div>
                <Badge value={job.status} />
                {job.status === "FAILED" && (
                  <button onClick={() => void retry(job.job_id)}>
                    Reintentar
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="Sin operaciones en cola" />
        )}
      </QueryState>
    </Card>
  );
}
export function SettlementDetail() {
  const { batchId } = useParams(),
    { id } = useCommunity();
  const base = `${communityPath(id)}/settlements/${batchId}`;
  const batch = useApi<BatchView>(base, !!id && !!batchId, true);
  const [offset, setOffset] = useState(0),
    [claimOffset, setClaimOffset] = useState(0);
  const allocations = useApi<AllocationView[]>(
      `${base}/allocations?limit=20&offset=${offset}`,
      !!id && !!batchId,
      true,
    ),
    claims = useApi<ClaimView[]>(
      `${base}/claims?limit=20&offset=${claimOffset}`,
      !!id && !!batchId,
    );
  return (
    <Page
      title="Detalle del intervalo"
      description="Compromisos inmutables, asignaciones personales y estado de liquidación."
      action={
        <Link className="button" to="/liquidacion">
          ← Volver
        </Link>
      }
    >
      <QueryState query={batch}>
        {batch.data && (
          <>
            <Card
              title={`${date(batch.data.interval_start)} — ${date(batch.data.interval_end)}`}
            >
              <Badge value={batch.data.status} />
              {batch.data.status === "CHALLENGEABLE" && (
                <Notice>
                  Pendiente de aprobación de gobernanza. Una vez vencido el
                  período de revisión, la wallet autorizada puede{" "}
                  <Link to={`/gobernanza?action=finalize_batch&batch=${batch.data.id}`}>
                    preparar la finalización del lote
                  </Link>
                  . La emisión SUN se tramita después de finalizarlo.
                </Notice>
              )}
              <div className="metrics">
                <Metric
                  label="Inyección verificada"
                  value={kwh(batch.data.injection_wh)}
                />
                <Metric
                  label="Consumo elegible"
                  value={kwh(batch.data.consumption_wh)}
                  tone="blue"
                />
                <Metric
                  label="Energía asignada"
                  value={kwh(batch.data.allocated_wh)}
                />
                <Metric
                  label="Obligación total"
                  value={eth(batch.data.total_due_wei)}
                  tone="amber"
                />
              </div>
              <dl className="detail-list">
                <dt>Lote</dt>
                <dd>
                  <code>{batch.data.id}</code>
                </dd>
                <dt>Referencia en cadena</dt>
                <dd>
                  <code>{batch.data.chain_batch_id}</code>
                </dd>
                <dt>Versión de política</dt>
                <dd>
                  <code>{batch.data.policy_id}</code>
                </dd>
                <dt>Raíz de evidencia</dt>
                <dd>
                  <code>{batch.data.root}</code>
                </dd>
              </dl>
            </Card>
            <Card title="Mis asignaciones">
              <QueryState query={allocations}>
                {allocations.data?.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Asignación</th>
                          <th>Productor / consumidor</th>
                          <th>Energía</th>
                          <th>Obligación</th>
                          <th>Liquidación</th>
                          <th>Financiación</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allocations.data.map((a) => (
                          <tr key={a.id}>
                            <td>
                              <code>{a.id}</code>
                              <details>
                                <summary>Prueba Merkle</summary>
                                <pre>{JSON.stringify(a.proof, null, 2)}</pre>
                              </details>
                            </td>
                            <td>
                              <code>{a.producer_id}</code>
                              <br />
                              <code>{a.consumer_id}</code>
                            </td>
                            <td>{kwh(a.energy_wh)}</td>
                            <td>{eth(a.due_wei)}</td>
                            <td>
                              <Badge value={a.status} />
                            </td>
                            <td>
                              <Badge value={a.funding_status} />
                              <Funding allocation={a} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty title="Sin asignaciones personales en este intervalo" />
                )}
              </QueryState>
              <div className="pagination">
                <button
                  disabled={!offset}
                  onClick={() => setOffset((v) => Math.max(0, v - 20))}
                >
                  Anterior
                </button>
                <button
                  disabled={(allocations.data?.length ?? 0) < 20}
                  onClick={() => setOffset((v) => v + 20)}
                >
                  Siguiente
                </button>
              </div>
            </Card>
            <Card title="Mis evidencias de inyección y consumo">
              <QueryState query={claims}>
                {claims.data?.length ? (
                  <ul className="plain-list">
                    {claims.data.map((c) => (
                      <li key={c.id}>
                        <div>
                          <h3>
                            {c.kind === 0 ? "Inyección" : "Consumo"} ·{" "}
                            {kwh(c.energy_wh)}
                          </h3>
                          <p>
                            Nodo <code>{c.node_id}</code>
                          </p>
                          <p>
                            Medidor <code>{c.meter_id}</code>
                          </p>
                          <small>Claim: {c.chain_claim_id}</small>
                        </div>
                        <Badge value={c.status} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Empty title="Sin claims personales" />
                )}
              </QueryState>
              <Pagination
                label="Páginas de evidencia"
                offset={claimOffset}
                count={claims.data?.length ?? 0}
                onChange={setClaimOffset}
              />
              <Notice>
                El API permite ver tus referencias y pruebas Merkle. No publica
                el manifiesto completo, las mediciones de otros participantes ni
                un vínculo individual de origen para cada SUN fungible.
              </Notice>
            </Card>
            <OperatorJobs batch={batch.data} />
          </>
        )}
      </QueryState>
    </Page>
  );
}
