import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GovernancePage from "../features/governance/GovernancePage";

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  begin: vi.fn(),
  governance: true,
  pending: false,
  ready: false,
}));
vi.mock("../shared/api/client", () => ({
  api: mocks.api,
  communityPath: (id: string) => `/communities/${id}`,
}));
vi.mock("../shared/api/hooks", () => ({
  useCommunity: () => ({ id: "community", community: { status: "ACTIVE" } }),
}));
vi.mock("../features/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { uid: "governor" } }),
}));
vi.mock("../shared/blockchain/WalletProvider", () => ({
  useRoles: () => ({ data: { governance: mocks.governance } }),
}));
vi.mock("../shared/blockchain/read-hooks", () => ({
  useTimelock: () => ({
    data: { ready: mocks.ready, pending: mocks.pending, done: false },
    isSuccess: true,
  }),
}));
vi.mock("../shared/blockchain/transactions", () => ({
  useTransactions: () => ({ state: "IDLE", begin: mocks.begin }),
  activeState: () => false,
}));
vi.mock("../features/wallet/WalletPanel", () => ({ WalletPanel: () => null }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  mocks.governance = true;
  mocks.pending = false;
  mocks.ready = false;
});

it("prepares the selected settlement for review without submitting a transaction", async () => {
  const batch = "12345678-1234-4234-8234-123456789abc";
  const timelock = "0x1111111111111111111111111111111111111111";
  vi.stubEnv("VITE_TIMELOCK_ADDRESS", timelock);
  mocks.api.mockResolvedValue({
    chain_id: 31337, timelock, operation_id: "0x01", delay_seconds: 60,
  });
  render(
    <MemoryRouter initialEntries={[`/gobernanza?action=finalize_batch&batch=${batch}`]}>
      <GovernancePage />
    </MemoryRouter>,
  );
  expect((screen.getByLabelText("UUID del lote energético") as HTMLInputElement).value)
    .toBe(batch);
  fireEvent.click(screen.getByRole("button", { name: "Preparar para revisión" }));
  await waitFor(() => expect(mocks.api).toHaveBeenCalledWith(
    "/communities/community/governance/prepare",
    { method: "POST", body: expect.objectContaining({ action: "finalize_batch", batch_id: batch }) },
  ));
  await screen.findByText(`Finalizar lote ${batch}`);
  expect(mocks.begin).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Ejecutar acción autorizada" }).hasAttribute("disabled"))
    .toBe(true);
});

it("requires the governance wallet role before showing finalization controls", () => {
  mocks.governance = false;
  render(<MemoryRouter><GovernancePage /></MemoryRouter>);
  expect(screen.queryByRole("button", { name: "Preparar para revisión" })).toBeNull();
  expect(screen.getByText("Se requiere un rol autorizado")).toBeTruthy();
});

it("allows execution of a ready operation without scheduling it twice", () => {
  mocks.pending = true;
  mocks.ready = true;
  localStorage.setItem("solar.governance", JSON.stringify([{
    community: "community", user: "governor", action: "finalize_batch",
    description: "Finalizar lote revisado",
    prepared: { operation_id: "0x01", delay_seconds: 60 },
  }]));
  render(<MemoryRouter><GovernancePage /></MemoryRouter>);
  expect(screen.getByRole("button", { name: "Programar en timelock" }).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.getByRole("button", { name: "Ejecutar acción autorizada" }).hasAttribute("disabled"))
    .toBe(false);
});
