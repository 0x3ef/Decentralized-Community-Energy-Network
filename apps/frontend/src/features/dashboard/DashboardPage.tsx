import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Activity, Wallet, Leaf } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { useHomeSelection, useIntervals } from "../energy/hooks";
const EnergyChart = lazy(() =>
  import("../energy/EnergyChart").then((module) => ({
    default: module.EnergyChart,
  })),
);
import { useCommunity, useNativeWallet, useApi } from "../../shared/api/hooks";
import { communityPath } from "../../shared/api/client";
import type { ParticipantStatement, BatchView } from "../../shared/api/models";
import {
  Page,
  Card,
  Metric,
  QueryState,
  Empty,
  Badge,
  Notice,
} from "../../shared/ui/components";
import { eth, kwh, units, date } from "../../shared/utils/format";

export default function DashboardPage() {
  const { user } = useAuth(),
    { community, id } = useCommunity(),
    { home, homes } = useHomeSelection(),
    intervals = useIntervals(home?.id),
    native = useNativeWallet(),
    statement = useApi<ParticipantStatement>(
      `${communityPath(id)}/settlement-statement`,
      !!id,
      true,
    ),
    batches = useApi<BatchView[]>(
      `${communityPath(id)}/settlements?limit=5&offset=0`,
      !!id,
    );
  const total = (
    key: "generation_wh" | "consumption_wh" | "eligible_export_wh",
  ) =>
    intervals.data?.length
      ? intervals.data.reduce((sum, interval) => sum + interval[key], 0)
      : undefined;
  return (
    <Page
      title={`Hola, ${user?.first_name ?? "bienvenido"}`}
      description={
        [community?.name, home?.name].filter(Boolean).join(" · ") ||
        "Selecciona una comunidad para consultar tu actividad."
      }
      action={
        <Link className="button" to="/energia">
          Ver energía <ArrowUpRight size={16} />
        </Link>
      }
    >
      <div className="section-heading">
        <h2>Energía de tu hogar</h2>
        <span className="fine-print">Últimas 24 horas</span>
      </div>
      <QueryState query={homes}>
        {home ? (
          <QueryState query={intervals}>
            <div className="metrics energy-metrics">
              <Metric
                label="Generación solar"
                value={kwh(total("generation_wh"))}
                hint="Energía producida"
                tone="amber"
              />
              <Metric
                label="Consumo"
                value={kwh(total("consumption_wh"))}
                hint="Energía utilizada en el hogar"
                tone="blue"
              />
              <Metric
                label="Exportación elegible"
                value={kwh(total("eligible_export_wh"))}
                hint="La emisión de SUN requiere aprobar el lote"
              />
            </div>
          </QueryState>
        ) : (
          <Notice>
            <Link to="/hogares">Registra un hogar</Link> para consultar sus
            mediciones.
          </Notice>
        )}
      </QueryState>
      <div className="overview-layout">
        <Card title="Generación y consumo">
          <div className="chart-meta">
            <span>
              <i className="legend-dot amber" />
              Generación
            </span>
            <span>
              <i className="legend-dot blue" />
              Consumo
            </span>
            <small>kWh por intervalo</small>
          </div>
          {home ? (
            <QueryState query={intervals}>
              <Suspense
                fallback={
                  <div className="loading" role="status">
                    Cargando gráfica…
                  </div>
                }
              >
                <EnergyChart intervals={intervals.data ?? []} />
              </Suspense>
            </QueryState>
          ) : (
            <Empty title="Sin mediciones" />
          )}
        </Card>
        <Card title="Tus fondos" className="funds-summary">
          {id ? (
            <QueryState query={native}>
              <dl className="balance-list">
                <div>
                  <dt>SUN en wallet</dt>
                  <dd>
                    {native.data ? `${units(native.data.sun_units)} SUN` : "—"}
                  </dd>
                </div>
                <div>
                  <dt>ETH disponible en depósito</dt>
                  <dd>{eth(native.data?.available_wei)}</dd>
                </div>
                <div>
                  <dt>Ingresos por retirar</dt>
                  <dd>{eth(native.data?.earnings_wei)}</dd>
                </div>
              </dl>
            </QueryState>
          ) : (
            <Empty title="Selecciona una comunidad" />
          )}
          <Link className="button primary" to="/depositos">
            <Wallet size={16} />
            Gestionar fondos
          </Link>
          <p className="fine-print">
            Los SUN representan energía. Los pagos se liquidan en ETH.
          </p>
        </Card>
      </div>
      <div className="two-col">
        <Card title="Liquidaciones recientes">
          {id ? (
            <QueryState query={batches}>
              {batches.data?.length ? (
                <ul className="plain-list">
                  {batches.data.map((batch) => (
                    <li key={batch.id}>
                      <Activity size={16} />
                      <div>
                        <Link to={`/liquidacion/${batch.id}`}>
                          {date(batch.interval_start)}
                        </Link>
                        <p>
                          {kwh(batch.allocated_wh)} asignados ·{" "}
                          {eth(batch.total_due_wei)}
                        </p>
                      </div>
                      <Badge value={batch.status} />
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="Aún no hay liquidaciones" />
              )}
            </QueryState>
          ) : (
            <Empty title="Selecciona una comunidad" />
          )}
          <Link className="section-link" to="/liquidacion">
            Ver liquidación <ArrowUpRight size={14} />
          </Link>
        </Card>
        <Card title="Consumo y compensación">
          {id ? (
            <QueryState query={statement}>
              <dl className="balance-list">
                <div>
                  <dt>Consumo compensado</dt>
                  <dd>{kwh(statement.data?.retired_wh)}</dd>
                </div>
                <div>
                  <dt>Obligación pendiente</dt>
                  <dd>{eth(statement.data?.unsettled_due_wei)}</dd>
                </div>
              </dl>
            </QueryState>
          ) : (
            <Empty title="Selecciona una comunidad" />
          )}
          <p className="fine-print">
            Una vez liquidada la asignación, puedes usar SUN para compensar
            consumo elegible.
          </p>
          <Link className="section-link" to="/compensacion">
            <Leaf size={15} />
            Compensar consumo <ArrowUpRight size={14} />
          </Link>
        </Card>
      </div>
    </Page>
  );
}
