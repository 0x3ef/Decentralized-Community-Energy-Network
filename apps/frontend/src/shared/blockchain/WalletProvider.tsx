/* oxlint-disable react/only-export-components -- Context providers intentionally export their associated hooks. */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  createPublicClient,
  custom,
  getAddress,
  type Address,
  type Hex,
  type EIP1193Provider,
} from "viem";
import { useQuery } from "@tanstack/react-query";
import registryAbi from "./CommunityRegistry.json";
import timelockAbi from "./TimelockController.json";
import { useCommunity, useNativeWallet, useApi } from "../api/hooks";
import { api } from "../api/client";
import { errorMessage } from "../utils/format";
export type BrowserWallet = EIP1193Provider;
declare global {
  interface Window {
    ethereum?: BrowserWallet;
  }
}
interface WalletContext {
  address: Address | undefined;
  chainId: number | undefined;
  connect: () => Promise<void>;
  switchNetwork: () => Promise<void>;
  link: () => Promise<void>;
  error: string;
  linked: boolean;
  expectedChain: number;
  provider: BrowserWallet | undefined;
}
const Context = createContext<WalletContext | null>(null);
export function WalletProvider({ children }: { children: ReactNode }) {
  const native = useNativeWallet();
  const wallets = useApi<{
    wallets: Array<{ address: string; is_verified: boolean }>;
  }>("/wallet/");
  const [address, setAddress] = useState<Address>(),
    [chainId, setChainId] = useState<number>(),
    [error, setError] = useState("");
  const provider = window.ethereum;
  const expectedChain =
    native.data?.chain_id ?? Number(import.meta.env.VITE_CHAIN_ID || 31337);
  const updateAccounts = (value: unknown) => {
    const accounts = value as string[];
    setAddress(accounts[0] ? getAddress(accounts[0]) : undefined);
  };
  useEffect(() => {
    if (!provider) return;
    void provider
      .request({ method: "eth_accounts" })
      .then(updateAccounts)
      .catch(() => {});
    void provider
      .request({ method: "eth_chainId" })
      .then((value) => setChainId(Number(value)))
      .catch(() => {});
    const accounts = (value: unknown) => updateAccounts(value),
      chain = (value: unknown) => setChainId(Number(value));
    provider.on?.("accountsChanged", accounts);
    provider.on?.("chainChanged", chain);
    return () => {
      provider.removeListener?.("accountsChanged", accounts);
      provider.removeListener?.("chainChanged", chain);
    };
  }, [provider]);
  async function safe(action: () => Promise<void>) {
    setError("");
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
      throw e;
    }
  }
  const connect = () =>
    safe(async () => {
      if (!provider)
        throw new Error("Instala MetaMask para conectar una wallet.");
      updateAccounts(await provider.request({ method: "eth_requestAccounts" }));
    });
  const switchNetwork = () =>
    safe(async () => {
      if (!provider) throw new Error("Conecta MetaMask.");
      if (![31337, 1337, 11155111].includes(expectedChain))
        throw new Error("Red no admitida.");
      const chainHex = `0x${expectedChain.toString(16)}`;
      try {
        await provider.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: chainHex }],
        });
      } catch (error) {
        if ((error as { code?: number }).code !== 4902) throw error;
        const rpc =
          expectedChain === 11155111
            ? import.meta.env.VITE_SEPOLIA_RPC_URL
            : import.meta.env.VITE_ANVIL_RPC_URL || "http://127.0.0.1:8545";
        if (!rpc)
          throw new Error(
            "Configura el RPC de Sepolia en el despliegue o añade la red en MetaMask.",
          );
        const endpoint = new URL(rpc);
        if (
          endpoint.protocol !== "https:" &&
          !(
            endpoint.protocol === "http:" &&
            ["localhost", "127.0.0.1"].includes(endpoint.hostname)
          )
        )
          throw new Error("El RPC debe usar HTTPS, salvo Anvil local.");
        await provider.request({
          method: "wallet_addEthereumChain",
          params: [
            {
              chainId: chainHex,
              chainName: expectedChain === 11155111 ? "Sepolia" : "Anvil",
              nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
              rpcUrls: [rpc],
              ...(expectedChain === 11155111
                ? { blockExplorerUrls: ["https://sepolia.etherscan.io"] }
                : {}),
            },
          ],
        });
        await provider.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: chainHex }],
        });
      }
      setChainId(Number(await provider.request({ method: "eth_chainId" })));
    });
  const link = () =>
    safe(async () => {
      if (!provider || !address) throw new Error("Conecta tu wallet primero.");
      const { message, nonce } = await api<{ message: string; nonce: string }>(
        "/communities/wallet/challenge",
        { method: "POST", body: { address } },
      );
      const signature = await provider.request({
        method: "personal_sign",
        params: [
          `0x${Array.from(new TextEncoder().encode(message))
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("")}`,
          address,
        ],
      });
      await api("/communities/wallet/verify", {
        method: "POST",
        body: { address, nonce, signature },
      });
      await Promise.all([native.refetch(), wallets.refetch()]);
    });
  const linked =
    !!address &&
    (native.data?.address.toLowerCase() === address.toLowerCase() ||
      !!wallets.data?.wallets.some(
        (w) =>
          w.is_verified && w.address.toLowerCase() === address.toLowerCase(),
      ));
  return (
    <Context.Provider
      value={{
        address,
        chainId,
        connect,
        switchNetwork,
        link,
        error,
        linked,
        expectedChain,
        provider,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useWallet() {
  const value = useContext(Context);
  if (!value) throw new Error("WalletProvider missing");
  return value;
}
export function useRoles() {
  const { id, community } = useCommunity();
  const { provider, address, chainId, expectedChain, linked } = useWallet();
  const registry = (community?.registry_address ??
    import.meta.env.VITE_REGISTRY_ADDRESS) as Address | undefined;
  const timelock = import.meta.env.VITE_TIMELOCK_ADDRESS as Address | undefined;
  return useQuery({
    queryKey: ["roles", id, address, chainId, linked, registry, timelock],
    enabled:
      !!provider &&
      !!address &&
      !!id &&
      !!registry &&
      linked &&
      chainId === expectedChain,
    queryFn: async () => {
      const client = createPublicClient({ transport: custom(provider!) });
      const abi = registryAbi as never;
      const communityId =
        `0x${id.replaceAll("-", "").padStart(64, "0")}` as Hex;
      const state = (await client.readContract({
        address: registry!,
        abi,
        functionName: "communities",
        args: [communityId],
      })) as unknown as readonly [Address, Address, number, ...unknown[]];
      const readRole = async (name: string) => {
        const role = (await client.readContract({
          address: registry!,
          abi,
          functionName: name,
        })) as Hex;
        return (await client.readContract({
          address: registry!,
          abi,
          functionName: "hasRole",
          args: [role, address],
        })) as boolean;
      };
      const [registrar, meterRegistrar] = await Promise.all([
        readRole("REGISTRAR_ROLE"),
        readRole("METER_REGISTRAR_ROLE"),
      ]);
      let proposer = false,
        executor = false;
      if (timelock) {
        const ta = timelockAbi as never;
        const pr = (await client.readContract({
          address: timelock,
          abi: ta,
          functionName: "PROPOSER_ROLE",
        })) as Hex;
        const er = (await client.readContract({
          address: timelock,
          abi: ta,
          functionName: "EXECUTOR_ROLE",
        })) as Hex;
        proposer = (await client.readContract({
          address: timelock,
          abi: ta,
          functionName: "hasRole",
          args: [pr, address],
        })) as boolean;
        executor = (await client.readContract({
          address: timelock,
          abi: ta,
          functionName: "hasRole",
          args: [er, address],
        })) as boolean;
      }
      return {
        operator: state[1].toLowerCase() === address!.toLowerCase(),
        registrar,
        meterRegistrar,
        proposer,
        executor,
        governance: registrar || meterRegistrar || proposer || executor,
      };
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });
}
