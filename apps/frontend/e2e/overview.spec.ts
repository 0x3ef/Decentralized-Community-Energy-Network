import { test, expect } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
const demoPath = new URL("../../../.run/demo/demo.json", import.meta.url);
const envPath = new URL("../../../infrastructure/docker/.env", import.meta.url);
const available = existsSync(demoPath) && existsSync(envPath);
const demo = available ? JSON.parse(readFileSync(demoPath, "utf8")) : null;
const password = available
  ? readFileSync(envPath, "utf8").match(/^SEED_PASSWORD=(.+)$/m)?.[1]
  : undefined;
test.skip(
  !available || !password,
  "Requires an existing demo; does not seed or reset data.",
);
for (const mobile of [false, true]) {
  test(`existing account: overview and management (${mobile ? "mobile" : "desktop"})`, async ({
    page,
  }) => {
    await page.setViewportSize(
      mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
    );
    const response = await page.request.post("/api/v1/auth/login", {
      data: { email: demo.members[4].email, password },
    });
    expect(response.status()).toBe(200);
    const tokens = await response.json();
    await page.addInitScript((tokens) => {
      sessionStorage.setItem("solar.access", tokens.access_token);
      sessionStorage.setItem("solar.refresh", tokens.refresh_token);
    }, tokens);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /^Hola,/ })).toBeVisible();
    await expect(
      page
        .getByRole("img", {
          name: "Generación solar y consumo por intervalo, en kWh",
        })
        .or(
          page.getByRole("heading", {
            name: "Aún no hay intervalos energéticos",
          }),
        ),
    ).toBeVisible();
    await expect(page.locator(".balance-list").first()).toContainText(
      "SUN en wallet",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/overview-${mobile ? "mobile" : "desktop"}.png`,
      fullPage: true,
    });
    if (mobile) await page.getByRole("button", { name: "Abrir menú" }).click();
    await expect(
      page
        .getByRole("navigation", { name: "Navegación principal" })
        .getByRole("link"),
    ).toHaveCount(5);
    await expect(
      page.getByRole("link", { name: "Nodos y medidores", exact: true }),
    ).not.toBeVisible();
    await page.locator(".management-menu > summary").click();
    await page
      .getByRole("link", { name: "Nodos y medidores", exact: true })
      .click();
    await expect(page).toHaveURL(/\/dispositivos$/);
    if (mobile)
      await expect(
        page.getByRole("dialog", { name: "Menú principal" }),
      ).not.toBeVisible();
    await page.goto("/depositos");
    await expect(
      page.getByRole("button", { name: "Revisar operación" }),
    ).toBeDisabled();
    await expect(
      page.getByRole("heading", { name: "Autorizaciones SUN confirmadas" }),
    ).not.toBeVisible();
    await page
      .getByText("SUN, reservas y autorizaciones", { exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Autorizaciones SUN confirmadas" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Activar tema oscuro" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({
      path: `test-results/wallet-dark-${mobile ? "mobile" : "desktop"}.png`,
      fullPage: true,
    });
  });
}
