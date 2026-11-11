import { it, expect, vi, afterEach, beforeEach } from "vitest";
import { renderHook, act, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { WalletProvider, useWallet } from "../shared/blockchain/WalletProvider";
import type { BrowserWallet } from "../shared/blockchain/WalletProvider";
const refetch = vi.fn();
vi.mock("../shared/api/hooks", () => ({
  useNativeWallet: () => ({ data: undefined, refetch }),
  useApi: () => ({ data: { wallets: [] }, refetch }),
  useCommunity: () => ({ id: "community" }),
}));
const request = vi.fn(),
  on = vi.fn(),
  removeListener = vi.fn();
function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <WalletProvider>{children}</WalletProvider>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  request.mockImplementation(async ({ method }: { method: string }) =>
    method === "eth_chainId" ? "0x1" : [],
  );
  window.ethereum = { request, on, removeListener } as unknown as BrowserWallet;
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  delete window.ethereum;
});
it("checks existing accounts without requesting a signature or connection on load", async () => {
  const hook = renderHook(useWallet, { wrapper });
  await waitFor(() => expect(hook.result.current.chainId).toBe(1));
  expect(request.mock.calls.map((c) => c[0].method)).toEqual([
    "eth_accounts",
    "eth_chainId",
  ]);
  expect(hook.result.current.linked).toBe(false);
});
it("connects only after explicit action and detects a wrong chain", async () => {
  request.mockImplementation(async ({ method }: { method: string }) =>
    method === "eth_requestAccounts"
      ? ["0x1111111111111111111111111111111111111111"]
      : method === "eth_chainId"
        ? "0x1"
        : [],
  );
  const hook = renderHook(useWallet, { wrapper });
  await act(() => hook.result.current.connect());
  expect(hook.result.current.address).toBe(
    "0x1111111111111111111111111111111111111111",
  );
  expect(hook.result.current.chainId).not.toBe(
    hook.result.current.expectedChain,
  );
  expect(hook.result.current.linked).toBe(false);
});
it("responds to account changes and unregisters extension listeners", async () => {
  const hook = renderHook(useWallet, { wrapper });
  await waitFor(() => expect(on).toHaveBeenCalledTimes(2));
  const accounts = on.mock.calls.find((c) => c[0] === "accountsChanged")![1];
  act(() => accounts(["0x2222222222222222222222222222222222222222"]));
  expect(hook.result.current.address).toBe(
    "0x2222222222222222222222222222222222222222",
  );
  act(() => accounts([]));
  expect(hook.result.current.address).toBeUndefined();
  hook.unmount();
  expect(removeListener).toHaveBeenCalledTimes(2);
});
it("rejects wallet verification before connecting", async () => {
  const hook = renderHook(useWallet, { wrapper });
  await act(async () => {
    await expect(hook.result.current.link()).rejects.toThrow(
      "Conecta tu wallet",
    );
  });
  expect(hook.result.current.error).toContain("Conecta tu wallet");
});

it("requests the configured Sepolia chain without accepting mainnet", async () => {
  vi.stubEnv("VITE_CHAIN_ID", "11155111");
  try {
    let chain = "0x1";
    request.mockImplementation(
      async ({
        method,
        params,
      }: {
        method: string;
        params?: Array<{ chainId: string }>;
      }) => {
        if (method === "eth_chainId") return chain;
        if (method === "wallet_switchEthereumChain") {
          chain = params![0].chainId;
          return null;
        }
        return [];
      },
    );
    const hook = renderHook(useWallet, { wrapper });
    await waitFor(() => expect(hook.result.current.chainId).toBe(1));
    expect(hook.result.current.expectedChain).toBe(11155111);
    await act(() => hook.result.current.switchNetwork());
    expect(hook.result.current.chainId).toBe(11155111);
    expect(request).toHaveBeenCalledWith({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0xaa36a7" }],
    });
  } finally {
    vi.unstubAllEnvs();
  }
});
