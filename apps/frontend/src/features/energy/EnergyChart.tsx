import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { EnergyIntervalReadModel } from "../../shared/api/models";
import { Empty } from "../../shared/ui/components";
export function EnergyChart({
  intervals,
  grid = false,
}: {
  intervals: EnergyIntervalReadModel[];
  grid?: boolean;
}) {
  if (!intervals.length)
    return (
      <Empty title="Aún no hay intervalos energéticos">
        La gráfica requiere intervalos calculados a partir de mediciones
        aceptadas.
      </Empty>
    );
  const data = intervals.map((i) => ({
    time: new Intl.DateTimeFormat("es-CO", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Bogota",
    }).format(new Date(i.interval_start)),
    generation: i.generation_wh / 1000,
    consumption: i.consumption_wh / 1000,
    imports: i.grid_import_wh / 1000,
    exports: i.grid_export_wh / 1000,
  }));
  return (
    <div
      className="chart"
      role="img"
      aria-label={
        grid
          ? "Energía importada y exportada por intervalo, en kWh"
          : "Generación solar y consumo por intervalo, en kWh"
      }
    >
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart
          data={data}
          margin={{ top: 15, right: 15, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="solar-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e9a522" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#e9a522" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            vertical={false}
            strokeDasharray="3 4"
            stroke="var(--border)"
          />
          <XAxis
            dataKey="time"
            tickLine={false}
            axisLine={false}
            minTickGap={45}
          />
          <YAxis unit=" kWh" tickLine={false} axisLine={false} width={75} />
          <Tooltip />
          <Legend />
          <Area
            isAnimationActive={false}
            type="monotone"
            dataKey={grid ? "imports" : "generation"}
            name={grid ? "Importación" : "Generación solar"}
            stroke={grid ? "#3b82f6" : "#e9a522"}
            fill="url(#solar-fill)"
            strokeWidth={2}
          />
          <Area
            isAnimationActive={false}
            type="monotone"
            dataKey={grid ? "exports" : "consumption"}
            name={grid ? "Exportación" : "Consumo del hogar"}
            stroke={grid ? "#059669" : "#3b82f6"}
            fill="transparent"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
