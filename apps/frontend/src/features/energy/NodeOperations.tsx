import { useState } from "react";
import { useApi, useCommunity } from "../../shared/api/hooks";
import { api, communityPath } from "../../shared/api/client";
import type { Node } from "../../shared/api/models";
import {
  Card,
  Form,
  Field,
  Notice,
  QueryState,
  Badge,
  Empty,
} from "../../shared/ui/components";
import { errorMessage } from "../../shared/utils/format";
export function NodeOperations() {
  const { id } = useCommunity();
  const nodes = useApi<Node[]>(`${communityPath(id)}/nodes`, !!id);
  const [message, setMessage] = useState("");
  return (
    <Card title="Nodos y autorización de medidores · operador">
      <QueryState query={nodes}>
        {nodes.data?.length ? (
          <ul className="plain-list">
            {nodes.data.map((node) => (
              <li key={node.id}>
                <div>
                  <code>{node.id}</code>
                  <p>Hogar: {node.home_id}</p>
                </div>
                <Badge value={node.authorized ? "APPROVED" : "PENDING"} />
                <button
                  onClick={async () => {
                    try {
                      await api(
                        `/communities/nodes/${node.id}/governance/sync`,
                        { method: "POST" },
                      );
                      await nodes.refetch();
                      setMessage("Nodo sincronizado con el registro.");
                    } catch (e) {
                      setMessage(errorMessage(e));
                    }
                  }}
                >
                  Sincronizar nodo
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="Sin nodos registrados" />
        )}
      </QueryState>
      <Form
        onSubmit={async (data) => {
          try {
            await api(`/communities/nodes/${data.get("node")}/meters`, {
              method: "POST",
              body: {
                device_id: data.get("device"),
                credential: data.get("credential"),
              },
            });
            setMessage(
              "Autorización operativa de medidor registrada. Guarda la credencial en el dispositivo.",
            );
          } catch (e) {
            setMessage(errorMessage(e));
          }
        }}
      >
        <Field label="Nodo autorizado">
          <select name="node" required>
            <option value="">Selecciona un nodo</option>
            {nodes.data
              ?.filter((n) => n.authorized)
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {n.id}
                </option>
              ))}
          </select>
        </Field>
        <Field label="UUID interno del dispositivo">
          <input name="device" required pattern="[a-fA-F0-9-]{36}" />
        </Field>
        <Field
          label="Credencial del medidor"
          hint="Se usa para autenticar telemetría. No es una clave privada de wallet."
        >
          <input
            name="credential"
            type="password"
            minLength={16}
            maxLength={200}
            autoComplete="off"
            required
          />
        </Field>
        <Notice>
          La gobernanza debe autorizar primero el nodo y el medidor en cadena.
          Este formulario registra la credencial operativa después de esa
          comprobación.
        </Notice>
        <button className="primary">Registrar credencial de medidor</button>
      </Form>
      {message && <Notice>{message}</Notice>}
    </Card>
  );
}
