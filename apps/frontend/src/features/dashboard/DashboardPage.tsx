import { InfrastructureHealth } from "./InfrastructureHealth";
import {
  ContributionChart,
  AllocationHistory,
} from "../energy/ContributionChart";
import { Link } from "react-router-dom";
import { Sun, ArrowUpRight, ShieldCheck, House, Activity } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { useHomeSelection, useIntervals } from "../energy/hooks";
import { EnergyChart } from "../energy/EnergyChart";
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
  const totals = (
    key:
      | "generation_wh"
      | "consumption_wh"
      | "eligible_export_wh"
      | "grid_import_wh",
  ) =>
    intervals.data?.length
      ? intervals.data.reduce((a, b) => a + b[key], 0)
      : undefined;
  return (
    <Page
      title={`Tu energía, ${user?.first_name ?? "en comunidad"}`}
      description="Una visión clara de tu hogar y del valor que compartes con tu comunidad."
    >
      <section className="welcome-banner">
        <div>
          <span className="banner-tag">
            <span className="live-dot" /> ENERGÍA CON PROPÓSITO
          </span>
          <h2>
            Cada kilovatio cuenta.
            <br />
            Cada aporte conecta.
          </h2>
          <p>
            {community
              ? `${community.name} · ${home?.name ?? "Conecta tu hogar para empezar"}`
              : "Forma parte de una comunidad que transforma energía en impacto."}
          </p>
          <Link className="banner-link" to="/comunidad">
            Explorar mi comunidad <ArrowUpRight size={17} />
          </Link>
        </div>
        <div className="sun-illustration" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <Sun size={72} />
          <span className="energy-chip">
            <ShieldCheck size={16} /> Energía verificable
          </span>
        </div>
      </section>
      <div className="section-heading">
        <h2>Tu energía · últimas 24 horas</h2>
        <Link to="/energia">
          Ver monitoreo <ArrowUpRight size={14} />
        </Link>
      </div>
      <QueryState query={homes}>
        {home ? (
          <QueryState query={intervals}>
            <div className="metrics">
              <Metric
                label="Generación solar"
                value={kwh(totals("generation_wh"))}
                hint={home.name}
                tone="amber"
              />
              <Metric
                label="Consumo del hogar"
                value={kwh(totals("consumption_wh"))}
                hint="Carga total del hogar"
                tone="blue"
              />
              <Metric
                label="Exportación verificada elegible"
                value={kwh(totals("eligible_export_wh"))}
                hint="No equivale a SUN emitidos; consulta Créditos y Liquidación"
              />
              <Metric
                label="Energía importada"
                value={kwh(totals("grid_import_wh"))}
                hint="Desde la red eléctrica"
                tone="blue"
              />
            </div>
          </QueryState>
        ) : (
          <Notice>
            Registra tu primer hogar para comenzar a ver mediciones.{" "}
            <Link to="/hogares">Registrar hogar →</Link>
          </Notice>
        )}
      </QueryState>
      <div className="dashboard-columns">
        <Card title="Generación y consumo">
          <div className="chart-meta">
            <span>
              <i className="legend-dot amber" /> Generación solar
            </span>
            <span>
              <i className="legend-dot blue" /> Consumo del hogar
            </span>
            <small>kWh por intervalo</small>
          </div>
          {home ? (
            <QueryState query={intervals}>
              <EnergyChart intervals={intervals.data ?? []} />
            </QueryState>
          ) : (
            <Empty title="Tu energía aparecerá aquí">
              La gráfica se completa con mediciones verificables de tu hogar.
            </Empty>
          )}
        </Card>
        <Card title="Mi comunidad" className="community-summary">
          <div className="card-icon">
            <House />
          </div>
          <h3>{community?.name ?? "Tu próxima conexión"}</h3>
          {community ? (
            <>
              <Badge value={community.status} />
              <p>{community.boundary_description}</p>
              <dl className="detail-list">
                <dt>Periodo de liquidación</dt>
                <dd>{community.interval_seconds / 60} min</dd>
                <dt>Crédito energético</dt>
                <dd>1 SUN = 1 kWh</dd>
              </dl>
            </>
          ) : (
            <p>
              Conecta hogares, infraestructura y personas para compartir energía
              con reglas transparentes.
            </p>
          )}
          <Link className="button" to="/comunidad">
            Ver comunidad <ArrowUpRight size={15} />
          </Link>
        </Card>
      </div>
      <div className="section-heading">
        <h2>Tu participación en el protocolo</h2>
        <span className="fine-print">
          Balances confirmados · activos de prueba
        </span>
      </div>
      {id ? (
        <>
          <div className="metrics">
            <Metric
              label="SUN en tu wallet"
              value={native.data ? `${units(native.data.sun_units)} SUN` : "—"}
              hint="Créditos de energía elegible"
            />
            <Metric
              label="Consumo compensado"
              value={kwh(statement.data?.retired_wh)}
              hint="SUN retirados de circulación"
            />
            <Metric
              label="Obligación pendiente"
              value={eth(statement.data?.unsettled_due_wei)}
              hint="Asignaciones pendientes de liquidación"
              tone="blue"
            />
            <Metric
              label="Ingresos por retirar"
              value={eth(statement.data?.claimable_wei)}
              hint="Compensación confirmada del productor"
              tone="amber"
            />
          </div>
          {(native.isError || statement.isError) && (
            <Notice>
              Algunos balances no están disponibles. Conecta y verifica una
              wallet en una comunidad con contratos desplegados.
            </Notice>
          )}
        </>
      ) : (
        <Notice>
          Los balances y la liquidación estarán disponibles al pertenecer a una
          comunidad autorizada.
        </Notice>
      )}
      <div className="two-col">
        <Card title="Actividad de liquidación">
          {id ? (
            <QueryState query={batches}>
              {batches.data?.length ? (
                <ul className="plain-list">
                  {batches.data.map((batch) => (
                    <li key={batch.id}>
                      <Activity size={18} />
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
            <Empty title="Tu actividad se registrará aquí" />
          )}
        </Card>
        <Card title="Una energía, tres procesos">
          <ol className="steps">
            <li>
              <span>01</span>
              <div>
                <h3>Medir y verificar</h3>
                <p>
                  La infraestructura registra inyección y consumo elegibles.
                </p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <h3>Asignar y liquidar</h3>
                <p>
                  El protocolo distribuye energía y liquida obligaciones en ETH.
                </p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <h3>Compensar con SUN</h3>
                <p>
                  Retira créditos contra consumo entregado elegible, sin un
                  segundo pago.
                </p>
              </div>
            </li>
          </ol>
        </Card>
      </div>
      <InfrastructureHealth homeId={home?.id} />
      <div className="two-col">
        <Card title="Tu contribución por intervalo · kWh">
          <ContributionChart intervals={intervals.data ?? []} />
        </Card>
        <Card title="Historial de asignación comunitaria · últimos 5 lotes">
          {id ? (
            <QueryState query={batches}>
              <AllocationHistory batches={batches.data ?? []} />
            </QueryState>
          ) : (
            <Empty title="Selecciona una comunidad" />
          )}
        </Card>
      </div>
    </Page>
  );
}
