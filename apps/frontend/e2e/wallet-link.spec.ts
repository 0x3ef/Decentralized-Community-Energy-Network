import { test, expect } from "@playwright/test";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import type { Hex } from "viem";
/** An ephemeral test account signs only ownership messages; no production keys. */
test("real API: ownership challenge, signature verification and pending membership application", async ({
  page,
  request,
}) => {
  const account = privateKeyToAccount(generatePrivateKey()),
    suffix = Date.now().toString().slice(-8);
  const origin = "http://127.0.0.1:8000/api/v1",
    email = `wl${suffix}@example.com`,
    password = "wallet-link-test-password";
  const signup = await request.post(`${origin}/auth/signup`, {
    data: {
      username: suffix,
      email,
      password,
      first_name: "Lucia",
      last_name: "Solar",
    },
  });
  expect(signup.status()).toBe(201);
  const tokens = await (
    await request.post(`${origin}/auth/login`, { data: { email, password } })
  ).json();
  const community = await (
    await request.post(`${origin}/communities`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
      data: {
        name: "Solicitud de prueba",
        boundary_description: "Comunidad de prueba de membresía",
      },
    })
  ).json();
  await page.exposeBinding("signOwnership", async (_source, message: string) =>
    account.signMessage({ message: { raw: message as Hex } }),
  );
  await page.addInitScript(
    ({ address, tokens }) => {
      sessionStorage.setItem("solar.access", tokens.access_token);
      sessionStorage.setItem("solar.refresh", tokens.refresh_token);
      let connected = false;
      const listeners: Record<string, ((value: unknown) => void)[]> = {};
      Object.defineProperty(window, "ethereum", {
        value: {
          request: async ({
            method,
            params,
          }: {
            method: string;
            params?: string[];
          }) => {
            if (method === "eth_accounts") return connected ? [address] : [];
            if (method === "eth_chainId") return "0x7a69";
            if (method === "eth_requestAccounts") {
              connected = true;
              listeners.accountsChanged?.forEach((fn) => fn([address]));
              return [address];
            }
            if (method === "personal_sign")
              return (
                window as unknown as {
                  signOwnership: (message: string) => Promise<string>;
                }
              ).signOwnership(params![0]);
            throw new Error("Unexpected test wallet operation: " + method);
          },
          on: (event: string, handler: (value: unknown) => void) =>
            (listeners[event] ??= []).push(handler),
          removeListener: () => {},
        },
      });
    },
    { address: account.address, tokens },
  );
  await page.goto("/depositos");
  await page
    .getByRole("button", { name: "Conectar MetaMask", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Verificar propiedad" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Verificar propiedad" }).click();
  await expect(
    page.getByRole("button", { name: "Verificar propiedad" }),
  ).toHaveCount(0);
  const wallets = await (
    await request.get(`${origin}/wallet/`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    })
  ).json();
  expect(wallets.wallets).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ address: account.address, is_verified: true }),
    ]),
  );
  await page.getByRole("link", { name: "Mi comunidad", exact: true }).click();
  await page
    .getByLabel("Identificador de comunidad", { exact: true })
    .fill(community.id);
  const applied = page.waitForResponse(
    (response) =>
      response
        .url()
        .endsWith(`/communities/${community.id}/memberships/apply`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Registrar solicitud" }).click();
  const response = await applied;
  expect(response.status()).toBe(201);
  expect((await response.json()).status).toBe("PENDING");
  await expect(page.getByText(/Solicitud pendiente registrada/)).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Gobernanza", exact: true }),
  ).toHaveCount(0);
});
