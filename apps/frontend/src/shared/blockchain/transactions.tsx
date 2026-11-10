/* oxlint-disable react/only-export-components -- Context providers intentionally export their associated hooks. */
import { validateNativeCall } from "./validate";
import {
  createContext,
  useContext,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { createPublicClient, custom, type Address, type Hex } from "viem";
import { useQueryClient } from "@tanstack/react-query";
import { useWallet } from "./WalletProvider";
import { useAuth } from "../../features/auth/AuthProvider";
import { api, communityPath } from "../api/client";
import { useCommunity, useNativeWallet } from "../api/hooks";
import type { Prepared } from "../api/models";
import { Dialog, Notice, Hash, Badge } from "../ui/components";
import { errorMessage, exactUnits } from "../utils/format";
export type TransactionState =
  | "IDLE"
  | "PREPARING"
  | "AWAITING_SIGNATURE"
  | "SUBMITTED"
  | "CONFIRMING"
  | "CONFIRMED"
  | "FAILED"
  | "RECONCILIATION_REQUIRED";
export interface Journal {
  id: string;
  user: string;
  community: string;
  address: string;
  chain: number;
  action: string;
  state: TransactionState;
  hash?: Hex;
  previousHash?: Hex;
  message?: string;
  created: string;
  track?: boolean;
  syncPath?: string;
}
interface Request {
  action: string;
  label: string;
  body?: Record<string, unknown>;
  prepare?: () => Promise<Prepared>;
  after?: (hash: Hex) => Promise<unknown>;
  track?: boolean;
  syncPath?: string;
}
interface Review {
  request: Request;
  prepared: Prepared;
  community: string;
  user: string;
  address: Address;
}
interface TxContext {
  state: TransactionState;
  begin: (request: Request) => Promise<void>;
  journal: Journal[];
  reconcile: (entry: Journal) => Promise<void>;
  error: string;
}
const Context = createContext<TxContext | null>(null);
export const activeState = (state: TransactionState) =>
  ["PREPARING", "AWAITING_SIGNATURE", "SUBMITTED", "CONFIRMING"].includes(
    state,
  );
function readJournal(): Journal[] {
  try {
    return JSON.parse(
      localStorage.getItem("solar.transactions") ?? "[]",
    ) as Journal[];
  } catch {
    return [];
  }
}
export function TransactionProvider({ children }: { children: ReactNode }) {
  const wallet = useWallet(),
    { user } = useAuth(),
    { id, community } = useCommunity(),
    native = useNativeWallet(),
    client = useQueryClient();
  const [state, setState] = useState<TransactionState>("IDLE"),
    [error, setError] = useState(""),
    [review, setReview] = useState<Review | null>(null),
    [journal, setJournal] = useState<Journal[]>(readJournal),
    [current, setCurrent] = useState<Journal | null>(null);
  const preparing = useRef(false);
  function save(entry: Journal) {
    setJournal((previous) => {
      const next = [entry, ...previous.filter((x) => x.id !== entry.id)].slice(
        0,
        200,
      );
      localStorage.setItem("solar.transactions", JSON.stringify(next));
      return next;
    });
    setCurrent(entry);
    setState(entry.state);
  }
  async function begin(request: Request) {
    if (activeState(state) || preparing.current) return;
    preparing.current = true;
    setState("PREPARING");
    setError("");
    setCurrent(null);
    try {
      if (!wallet.provider || !wallet.address || !wallet.linked || !user)
        throw new Error("Conecta y verifica tu wallet antes de continuar.");
      if (wallet.chainId !== wallet.expectedChain)
        throw new Error("Cambia a la red configurada antes de firmar.");
      const prepared = request.prepare
        ? await request.prepare()
        : await api<Prepared>(`${communityPath(id)}/native/prepare`, {
            method: "POST",
            body: { action: request.action, ...request.body },
          });
      if (
        prepared.chain_id !== wallet.expectedChain ||
        (prepared.from &&
          prepared.from.toLowerCase() !== wallet.address.toLowerCase())
      )
        throw new Error("La preparación no coincide con tu red o wallet.");
      if (!request.prepare) {
        if (!native.data)
          throw new Error(
            "No hay balances confirmados para validar la operación.",
          );
        validateNativeCall(
          prepared,
          request.action,
          request.body ?? {},
          native.data,
          wallet.address,
        );
      } else {
        const allowed = [
          community?.registry_address,
          import.meta.env.VITE_REGISTRY_ADDRESS,
          import.meta.env.VITE_TIMELOCK_ADDRESS,
        ]
          .filter(Boolean)
          .map((value) => String(value).toLowerCase());
        if (
          !allowed.includes(prepared.to.toLowerCase()) ||
          BigInt(prepared.value) !== 0n
        )
          throw new Error(
            "El destino de gobernanza no coincide con la configuración.",
          );
      }
      if (request.prepare) {
        const rpc = createPublicClient({ transport: custom(wallet.provider) });
        await rpc.call({
          account: wallet.address,
          to: prepared.to as Address,
          data: prepared.data as Hex,
          value: BigInt(prepared.value),
        });
      }
      setReview({
        request,
        prepared,
        community: id,
        user: user.uid,
        address: wallet.address,
      });
      setState("AWAITING_SIGNATURE");
    } catch (e) {
      setError(errorMessage(e));
      setState("FAILED");
    } finally {
      preparing.current = false;
    }
  }
  async function confirm() {
    if (!review || !wallet.provider) return;
    const r = review;
    setReview(null);
    let entry: Journal = {
      id: crypto.randomUUID(),
      user: r.user,
      community: r.community,
      address: r.address,
      chain: r.prepared.chain_id,
      action: r.request.action,
      state: "AWAITING_SIGNATURE",
      // oxlint-disable-next-line react/purity -- This async signature handler runs after a user event, never during render.
      created: new Date().toISOString(),
      track: r.request.track,
      syncPath: r.request.syncPath,
    };
    try {
      const accounts = await wallet.provider.request({
        method: "eth_accounts",
      });
      const chain = Number(
        await wallet.provider.request({ method: "eth_chainId" }),
      );
      if (
        accounts[0]?.toLowerCase() !== r.address.toLowerCase() ||
        chain !== r.prepared.chain_id ||
        user?.uid !== r.user ||
        id !== r.community
      )
        throw new Error(
          "La cuenta, red o comunidad cambió. Prepara la operación otra vez.",
        );
      const hash = await wallet.provider.request({
        method: "eth_sendTransaction",
        params: [
          {
            from: r.address,
            to: r.prepared.to as Address,
            data: r.prepared.data as Hex,
            value: `0x${BigInt(r.prepared.value).toString(16)}`,
          },
        ],
      });
      entry = { ...entry, hash, state: "SUBMITTED" };
      save(entry);
      let trackingError = false;
      if (r.request.track !== false)
        try {
          await track(entry);
        } catch {
          trackingError = true;
        }
      entry = { ...entry, state: "CONFIRMING" };
      save(entry);
      const rpc = createPublicClient({ transport: custom(wallet.provider) });
      let replaced = false;
      const receipt = await rpc.waitForTransactionReceipt({
        hash,
        confirmations: chain === 11155111 ? 3 : 1,
        timeout: 90_000,
        onReplaced: (replacement) => {
          if (replacement.reason === "repriced") {
            // oxlint-disable-next-line react/immutability -- RPC replacement events update the local async transaction journal, not render inputs.
            entry = {
              ...entry,
              previousHash: entry.hash,
              hash: replacement.transaction.hash,
            };
            save(entry);
          } else replaced = true;
        },
      });
      if (
        Number(await wallet.provider.request({ method: "eth_chainId" })) !==
        entry.chain
      )
        throw new Error(
          "La red cambió durante la confirmación. Recupera la red original y concilia el recibo.",
        );
      if (replaced) {
        save({
          ...entry,
          state: "FAILED",
          message:
            "La transacción fue cancelada o reemplazada por otra operación. No se ha confirmado la operación original.",
        });
        return;
      }
      if (receipt.status !== "success") {
        entry = {
          ...entry,
          state: "FAILED",
          message: "La transacción revirtió en el contrato.",
        };
        save(entry);
        return;
      }
      if (r.request.track !== false) {
        try {
          let result = await track(entry);
          for (
            let attempt = 0;
            attempt < 8 && result.status === "SUBMITTED";
            attempt++
          ) {
            await new Promise((resolve) => setTimeout(resolve, 1500));
            result = await track(entry);
          }
          trackingError = result.status !== "CONFIRMED";
        } catch {
          trackingError = true;
        }
      }
      if (r.request.after)
        try {
          await r.request.after(entry.hash!);
        } catch {
          trackingError = true;
        }
      entry = {
        ...entry,
        state: trackingError ? "RECONCILIATION_REQUIRED" : "CONFIRMED",
        message: trackingError
          ? "Confirmada en cadena; falta sincronizar el registro del servidor."
          : undefined,
      };
      save(entry);
      await client.invalidateQueries();
    } catch (e) {
      entry = {
        ...entry,
        state: entry.hash ? "RECONCILIATION_REQUIRED" : "FAILED",
        message: normalizeWalletError(e),
      };
      save(entry);
      setError(entry.message ?? "");
    }
  }
  async function track(entry: Journal) {
    return api<{ status: string }>(
      `${communityPath(entry.community)}/native/transactions`,
      {
        method: "POST",
        body: { transaction_hash: entry.hash, action: entry.action },
      },
    );
  }
  async function reconcile(entry: Journal) {
    setError("");
    try {
      if (
        !wallet.provider ||
        wallet.address?.toLowerCase() !== entry.address.toLowerCase() ||
        wallet.chainId !== entry.chain ||
        entry.user !== user?.uid
      )
        throw new Error("Conecta la wallet y la red de esta transacción.");
      if (!entry.hash) return;
      const rpc = createPublicClient({ transport: custom(wallet.provider) });
      const [receipt, block] = await Promise.all([
        rpc.getTransactionReceipt({ hash: entry.hash }),
        rpc.getBlockNumber(),
      ]);
      if (receipt.status === "reverted") {
        save({
          ...entry,
          state: "FAILED",
          message: "La transacción revirtió.",
        });
        return;
      }
      if (
        block - receipt.blockNumber + 1n <
        BigInt(entry.chain === 11155111 ? 3 : 1)
      )
        throw new Error("Aún faltan confirmaciones.");
      const tracked =
        entry.track === false ? { status: "CONFIRMED" } : await track(entry);
      if (entry.syncPath)
        await api(entry.syncPath, {
          method: "POST",
          body: { transaction_hash: entry.hash },
        });
      save({
        ...entry,
        state:
          tracked.status === "CONFIRMED"
            ? "CONFIRMED"
            : "RECONCILIATION_REQUIRED",
      });
      await client.invalidateQueries();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  return (
    <Context.Provider
      value={{
        state,
        begin,
        journal: journal.filter((x) => x.user === user?.uid),
        reconcile,
        error,
      }}
    >
      {children}
      <Dialog
        title="Revisar transacción"
        open={!!review}
        onClose={() => {
          setReview(null);
          setState("IDLE");
        }}
      >
        {review && (
          <>
            <p>{review.request.label}</p>
            <dl className="detail-list">
              <dt>Red</dt>
              <dd>
                {review.prepared.chain_id === 11155111
                  ? "Sepolia ETH"
                  : `Anvil ETH · ${review.prepared.chain_id}`}
              </dd>
              <dt>Wallet</dt>
              <dd>
                <code>{review.address}</code>
              </dd>
              <dt>Contrato de destino</dt>
              <dd>
                <code>{review.prepared.to}</code>
              </dd>
              <dt>Valor nativo</dt>
              <dd>{exactUnits(review.prepared.value)} ETH</dd>
              <dt>Argumentos</dt>
              <dd>
                <code>{JSON.stringify(review.request.body ?? {})}</code>
              </dd>
            </dl>
            <details>
              <summary>Datos de la llamada</summary>
              <code className="break-all">{review.prepared.data}</code>
            </details>
            <Notice>
              El gas se calcula en MetaMask. Sepolia y Anvil son redes de
              prueba; sus ETH no tienen valor monetario real.
            </Notice>
            <div className="actions">
              <button
                onClick={() => {
                  setReview(null);
                  setState("IDLE");
                }}
              >
                Cancelar
              </button>
              <button className="primary" onClick={() => void confirm()}>
                Confirmar en MetaMask
              </button>
            </div>
          </>
        )}
      </Dialog>
      {((activeState(state) && state !== "AWAITING_SIGNATURE") ||
        current ||
        error) && (
        <div className="transaction-toast" role="status">
          <Badge value={state} />
          {current?.hash && (
            <Hash value={current.hash} chainId={current.chain} />
          )}
          <p>{current?.message ?? error}</p>
          {!activeState(state) && (
            <button
              className="text-button"
              onClick={() => {
                setCurrent(null);
                setError("");
                setState("IDLE");
              }}
            >
              Cerrar
            </button>
          )}
        </div>
      )}
    </Context.Provider>
  );
}
export function normalizeWalletError(error: unknown) {
  const e = error as { code?: number; shortMessage?: string; message?: string };
  if (e.code === 4001)
    return "Cancelaste la firma en MetaMask. No se envió la transacción.";
  if (e.code === 4902) return "La red no está configurada en MetaMask.";
  if (/insufficient funds/i.test(e.message ?? ""))
    return "Saldo ETH insuficiente para el importe y el gas.";
  return e.shortMessage ?? errorMessage(error);
}
export function useTransactions() {
  const value = useContext(Context);
  if (!value) throw new Error("TransactionProvider missing");
  return value;
}
