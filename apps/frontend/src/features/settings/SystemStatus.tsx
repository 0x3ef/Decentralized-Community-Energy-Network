import { useApi, useCommunity } from "../../shared/api/hooks";
import { useRoles } from "../../shared/blockchain/WalletProvider";
import { communityPath } from "../../shared/api/client";
import { Card, QueryState, Notice } from "../../shared/ui/components";
interface System {
  status: string;
  components: Record<
    string,
    {
      state: string;
      age_seconds?: number;
      block_number?: number;
      persisted?: number;
      duplicates?: number;
      rejected?: number;
      queue_depth?: number;
    }
  >;
}
interface Operations extends System {
  indexed_block: number | null;
  confirmed_block: number | null;
  lag_blocks: number | null;
  alerts: string[];
  batches: Record<string, number>;
  jobs: Record<string, number>;
  telemetry_quality: Record<string, number>;
}
const labels: Record<string, string> = {
  database: "Base de datos",
  redis: "Cola y sesiones",
  blockchain: "RPC y confirmaciones",
  worker: "Procesador de energía y liquidación",
  subscriber: "Ingesta MQTT",
};
const states: Record<string, string> = {
  ready: "Disponible",
  degraded: "Con incidencias",
  missing: "Sin señal",
  stale: "Señal desactualizada",
  unavailable: "No disponible",
  wrong_chain: "Red incorrecta",
};
export function SystemStatus() {
  const status = useApi<System>("/system/status", true, true),
    { id } = useCommunity(),
    roles = useRoles();
  const operations = useApi<Operations>(
    `${communityPath(id)}/operations/status`,
    !!id && !!roles.data?.operator,
    true,
  );
  return (
    <>
      <Card title="Estado del sistema">
        <QueryState query={status}>
          {status.data && (
            <>
              <dl className="detail-list">
                {Object.entries(status.data.components).map(([key, value]) => (
                  <div className="contents" key={key}>
                    <dt>{labels[key] ?? key}</dt>
                    <dd>
                      {states[value.state] ?? value.state}
                      {value.age_seconds != null
                        ? ` · ${value.age_seconds} s`
                        : ""}
                    </dd>
                  </div>
                ))}
              </dl>
              {status.data.status !== "ready" && (
                <Notice tone="warning">
                  Hay servicios pendientes o degradados. La disponibilidad de la
                  interfaz no confirma una liquidación en cadena.
                </Notice>
              )}
            </>
          )}
        </QueryState>
      </Card>
      {roles.data?.operator && (
        <Card title="Observabilidad de la comunidad · operador">
          <QueryState query={operations}>
            {operations.data && (
              <>
                <dl className="detail-list">
                  <dt>Bloque indexado</dt>
                  <dd>{operations.data.indexed_block ?? "—"}</dd>
                  <dt>Bloque confirmado</dt>
                  <dd>{operations.data.confirmed_block ?? "—"}</dd>
                  <dt>Retraso de indexación</dt>
                  <dd>{operations.data.lag_blocks ?? "—"} bloques</dd>
                </dl>
                {operations.data.alerts.length > 0 && (
                  <Notice tone="warning">
                    Alertas: {operations.data.alerts.join(", ")}. Revisa las
                    operaciones del lote antes de reintentar.
                  </Notice>
                )}
                <details>
                  <summary>Contadores de calidad, lotes y trabajos</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        calidad: operations.data.telemetry_quality,
                        lotes: operations.data.batches,
                        trabajos: operations.data.jobs,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </>
            )}
          </QueryState>
        </Card>
      )}
    </>
  );
}
