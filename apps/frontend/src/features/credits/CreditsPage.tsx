import { useState } from "react";
import { useApi, useNativeWallet } from "../../shared/api/hooks";
import type { EnergyCreditReadModel } from "../../shared/api/models";
import {
  Page,
  Card,
  QueryState,
  Empty,
  Metric,
  Badge,
  Notice,
  Hash,
} from "../../shared/ui/components";
import { date, kwh, units } from "../../shared/utils/format";
function Issuance({ id }: { id: string }) {
  const q = useApi<{
    credit_id: string;
    status: string;
    operations: Array<{
      status: string;
      transaction_hash?: string;
      id?: string;
    }>;
  }>(`/communities/credits/${id}/issuance`);
  return (
    <QueryState query={q}>
      {q.data?.operations.length ? (
        q.data.operations.map((item, index) => (
          <div key={item.id ?? index}>
            <Badge value={item.status} />
            {item.transaction_hash ? (
              <Hash value={item.transaction_hash} />
            ) : (
              <p>Hash no expuesto por el registro.</p>
            )}
          </div>
        ))
      ) : (
        <p>
          El registro de emisión no expone una transacción para este crédito.
          Consulta el lote nativo y sus claims; no se infiere un hash.
        </p>
      )}
    </QueryState>
  );
}
export default function CreditsPage() {
  const q = useApi<EnergyCreditReadModel[]>("/energy/credits"),
    native = useNativeWallet();
  const [selected, setSelected] = useState("");
  return (
    <Page
      title="Créditos SUN"
      description="Un crédito representa energía elegible verificada. 1 SUN equivale a 1 kWh."
    >
      <div className="metrics">
        <Metric
          label="SUN en wallet"
          value={native.data ? `${units(native.data.sun_units)} SUN` : "—"}
        />
        <Metric
          label="SUN depositados"
          value={
            native.data ? `${units(native.data.escrow_sun_units)} SUN` : "—"
          }
        />
        <Metric
          label="SUN reservados"
          value={
            native.data ? `${units(native.data.reserved_sun_units)} SUN` : "—"
          }
          tone="amber"
        />
      </div>
      <Card title="Registro de créditos energéticos">
        <QueryState query={q}>
          {q.data?.length ? (
            <div className="table-wrap">
              <table>
                <caption>
                  El estado de un crédito contable y el saldo SUN en cadena son
                  registros distintos.
                </caption>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Energía elegible</th>
                    <th>SUN contables</th>
                    <th>Estado</th>
                    <th>Referencia del intervalo</th>
                    <th>Emisión</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.map((c) => (
                    <tr key={c.id}>
                      <td>{date(c.created_at)}</td>
                      <td>{kwh(c.energy_wh)}</td>
                      <td>{String(c.token_amount)} SUN</td>
                      <td>
                        <Badge value={c.status} />
                      </td>
                      <td>
                        <code>{c.interval_id}</code>
                      </td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() =>
                            setSelected(selected === c.id ? "" : c.id)
                          }
                        >
                          Ver registro
                        </button>
                        {selected === c.id && <Issuance id={c.id} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Tu primera contribución está por llegar">
              Los créditos aparecen tras evaluar intervalos energéticos. Una
              medición pendiente no es SUN emitido.
            </Empty>
          )}
        </QueryState>
      </Card>
      <Notice>
        La emisión nativa depende de lotes aprobados y finalizados. Los SUN son
        fungibles: su saldo no conserva automáticamente una procedencia
        individual. La trazabilidad se apoya en el registro de créditos, los
        intervalos y las pruebas del lote. El API actual no expone un historial
        completo de transferencias ni de retiros por evento.
      </Notice>
    </Page>
  );
}
