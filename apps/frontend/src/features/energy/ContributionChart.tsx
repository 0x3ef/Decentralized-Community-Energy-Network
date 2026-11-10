import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type {
  EnergyIntervalReadModel,
  BatchView,
} from "../../shared/api/models";
import { Empty } from "../../shared/ui/components";
import { date, eth } from "../../shared/utils/format";
export function ContributionChart({
  intervals,
}: {
  intervals: EnergyIntervalReadModel[];
}) {
  if (!intervals.length)
    return <Empty title="Sin contribuciones verificables" />;
  const data = intervals.map((row) => ({
    time: new Intl.DateTimeFormat("es-CO", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Bogota",
    }).format(new Date(row.interval_start)),
    eligible: row.eligible_export_wh / 1000,
  }));
  return (
    <div
      className="chart"
      role="img"
      aria-label="Exportación elegible por intervalo en kWh"
    >
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="time" minTickGap={40} />
          <YAxis unit=" kWh" width={70} />
          <Tooltip />
          <Bar
            dataKey="eligible"
            name="Exportación elegible"
            fill="#059669"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
export function AllocationHistory({ batches }: { batches: BatchView[] }) {
  if (!batches.length) return <Empty title="Sin asignaciones históricas" />;
  const data = [...batches].reverse().map((row) => ({
    interval: date(row.interval_start),
    allocated: row.allocated_wh / 1000,
    obligation: eth(row.total_due_wei),
    status: row.status,
  }));
  return (
    <div
      className="chart"
      role="img"
      aria-label="Energía comunitaria asignada por lote en kWh"
    >
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="interval" minTickGap={40} />
          <YAxis unit=" kWh" width={70} />
          <Tooltip
            content={({ active, payload }) =>
              active && payload?.[0] ? (
                <div className="card">
                  <p>{String(payload[0].payload.interval)}</p>
                  <p>{String(payload[0].payload.allocated)} kWh</p>
                  <p>{String(payload[0].payload.obligation)}</p>
                  <p>{String(payload[0].payload.status)}</p>
                </div>
              ) : null
            }
          />
          <Bar
            dataKey="allocated"
            name="Asignación comunitaria"
            fill="#3b82f6"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
