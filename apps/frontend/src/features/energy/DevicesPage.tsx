import { NodeOperations } from "./NodeOperations";
import {
  measurementValue,
  measurementIsStale,
} from "../../shared/utils/telemetry";
import { useState } from "react";
import { Radio, Plus, Wifi, WifiOff } from "lucide-react";
import { useHomeSelection } from "./hooks";
import {
  useApi,
  useDevices,
  useCommunity,
  useAction,
} from "../../shared/api/hooks";
import type { Health, Device, Node } from "../../shared/api/models";
import { useRoles } from "../../shared/blockchain/WalletProvider";
import { communityPath } from "../../shared/api/client";
import {
  Page,
  Card,
  QueryState,
  Empty,
  Badge,
  Notice,
  Field,
  Form,
  Metric,
} from "../../shared/ui/components";
import { date, errorMessage } from "../../shared/utils/format";
import { DeviceRegistration } from "../homes/HomesPage";
function DeviceDetails({ device }: { device: Device }) {
  const health = useApi<Health>(`/iot/devices/${device.id}/health`, true, true);
  const quality = useApi<
    Array<{
      id: string;
      state: string;
      reason: string;
      occurrences: number;
      last_seen: string;
    }>
  >(`/iot/devices/${device.id}/quality?limit=10&offset=0`);
  const telemetry = useApi<
    Array<{
      id: string;
      received_at: string;
      measured_at: string;
      payload: Record<string, unknown>;
    }>
  >(`/communities/meters/${device.id}/telemetry?limit=5&offset=0`, true, true);
  const latest = telemetry.data?.[0];
  const value = (key: string, unit: string) => {
    const amount = measurementValue(latest?.payload, key);
    return amount === "—" ? "—" : `${amount} ${unit}`;
  };
  return (
    <>
      <Card title="Última lectura · potencia instantánea">
        <div className="metrics">
          <Metric
            label="Carga del hogar"
            value={value("consumption_power_w", "W")}
            tone="blue"
          />
          <Metric
            label="Intercambio neto de red"
            value={value("active_power_w", "W")}
            tone="blue"
          />
          <Metric
            label="Importación / exportación"
            value={`${value("grid_import_power_w", "W")} / ${value("grid_export_power_w", "W")}`}
          />
          <Metric
            label="Estado de batería"
            value={value("state_of_charge_pct", "%")}
            tone="amber"
          />
        </div>
        <p className="fine-print">
          Medida: {date(latest?.measured_at)} · Fuente:{" "}
          {device.telemetry_source}. La producción del inversor se consulta en
          su propio dispositivo.
        </p>
        {measurementIsStale(latest?.measured_at) && (
          <Notice tone="warning">
            Última lectura histórica o no disponible. No representa el estado
            actual del hogar.
          </Notice>
        )}
      </Card>
      <div className="two-col">
        <Card title="Salud del medidor">
          <QueryState query={health}>
            {health.data && (
              <>
                <div className="device-title">
                  {health.data.online ? (
                    <Wifi className="text-emerald-600" />
                  ) : (
                    <WifiOff />
                  )}
                  <h3>
                    {health.data.online ? "En línea" : "Sin señal reciente"}
                  </h3>
                  <Badge value={health.data.source} />
                </div>
                <dl className="detail-list">
                  <dt>Estado del dispositivo</dt>
                  <dd>
                    <Badge value={health.data.device_status} />
                  </dd>
                  <dt>Última telemetría autenticada</dt>
                  <dd>{date(health.data.last_authenticated_telemetry)}</dd>
                  <dt>Calidad más reciente</dt>
                  <dd>{health.data.last_quality ?? "Sin evaluación"}</dd>
                  <dt>Latencia</dt>
                  <dd>
                    {health.data.latency_seconds == null
                      ? "—"
                      : `${health.data.latency_seconds} s`}
                  </dd>
                </dl>
                {!health.data.online && (
                  <Notice tone="warning">
                    La información puede estar desactualizada. Una lectura
                    antigua no representa potencia actual.
                  </Notice>
                )}
              </>
            )}
          </QueryState>
        </Card>
        <Card title="Evaluaciones de calidad">
          <QueryState query={quality}>
            {quality.data?.length ? (
              <ul className="plain-list">
                {quality.data.map((q) => (
                  <li key={q.id}>
                    <Badge value={q.state} />
                    <div>
                      <p>{q.reason}</p>
                      <small>
                        {q.occurrences} ocurrencias · {date(q.last_seen)}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="Sin evaluaciones" />
            )}
          </QueryState>
        </Card>
      </div>
      <Card title="Últimas mediciones · evidencia original">
        <QueryState query={telemetry}>
          {telemetry.data?.length ? (
            telemetry.data.map((item) => (
              <details key={item.id}>
                <summary>
                  {date(item.received_at)} · {item.id}
                </summary>
                <pre>{JSON.stringify(item.payload, null, 2)}</pre>
              </details>
            ))
          ) : (
            <Empty title="Sin telemetría recibida" />
          )}
        </QueryState>
        <p className="fine-print">
          La potencia instantánea se expresa en W; los contadores acumulados en
          kWh. El consumo del hogar es distinto del intercambio neto con la red.
          Las fuentes simuladas no representan mediciones físicas.
        </p>
      </Card>
    </>
  );
}
export default function DevicesPage() {
  const { homes, home, select } = useHomeSelection(),
    devices = useDevices(home?.id);
  const [chosen, setChosen] = useState(""),
    [create, setCreate] = useState(false);
  const device =
    devices.data?.devices.find((d) => d.id === chosen) ??
    devices.data?.devices[0];
  const { id } = useCommunity(),
    roles = useRoles(),
    nodes = useApi<Node[]>(`${communityPath(id)}/nodes`, !!id);
  const node = useAction(`${communityPath(id)}/nodes`);
  return (
    <Page
      title="Nodos y medidores"
      description="Infraestructura identificada, fuentes visibles y calidad de medición auditable."
      action={
        <button
          disabled={!home}
          className="primary"
          onClick={() => setCreate(!create)}
        >
          <Plus size={17} /> Registrar dispositivo
        </button>
      }
    >
      <QueryState query={homes}>
        <div className="toolbar">
          <Field label="Hogar">
            <select
              value={home?.id ?? ""}
              onChange={(e) => {
                select(e.target.value);
                setChosen("");
              }}
            >
              <option value="" disabled>
                Selecciona un hogar
              </option>
              {homes.data?.homes.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </QueryState>
      {create && home && (
        <DeviceRegistration
          homeId={home.id}
          onDone={() => {
            setCreate(false);
            void devices.refetch();
          }}
        />
      )}
      {home ? (
        <QueryState query={devices}>
          {devices.data?.devices.length ? (
            <>
              <div className="device-tabs">
                {devices.data.devices.map((d) => (
                  <button
                    key={d.id}
                    className={d.id === device?.id ? "selected" : ""}
                    onClick={() => setChosen(d.id)}
                  >
                    <Radio size={17} />
                    {d.device_code}
                    <Badge value={d.status} />
                  </button>
                ))}
              </div>
              {device && <DeviceDetails key={device.id} device={device} />}
            </>
          ) : (
            <Card>
              <Empty title="Conecta tu primer medidor">
                Registra un dispositivo y solicita su autorización a la
                comunidad.
              </Empty>
            </Card>
          )}
        </QueryState>
      ) : (
        <Card>
          <Empty title="Registra un hogar primero" />
        </Card>
      )}
      {roles.data?.operator && id && (
        <Card title="Registro operativo de nodo">
          <Form
            onSubmit={async () => {
              try {
                await node.mutateAsync({ home_id: home?.id });
                await nodes.refetch();
              } catch {
                /* mutation error is rendered below */
              }
            }}
          >
            <p>
              Un nodo referencia un hogar. Su creación no autoriza sus
              medidores.
            </p>
            <button disabled={!home || node.isPending}>
              Proponer nodo para {home?.name}
            </button>
            {node.error && (
              <Notice tone="warning">{errorMessage(node.error)}</Notice>
            )}
          </Form>
        </Card>
      )}
      {roles.data?.operator && id && <NodeOperations />}
    </Page>
  );
}
