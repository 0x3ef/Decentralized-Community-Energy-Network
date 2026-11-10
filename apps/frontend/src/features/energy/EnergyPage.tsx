import { useState } from "react";
import { useHomeSelection, useIntervals } from "./hooks";
import { EnergyChart } from "./EnergyChart";
import {
  Page,
  Card,
  Metric,
  Field,
  QueryState,
  Badge,
  Notice,
} from "../../shared/ui/components";
import { kwh, date } from "../../shared/utils/format";
export default function EnergyPage() {
  const { home, homes, select } = useHomeSelection();
  const [days, setDays] = useState(1);
  const intervals = useIntervals(home?.id, days);
  const values = intervals.data;
  const sum = (
    key:
      | "generation_wh"
      | "consumption_wh"
      | "grid_import_wh"
      | "grid_export_wh"
      | "eligible_export_wh",
  ) =>
    values?.length
      ? values.reduce((total, row) => total + row[key], 0)
      : undefined;
  return (
    <Page
      title="Monitoreo energético"
      description="Del panel a la comunidad: energía por intervalo, con su calidad y evidencia."
    >
      <div className="toolbar">
        <Field label="Hogar">
          <select
            value={home?.id ?? ""}
            onChange={(e) => select(e.target.value)}
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
        <Field label="Periodo">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={1}>Últimas 24 horas</option>
            <option value={7}>Últimos 7 días</option>
            <option value={30}>Últimos 30 días</option>
          </select>
        </Field>
        <span className="fine-print">Hora de Colombia · America/Bogota</span>
      </div>
      {!home && (
        <Notice>Registra un hogar para consultar sus mediciones.</Notice>
      )}
      {home && (
        <QueryState query={intervals}>
          <div className="metrics">
            <Metric
              label="Generación solar"
              value={kwh(sum("generation_wh"))}
              tone="amber"
            />
            <Metric
              label="Consumo del hogar"
              value={kwh(sum("consumption_wh"))}
              tone="blue"
            />
            <Metric
              label="Importación de red"
              value={kwh(sum("grid_import_wh"))}
              tone="blue"
            />
            <Metric
              label="Exportación elegible"
              value={kwh(sum("eligible_export_wh"))}
            />
          </div>
          <Card title="Generación y consumo · kWh por intervalo">
            <EnergyChart intervals={values ?? []} />
          </Card>
          <Card title="Intercambio con la red · kWh por intervalo">
            <EnergyChart intervals={values ?? []} grid />
          </Card>
          <Card title="Registro de intervalos">
            <div className="table-wrap">
              <table>
                <caption>
                  Valores energéticos acumulados en cada intervalo; no son
                  potencia instantánea.
                </caption>
                <thead>
                  <tr>
                    <th>Inicio</th>
                    <th>Generación</th>
                    <th>Consumo</th>
                    <th>Importación</th>
                    <th>Exportación</th>
                    <th>Batería carga / descarga</th>
                    <th>Elegible</th>
                    <th>Calidad</th>
                  </tr>
                </thead>
                <tbody>
                  {values?.map((i) => (
                    <tr key={i.id}>
                      <td>{date(i.interval_start)}</td>
                      <td>{kwh(i.generation_wh)}</td>
                      <td>{kwh(i.consumption_wh)}</td>
                      <td>{kwh(i.grid_import_wh)}</td>
                      <td>{kwh(i.grid_export_wh)}</td>
                      <td>
                        {kwh(i.battery_charge_wh)} /{" "}
                        {kwh(i.battery_discharge_wh)}
                      </td>
                      <td>{kwh(i.eligible_export_wh)}</td>
                      <td>
                        <Badge value={i.quality_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </QueryState>
      )}
    </Page>
  );
}
