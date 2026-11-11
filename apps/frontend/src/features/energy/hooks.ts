import { useState, useEffect } from "react";
import { useHomes, useApi } from "../../shared/api/hooks";
import type { EnergyIntervalReadModel } from "../../shared/api/models";
export function useHomeSelection() {
  const homes = useHomes();
  const [selected, setSelected] = useState("");
  const home =
    homes.data?.homes.find((h) => h.id === selected) ?? homes.data?.homes[0];
  return { homes, home, select: setSelected };
}
export function rangeForDays(days: number) {
  const end = new Date();
  end.setSeconds(0, 0);
  return {
    start: new Date(end.getTime() - days * 86400000).toISOString(),
    end: end.toISOString(),
  };
}
export function useIntervals(homeId: string | undefined, days = 1) {
  const [anchor, setAnchor] = useState(() => new Date().toISOString());
  useEffect(() => {
    const timer = window.setInterval(
      () => setAnchor(new Date().toISOString()),
      60_000,
    );
    return () => window.clearInterval(timer);
  }, []);
  const end = new Date(anchor),
    start = new Date(end.getTime() - days * 86400000);
  return useApi<EnergyIntervalReadModel[]>(
    `/energy/homes/${homeId ?? ""}/energy/intervals?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
    !!homeId,
    true,
  );
}
