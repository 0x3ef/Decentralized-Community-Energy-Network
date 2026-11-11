/** Browser wallet transport is test-only. All API and contract calls are real. */
import { test, expect, type Page } from "@playwright/test";
import { readFileSync, existsSync } from "node:fs";
const path = new URL("./.native-fixture.json", import.meta.url);
interface Actor {
  address: string;
  access_token: string;
}
interface Fixture {
  community: string;
  batch: string;
  producer: Actor;
  consumer: Actor;
  registry: string;
  vault: string;
}
const fixture = existsSync(path)
  ? (JSON.parse(readFileSync(path, "utf8")) as Fixture)
  : null;
test.describe.configure({ mode: "serial" });
test.skip(
  !fixture,
  "Run e2e/seed_native.py against the local development stack first.",
);
async function rpc(method: string, params: unknown[] = []) {
  const response = await fetch("http://127.0.0.1:8545", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const result = (await response.json()) as {
    result: unknown;
    error?: { message: string; code: number };
  };
  if (result.error) throw new Error(result.error.message);
  return result.result;
}
async function prepare(page: Page, actor: Actor, initialChain = "0x7a69") {
  await page.exposeBinding(
    "walletRpc",
    async (_source, request: { method: string; params?: unknown[] }) => {
      if (request.method === "eth_sendTransaction")
        return rpc(request.method, request.params);
      return rpc(request.method, request.params);
    },
  );
  await page.addInitScript(
    ({ actor, community, chain }) => {
      sessionStorage.setItem("solar.access", actor.access_token);
      sessionStorage.setItem("solar.community", community);
      let currentChain = chain,
        connected = sessionStorage.getItem("e2e.wallet.connected") === "true";
      const listeners: Record<string, Array<(data: unknown) => void>> = {};
      const request = async ({
        method,
        params = [],
      }: {
        method: string;
        params?: unknown[];
      }) => {
        if (method === "eth_accounts") return connected ? [actor.address] : [];
        if (method === "eth_requestAccounts") {
          connected = true;
          sessionStorage.setItem("e2e.wallet.connected", "true");
          listeners.accountsChanged?.forEach((fn) => fn([actor.address]));
          return [actor.address];
        }
        if (method === "eth_chainId") return currentChain;
        if (
          method === "eth_sendTransaction" &&
          sessionStorage.getItem("e2e.reject") === "true"
        )
          throw { code: 4001, message: "User rejected request" };
        if (method === "wallet_switchEthereumChain") {
          currentChain = (params[0] as { chainId: string }).chainId;
          listeners.chainChanged?.forEach((fn) => fn(currentChain));
          return null;
        }
        return (
          window as unknown as {
            walletRpc: (request: unknown) => Promise<unknown>;
          }
        ).walletRpc({ method, params });
      };
      Object.defineProperty(window, "ethereum", {
        value: {
          request,
          on: (event: string, fn: (data: unknown) => void) =>
            (listeners[event] ??= []).push(fn),
          removeListener: (event: string, fn: (data: unknown) => void) => {
            listeners[event] = (listeners[event] ?? []).filter(
              (item) => item !== fn,
            );
          },
        },
      });
    },
    { actor, community: fixture!.community, chain: initialChain },
  );
  await page.goto("/depositos");
  await page
    .getByRole("button", { name: "Conectar MetaMask", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Verificar propiedad" }),
  ).toHaveCount(0);
}
async function sign(page: Page) {
  await expect(
    page.getByRole("dialog", { name: "Revisar transacción" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirmar en MetaMask" }).click();
  await expect(page.locator(".transaction-toast .badge")).toHaveText(
    "Confirmado",
    { timeout: 25000 },
  );
  await page
    .locator(".transaction-toast")
    .getByRole("button", { name: "Cerrar", exact: true })
    .click();
}
test("real Anvil: wrong-network guard, ETH deposit, exact review, withdrawal and transaction history", async ({
  page,
}) => {
  await prepare(page, fixture!.consumer, "0x1");
  await expect(page.getByText(/Red incorrecta/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Revisar operación" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Cambiar de red" }).click();
  await expect(page.getByText(/Red incorrecta/)).toHaveCount(0);
  await page.getByLabel("Importe (ETH)", { exact: true }).fill("0,002");
  await page.getByRole("button", { name: "Revisar operación" }).click();
  await expect(page.getByRole("dialog")).toContainText("0.002 ETH");
  await sign(page);
  await page.getByLabel("Operación", { exact: true }).selectOption("withdraw");
  await page.getByLabel("Importe (ETH)", { exact: true }).fill("999999");
  await page.getByRole("button", { name: "Revisar operación" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "supera el saldo" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("Importe (ETH)", { exact: true }).fill("0,001");
  await page.getByRole("button", { name: "Revisar operación" }).click();
  await sign(page);
  await page.getByRole("link", { name: "Transacciones", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Registro del servidor" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "deposit", exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "withdraw", exact: true }).first(),
  ).toBeVisible();
});
test("real Anvil: verified injection, allocations, settlement and producer earnings withdrawal", async ({
  page,
}) => {
  await prepare(page, fixture!.producer);
  await page
    .getByRole("link", { name: "Monitoreo energético", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "5 kWh", exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Nodos y medidores", exact: true })
    .click();
  await expect(page.getByText("Simulado", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Evaluaciones de calidad" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Créditos SUN", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "5 kWh", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ver registro", exact: true }).click();
  await expect(
    page.getByText(/no expone una transacción para este crédito/),
  ).toBeVisible();
  await page.goto(`/liquidacion/${fixture!.batch}`);
  await expect(
    page.getByRole("heading", { name: "Mis asignaciones" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Liquidado", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "0,003 ETH", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Depósitos y retiros", exact: true })
    .click();
  await page
    .getByLabel("Operación", { exact: true })
    .selectOption("withdraw_earnings");
  await page.getByLabel("Importe (ETH)", { exact: true }).fill("0,001");
  await page.getByRole("button", { name: "Revisar operación" }).click();
  await sign(page);
  await page.screenshot({
    path: "test-results/native-balances-desktop.png",
    fullPage: true,
  });
});
test("real Anvil: eligible consumption, SUN approval and confirmed retirement", async ({
  page,
}) => {
  await prepare(page, fixture!.consumer);
  await page
    .getByRole("link", { name: "Compensación energética", exact: true })
    .click();
  await page.getByLabel("Lote", { exact: true }).selectOption(fixture!.batch);
  const claims = page.getByLabel("Claim de consumo", { exact: true });
  await expect(claims).toContainText("3 kWh");
  await claims.selectOption({ index: 1 });
  await expect(
    page.getByRole("button", { name: "2. Compensar consumo" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "1. Autorizar SUN" }).click();
  await sign(page);
  await page.getByRole("button", { name: "2. Compensar consumo" }).click();
  await sign(page);
  await expect(
    page.getByRole("button", { name: "2. Compensar consumo" }),
  ).toBeDisabled();
});
test("wallet rejection and Escape keep funds unchanged", async ({
  page,
  request,
}) => {
  await prepare(page, fixture!.consumer);
  const endpoint = `http://127.0.0.1:8000/api/v1/communities/${fixture!.community}/native-wallet`;
  const headers = { Authorization: `Bearer ${fixture!.consumer.access_token}` };
  const before = await (await request.get(endpoint, { headers })).json();
  await page.getByLabel("Importe (ETH)", { exact: true }).fill("0,001");
  await page.getByRole("button", { name: "Revisar operación" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.evaluate(() => sessionStorage.setItem("e2e.reject", "true"));
  await page.getByRole("button", { name: "Revisar operación" }).click();
  await page.getByRole("button", { name: "Confirmar en MetaMask" }).click();
  await expect(page.locator(".transaction-toast")).toContainText(
    "Cancelaste la firma",
  );
  await expect(page.locator(".transaction-toast .badge")).toHaveText("Fallido");
  const after = await (await request.get(endpoint, { headers })).json();
  expect(after.available_wei).toBe(before.available_wei);
});
test("real Anvil: role-gated registry governance is signed and confirmed", async ({
  page,
}) => {
  await prepare(page, fixture!.producer);
  await expect(
    page.getByRole("link", { name: "Gobernanza", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Gobernanza", exact: true }).click();
  await page.getByLabel("Acción", { exact: true }).selectOption("membership");
  await page.getByLabel("Estado de destino", { exact: true }).selectOption("4");
  await page
    .getByLabel("Wallet del participante", { exact: true })
    .fill(fixture!.consumer.address);
  await page.getByRole("button", { name: "Preparar para revisión" }).click();
  await sign(page);
});
