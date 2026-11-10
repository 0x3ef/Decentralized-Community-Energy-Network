import { test, expect } from "@playwright/test";
const api = "http://127.0.0.1:8000/api/v1";
test("protected routes recover to Spanish login", async ({ page }) => {
  await page.goto("/hogares");
  await expect(
    page.getByRole("heading", { name: "Bienvenido de nuevo" }),
  ).toBeVisible();
  await expect(page.getByLabel("Correo electrónico")).toBeVisible();
});
test("real API: registration, login, proposal, home, sensor, monitoring and mobile navigation", async ({
  page,
}) => {
  const suffix = Date.now().toString().slice(-8),
    email = `ui${suffix}@example.com`,
    password = "frontend-test-password";
  await page.goto("/");
  await page
    .getByRole("button", { name: "Crea tu cuenta", exact: true })
    .click();
  await page.getByLabel("Nombre", { exact: true }).fill("Elena");
  await page.getByLabel("Apellido", { exact: true }).fill("Solar");
  await page.getByLabel("Nombre de usuario", { exact: true }).fill(suffix);
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tu energía, Elena" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Mi comunidad", exact: true }).click();
  await page.getByRole("button", { name: "Proponer comunidad" }).click();
  await page
    .getByLabel("Nombre", { exact: true })
    .fill(`Comunidad solar ${suffix}`);
  await page
    .getByLabel("Límite físico de la comunidad")
    .fill("Perímetro de prueba en Cali");
  await page.getByRole("button", { name: "Guardar propuesta" }).click();
  await expect(page.getByLabel("Comunidad activa")).toContainText(
    `Comunidad solar ${suffix}`,
  );
  await page
    .getByRole("button", { name: "Enviar propuesta al registro" })
    .click();
  await expect(
    page.getByText("Propuesta", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "Mis hogares", exact: true }).click();
  await page
    .getByRole("button", { name: "Registrar hogar", exact: true })
    .click();
  await page.getByLabel("Nombre", { exact: true }).fill("Casa del sol");
  await page.getByLabel("Dirección", { exact: true }).fill("Calle 10 # 20-30");
  await page.getByLabel("Ciudad", { exact: true }).fill("Cali");
  await page.getByLabel("Capacidad solar instalada (W)").fill("4200");
  await page.getByRole("button", { name: "Guardar hogar" }).click();
  await expect(
    page.getByRole("heading", { name: "Casa del sol" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Nodos y medidores", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Registrar dispositivo", exact: true })
    .click();
  await page.getByLabel("Código del dispositivo").fill("METER-UI-" + suffix);
  await page.getByLabel("Fuente", { exact: true }).selectOption("SIMULATED");
  await page.getByLabel("Identificador MQTT").fill("e2e-" + suffix);
  await page
    .getByRole("button", { name: "Registrar dispositivo pendiente" })
    .click();
  await expect(
    page.getByRole("button", { name: new RegExp("METER-UI-" + suffix) }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Salud del medidor" }),
  ).toBeVisible();
  await expect(
    page.getByText("Sin señal reciente", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Monitoreo energético", exact: true })
    .click();
  await expect(
    page
      .getByRole("heading", { name: "Aún no hay intervalos energéticos" })
      .first(),
  ).toBeVisible();
  await expect(page.locator(".metric strong").first()).toHaveText("—");
  await page.getByRole("link", { name: "Créditos SUN", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Tu primera contribución está por llegar",
    }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Depósitos y retiros", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Revisar operación" }),
  ).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.getByRole("link", { name: "Resumen", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tu energía, Elena" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Activar tema oscuro" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Tu energía, Elena" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(
    page.getByRole("heading", { name: "Bienvenido de nuevo" }),
  ).toBeVisible();
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña").fill(password);
  await page
    .getByRole("button", { name: "Iniciar sesión", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Tu energía, Elena" }),
  ).toBeVisible();
});
test("real API: login failure does not create a session", async ({
  page,
  request,
}) => {
  const response = await request.get(`${api}/auth/me`);
  expect(response.status()).toBe(401);
  await page.goto("/");
  await page.getByLabel("Correo electrónico").fill("missing@example.com");
  await page.getByLabel("Contraseña").fill("incorrect123");
  await page
    .getByRole("button", { name: "Iniciar sesión", exact: true })
    .click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Bienvenido de nuevo" }),
  ).toBeVisible();
});
