import { afterEach, describe, it, expect, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { Metric, QueryState, Badge } from "../shared/ui/components";
import {
  normalizeWalletError,
  activeState,
} from "../shared/blockchain/transactions";
afterEach(cleanup);
describe("honest and accessible feedback", () => {
  it("renders an unavailable metric without inventing zero", () => {
    render(<Metric label="Energía" value="—" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it("offers retry and hides stale content when the request fails", () => {
    const refetch = vi.fn();
    render(
      <QueryState
        query={{
          isPending: false,
          isError: true,
          error: new Error("Sin conexión"),
          refetch,
        }}
      >
        <div>old financial balance</div>
      </QueryState>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Sin conexión");
    expect(screen.queryByText("old financial balance")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(refetch).toHaveBeenCalledOnce();
  });
  it("localizes protocol status without changing its domain value", () => {
    render(<Badge value="FINALIZED" />);
    expect(screen.getByText("Finalizado")).toBeInTheDocument();
  });
  it("labels pending data for assistive technologies", () => {
    render(
      <QueryState
        query={{
          isPending: true,
          isError: false,
          error: null,
          refetch: vi.fn(),
        }}
      >
        hidden
      </QueryState>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Consultando datos");
  });
  it("distinguishes cancellation, gas errors and unknown failures", () => {
    expect(normalizeWalletError({ code: 4001 })).toContain("Cancelaste");
    expect(
      normalizeWalletError({ message: "insufficient funds for gas" }),
    ).toContain("gas");
    expect(normalizeWalletError(new Error("timeout"))).toBe("timeout");
  });
  it("blocks new signatures during submission and confirmation", () => {
    expect(activeState("SUBMITTED")).toBe(true);
    expect(activeState("CONFIRMING")).toBe(true);
    expect(activeState("RECONCILIATION_REQUIRED")).toBe(false);
    expect(activeState("CONFIRMED")).toBe(false);
  });
});
