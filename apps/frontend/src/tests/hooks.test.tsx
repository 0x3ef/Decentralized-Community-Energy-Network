import { it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useApi, useDevices } from "../shared/api/hooks";
import { session } from "../shared/api/client";
vi.mock("../features/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { uid: "test-user" } }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {children}
    </QueryClientProvider>
  );
}
it("does not fetch a disabled resource", async () => {
  const mock = vi.spyOn(globalThis, "fetch");
  renderHook(() => useApi("/private-resource", false), { wrapper });
  expect(mock).not.toHaveBeenCalled();
});
it("does not retry a request canceled by a session change", async () => {
  let resolveFetch!: (response: Response) => void;
  const mock = vi.spyOn(globalThis, "fetch").mockImplementation(
    () => new Promise((resolve) => (resolveFetch = resolve)),
  );
  session.save("old-access", "old-refresh");
  const hook = renderHook(() => useApi("/private-resource"), { wrapper });
  await waitFor(() => expect(mock).toHaveBeenCalledTimes(1));
  session.clear();
  resolveFetch(new Response(JSON.stringify({})));
  await waitFor(() => expect(hook.result.current.isError).toBe(true));
  expect(mock).toHaveBeenCalledTimes(1);
});
it("normalizes only the documented empty-device response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "Devices not found for the home" }), {
      status: 404,
    }),
  );
  const hook = renderHook(() => useDevices("home"), { wrapper });
  await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
  expect(hook.result.current.data).toEqual({ devices: [] });
});
it("preserves permission and missing-home errors", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "Home not found" }), { status: 404 }),
  );
  const hook = renderHook(() => useDevices("other-home"), { wrapper });
  await waitFor(() => expect(hook.result.current.isError).toBe(true));
  expect(hook.result.current.data).toBeUndefined();
});
