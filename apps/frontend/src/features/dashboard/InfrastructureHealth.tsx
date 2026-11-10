import { useDevices, useApi } from "../../shared/api/hooks";
import type { Device, Health } from "../../shared/api/models";
import { Card, QueryState, Empty, Badge } from "../../shared/ui/components";
import { date } from "../../shared/utils/format";
function MeterHealth({ device }: { device: Device }) {
  const health = useApi<Health>(`/iot/devices/${device.id}/health`, true, true);
  return (
    <li>
      <div>
        <strong>{device.device_code}</strong>
        <p>
          {health.data
            ? `${health.data.online ? "En línea" : "Sin señal reciente"} · ${date(health.data.last_authenticated_telemetry)}`
            : "Estado no disponible"}
        </p>
      </div>
      <Badge value={device.telemetry_source} />
      <Badge value={device.status} />
    </li>
  );
}
export function InfrastructureHealth({ homeId }: { homeId?: string }) {
  const devices = useDevices(homeId);
  return (
    <Card title="Infraestructura de tu hogar">
      {homeId ? (
        <QueryState query={devices}>
          {devices.data?.devices.length ? (
            <ul className="plain-list">
              {devices.data.devices.map((device) => (
                <MeterHealth key={device.id} device={device} />
              ))}
            </ul>
          ) : (
            <Empty title="Sin dispositivos conectados" />
          )}
        </QueryState>
      ) : (
        <Empty title="Registra un hogar para consultar medidores" />
      )}
    </Card>
  );
}
