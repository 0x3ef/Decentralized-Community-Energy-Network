import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "../features/auth/AuthProvider";
import { session } from "../shared/api/client";

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => session.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("retains session tokens when recovery fails because the API is unavailable", async () => {
  session.save("saved-access", "saved-refresh");
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Network unavailable"));
  const client = new QueryClient();
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}><AuthProvider>{children}</AuthProvider></QueryClientProvider>;
  }
  const hook = renderHook(useAuth, { wrapper });
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  expect(session.access()).toBe("saved-access");
  expect(session.refresh()).toBe("saved-refresh");
});

it("reports login failure when the current account's refresh is rejected", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input).endsWith("/auth/login")
      ? json({ access_token: "rejected", refresh_token: "rejected-refresh" })
      : json({}, 401),
  );
  const client = new QueryClient();
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}><AuthProvider>{children}</AuthProvider></QueryClientProvider>;
  }
  const hook = renderHook(useAuth, { wrapper });
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  await act(async () => {
    await expect(hook.result.current.login("user@example.com", "password")).rejects.toMatchObject({ status: 401 });
  });
  expect(hook.result.current.user).toBeNull();
  expect(session.access()).toBeNull();
});

it("keeps a new login when the previous recovery and logout finish late", async () => {
  const oldRecovery = deferred<Response>(), oldLogout = deferred<Response>();
  let account = "first", delayRecovery = false;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith("/auth/login"))
      return json({ access_token: account, refresh_token: `${account}-refresh` });
    if (path.endsWith("/auth/logout")) return oldLogout.promise;
    if (path.endsWith("/auth/me"))
      return delayRecovery ? oldRecovery.promise : json({ uid: account });
    throw new Error(`Unexpected request: ${path}`);
  });
  const client = new QueryClient();
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}><AuthProvider>{children}</AuthProvider></QueryClientProvider>;
  }
  const hook = renderHook(useAuth, { wrapper });
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  await act(async () => { await hook.result.current.login("first@example.com", "password"); });
  client.setQueryData(["private"], "first-account-data");
  delayRecovery = true;
  let recovery!: Promise<void>, logout!: Promise<void>;
  act(() => { recovery = hook.result.current.recover(); });
  // Let recover send its request before logging out.
  await act(async () => { await Promise.resolve(); });
  act(() => { logout = hook.result.current.logout(); });
  expect(hook.result.current.user).toBeNull();
  expect(client.getQueryData(["private"])).toBeUndefined();
  delayRecovery = false;
  account = "second";
  await act(async () => { await hook.result.current.login("second@example.com", "password"); });
  await act(async () => {
    oldRecovery.resolve(json({}, 401));
    oldLogout.resolve(json({}));
    await Promise.all([recovery, logout]);
  });
  expect(hook.result.current.user?.uid).toBe("second");
  expect(session.access()).toBe("second");
  expect(session.refresh()).toBe("second-refresh");
});
