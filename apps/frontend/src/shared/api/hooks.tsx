/* oxlint-disable react/only-export-components -- Context providers intentionally export their associated hooks. */
import { createContext, useContext, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, communityPath, ApiError } from "./client";
import type { Community, Home, Device, NativeWallet } from "./models";
import { useAuth } from "../../features/auth/AuthProvider";
export function useApi<T>(path: string, enabled = true, poll = false) {
  const { user } = useAuth();
  return useQuery<T>({
    queryKey: ["api", user?.uid, path],
    queryFn: ({ signal }) => api<T>(path, { signal }),
    enabled: !!user && enabled,
    staleTime: 20_000,
    refetchInterval: poll ? 30_000 : false,
    retry: (count, error) =>
      count < 1 &&
      !(
        error instanceof Error &&
        "status" in error &&
        [401, 403, 404, 409, 422].includes(Number(error.status))
      ),
  });
}
export function useAction<T = unknown>(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: unknown) => api<T>(path, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["api"] }),
  });
}
export const useHomes = () => useApi<{ homes: Home[] }>("/home/");
export function useDevices(home?: string) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["api", user?.uid, "devices", home],
    enabled: !!home && !!user,
    queryFn: async ({ signal }) => {
      try {
        return await api<{ devices: Device[] }>(
          `/device/device/?home_id=${encodeURIComponent(home!)}`,
          { signal },
        );
      } catch (error) {
        if (
          error instanceof ApiError &&
          error.status === 404 &&
          error.detail === "Devices not found for the home"
        )
          return { devices: [] };
        throw error;
      }
    },
    staleTime: 20_000,
    refetchInterval: 30_000,
    retry: false,
  });
}
export const useCommunities = () => useApi<Community[]>("/communities");
const Scope = createContext<{
  id: string;
  select: (id: string) => void;
  community: Community | undefined;
} | null>(null);
export function CommunityProvider({ children }: { children: ReactNode }) {
  const communities = useCommunities();
  const [chosen, setChosen] = useState(
    () => sessionStorage.getItem("solar.community") ?? "",
  );
  const id = communities.data?.some((c) => c.id === chosen)
    ? chosen
    : (communities.data?.[0]?.id ?? "");
  const select = (value: string) => {
    setChosen(value);
    sessionStorage.setItem("solar.community", value);
  };
  return (
    <Scope.Provider
      value={{
        id,
        select,
        community: communities.data?.find((c) => c.id === id),
      }}
    >
      {children}
    </Scope.Provider>
  );
}
export function useCommunity() {
  const value = useContext(Scope);
  if (!value) throw new Error("CommunityProvider missing");
  return value;
}
export function useNativeWallet() {
  const { id } = useCommunity();
  return useApi<NativeWallet>(`${communityPath(id)}/native-wallet`, !!id, true);
}
