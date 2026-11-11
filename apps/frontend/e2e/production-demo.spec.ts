import { test, expect } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
const demoPath = new URL("../../../.run/demo/demo.json", import.meta.url);
const reportPath = new URL(
  "../../../.run/demo/scenario-report.json",
  import.meta.url,
);
const available = existsSync(demoPath) && existsSync(reportPath);
const demo = available ? JSON.parse(readFileSync(demoPath, "utf8")) : null;
const password = available
  ? readFileSync(
      new URL("../../../infrastructure/docker/.env", import.meta.url),
      "utf8",
    ).match(/^SEED_PASSWORD=(.+)$/m)?.[1]
  : undefined;
test.skip(
  !available || !password,
  "Run make demo and make demo-scenario to verify the production nginx frontend.",
);
for (const [index, role] of [
  [0, "producer"],
  [1, "consumer"],
] as const) {
  test(`production Docker frontend shows confirmed ${role} balances from the MQTT scenario`, async ({
    page,
  }) => {
    const login = await page.request.post(
      "http://127.0.0.1:8080/api/v1/auth/login",
      { data: { email: demo.members[index].email, password } },
    );
    expect(login.status()).toBe(200);
    const tokens = await login.json();
    await page.addInitScript((tokens) => {
      sessionStorage.setItem("solar.access", tokens.access_token);
      sessionStorage.setItem("solar.refresh", tokens.refresh_token);
    }, tokens);
    await page.goto("http://127.0.0.1:8080/");
    await expect(
      page.getByRole("heading", { name: "Tu energía, Solar" }),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Depósitos y retiros", exact: true })
      .click();
    const metrics = page.locator(".metric");
    if (role === "producer") {
      await expect(
        metrics.filter({ hasText: "Ingresos reclamables" }).locator("strong"),
      ).toHaveText("0 ETH");
      await expect(page.getByText("0,003 ETH", { exact: true })).toBeVisible();
      await expect(
        metrics
          .filter({ hasText: "SUN disponibles en depósito" })
          .locator("strong"),
      ).toHaveText("2 SUN");
    } else {
      await expect(
        metrics.filter({ hasText: "Depósito disponible" }).locator("strong"),
      ).toHaveText("0,007 ETH");
      await page.getByRole("link", { name: "Resumen", exact: true }).click();
      await expect(
        page
          .locator(".metric")
          .filter({ hasText: "Consumo compensado" })
          .locator("strong"),
      ).toHaveText("3 kWh");
    }
    await page
      .getByRole("link", { name: "Configuración", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Estado del sistema" }),
    ).toBeVisible();
    await expect(
      page.getByText("Procesador de energía y liquidación", { exact: true }),
    ).toBeVisible();
  });
}
