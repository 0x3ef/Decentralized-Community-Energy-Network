import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { api, session, ApiError } from "../shared/api/client";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
beforeEach(() => sessionStorage.clear());
afterEach(() => vi.restoreAllMocks());
describe("API adapter", () => {
  it("refreshes concurrent expired requests once and uses the refresh Bearer token", async () => {
    session.save("expired", "refresh-secret");
    let refreshes = 0;
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input, init) => {
        const path = String(input);
        if (path.endsWith("/auth/refresh_token")) {
          refreshes++;
          expect(
            (init?.headers as Record<string, string> | undefined)
              ?.Authorization,
          ).toBe("Bearer refresh-secret");
          await new Promise((resolve) => setTimeout(resolve, 5));
          return json({ access_token: "fresh" });
        }
        return (init?.headers as Record<string, string> | undefined)
          ?.Authorization === "Bearer fresh"
          ? json({ ok: true })
          : json({}, 401);
      });
    const results = await Promise.all([api("/one"), api("/two")]);
    expect(refreshes).toBe(1);
    expect(results).toEqual([{ ok: true }, { ok: true }]);
    expect(fetcher).toHaveBeenCalledTimes(5);
  });
  it("normalizes unauthorized roles without retrying refresh", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}, 403));
    await expect(api("/governance")).rejects.toMatchObject({
      status: 403,
      message: "No tienes autorización para esta operación.",
    });
  });
  it("forwards abort signals", async () => {
    const controller = new AbortController();
    const mock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json([]));
    await api("/energy", { signal: controller.signal });
    expect(mock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });
  it("never sends account tokens on public login requests", async () => {
    session.save("secret");
    const mock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}));
    await api("/auth/login", {
      public: true,
      method: "POST",
      body: { email: "a@b.co", password: "safe" },
    });
    expect(mock.mock.calls[0][1]?.headers).not.toHaveProperty("Authorization");
  });
  it("clears both tokens when refresh is rejected", async () => {
    session.save("expired", "expired-refresh");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}, 401));
    await expect(api("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(session.access()).toBeNull();
    expect(session.refresh()).toBeNull();
  });
});
