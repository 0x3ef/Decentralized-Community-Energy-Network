import { useQuery } from "@tanstack/react-query";
import {
  createPublicClient,
  custom,
  type Address,
  type Hex,
  type Abi,
} from "viem";
import { useWallet } from "./WalletProvider";
import { useNativeWallet } from "../api/hooks";
import sunAbi from "./SUNToken.json";
import timelockAbi from "./TimelockController.json";
import type { Prepared } from "../api/models";
export function useAllowances() {
  const wallet = useWallet(),
    native = useNativeWallet();
  return useQuery({
    queryKey: [
      "allowance",
      wallet.address,
      wallet.chainId,
      native.data?.contracts,
    ],
    enabled:
      !!wallet.provider &&
      !!wallet.address &&
      wallet.linked &&
      wallet.chainId === wallet.expectedChain &&
      !!native.data,
    queryFn: async () => {
      const client = createPublicClient({
          transport: custom(wallet.provider!),
        }),
        contracts = native.data!.contracts;
      const read = (spender: string) =>
        client.readContract({
          address: contracts.sun_address as Address,
          abi: sunAbi as Abi,
          functionName: "allowance",
          args: [wallet.address, spender],
        }) as Promise<bigint>;
      const [vault, retirement] = await Promise.all([
        read(contracts.vault_address),
        read(contracts.settlement_address),
      ]);
      return { vault, retirement };
    },
    refetchInterval: 15_000,
    staleTime: 10_000,
    retry: false,
  });
}
export function useTimelock(prepared: Prepared) {
  const wallet = useWallet();
  return useQuery({
    queryKey: ["timelock", prepared.operation_id, wallet.chainId],
    enabled: !!wallet.provider && wallet.chainId === prepared.chain_id,
    queryFn: async () => {
      const client = createPublicClient({
        transport: custom(wallet.provider!),
      });
      const read = (functionName: string) =>
        client.readContract({
          address: prepared.timelock as Address,
          abi: timelockAbi as Abi,
          functionName,
          args: [prepared.operation_id as Hex],
        }) as Promise<boolean>;
      const [ready, done] = await Promise.all([
        read("isOperationReady"),
        read("isOperationDone"),
      ]);
      return { ready, done };
    },
    refetchInterval: 15_000,
    retry: false,
  });
}

export function useConnectedBalance() {
  const wallet = useWallet();
  return useQuery({
    queryKey: ["wallet-balance", wallet.address, wallet.chainId],
    enabled:
      !!wallet.provider &&
      !!wallet.address &&
      wallet.chainId === wallet.expectedChain,
    queryFn: () =>
      createPublicClient({ transport: custom(wallet.provider!) }).getBalance({
        address: wallet.address!,
      }),
    refetchInterval: 15_000,
    staleTime: 10_000,
    retry: false,
  });
}
