import { useState } from "react";
import { useApi, useCommunity } from "../../shared/api/hooks";
import { communityPath } from "../../shared/api/client";
import type { NativeTransaction } from "../../shared/api/models";
import { useTransactions } from "../../shared/blockchain/transactions";
import {
  Page,
  Card,
  QueryState,
  Empty,
  Badge,
  Hash,
  Notice,
} from "../../shared/ui/components";
import { date } from "../../shared/utils/format";
export default function TransactionsPage() {
  const { id } = useCommunity(),
    tx = useTransactions();
  const [offset, setOffset] = useState(0);
  const q = useApi<NativeTransaction[]>(
    `${communityPath(id)}/native/transactions?limit=20&offset=${offset}`,
    !!id,
    true,
  );
  const local = tx.journal.filter((e) => e.community === id);
  return (
    <Page
      title="Transacciones"
      description="Firmas, confirmaciones y conciliación de tu actividad en el protocolo."
    >
      <Card title="Actividad de esta sesión y dispositivo">
        {local.length ? (
          <ul className="plain-list">
            {local.map((e) => (
              <li key={e.id}>
                <div>
                  <strong>{e.action}</strong>
                  <p>
                    {date(e.created)} · red {e.chain}
                  </p>
                  {e.hash && <Hash value={e.hash} chainId={e.chain} />}
                  <p>{e.message}</p>
                  {e.previousHash && (
                    <p>
                      Hash reemplazado: <code>{e.previousHash}</code>
                    </p>
                  )}
                </div>
                <Badge value={e.state} />
                {[
                  "RECONCILIATION_REQUIRED",
                  "SUBMITTED",
                  "CONFIRMING",
                ].includes(e.state) && (
                  <button onClick={() => void tx.reconcile(e)}>
                    Comprobar recibo y conciliar
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="Sin operaciones locales" />
        )}
      </Card>
      <Card title="Registro del servidor">
        <QueryState query={q}>
          {q.data?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Operación</th>
                    <th>Transacción</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.map((e) => (
                    <tr key={e.id}>
                      <td>{date(e.created_at)}</td>
                      <td>{e.action}</td>
                      <td>
                        <Hash value={e.transaction_hash} chainId={e.chain_id} />
                      </td>
                      <td>
                        <Badge value={e.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Sin transacciones registradas" />
          )}
        </QueryState>
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset((v) => Math.max(0, v - 20))}
          >
            Anterior
          </button>
          <button
            disabled={(q.data?.length ?? 0) < 20}
            onClick={() => setOffset((v) => v + 20)}
          >
            Siguiente
          </button>
        </div>
      </Card>
      <Notice>
        Enviado no equivale a confirmado. Sepolia requiere tres confirmaciones
        en esta interfaz; Anvil, una. Los hashes de Anvil se consultan en su RPC
        local porque no hay explorador público.
      </Notice>
    </Page>
  );
}
