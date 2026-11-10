import { useState } from "react";
import { Home as HomeIcon, Plus, Sun } from "lucide-react";
import { useHomes, useAction, useDevices } from "../../shared/api/hooks";
import {
  Page,
  Card,
  Field,
  Form,
  QueryState,
  Empty,
  Badge,
  Notice,
} from "../../shared/ui/components";
import { api } from "../../shared/api/client";
import { errorMessage } from "../../shared/utils/format";
import type { Home } from "../../shared/api/models";
function HomeEditor({ home, done }: { home?: Home; done: () => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Card title={home ? "Editar hogar" : "Registrar hogar"}>
      <Form
        onSubmit={async (data) => {
          setBusy(true);
          setError("");
          try {
            const body = {
              ...Object.fromEntries(data),
              installed_capacity_w: Number(data.get("installed_capacity_w")),
              has_battery: data.get("has_battery") === "on",
            };
            await api(home ? `/home/${home.id}` : "/home/", {
              method: home ? "PATCH" : "POST",
              body,
            });
            done();
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Nombre">
          <input
            name="name"
            defaultValue={home?.name}
            maxLength={100}
            required
          />
        </Field>
        <Field label="Dirección">
          <input
            name="address"
            defaultValue={home?.address}
            minLength={3}
            maxLength={255}
            required
          />
        </Field>
        <Field label="Ciudad">
          <input name="city" defaultValue={home?.city} required />
        </Field>
        <Field label="País">
          <input
            name="country"
            defaultValue={home?.country ?? "Colombia"}
            required
          />
        </Field>
        <Field label="Zona horaria">
          <input
            name="timezone"
            defaultValue={home?.timezone ?? "America/Bogota"}
            required
          />
        </Field>
        <Field label="Capacidad solar instalada (W)">
          <input
            name="installed_capacity_w"
            type="number"
            defaultValue={home?.installed_capacity_w ?? 0}
            min={0}
            step={1}
            required
          />
        </Field>
        <label className="check">
          <input
            name="has_battery"
            type="checkbox"
            defaultChecked={home?.has_battery}
          />{" "}
          Tiene batería
        </label>
        {error && <Notice tone="warning">{error}</Notice>}
        <div className="actions">
          <button type="button" onClick={done}>
            Cancelar
          </button>
          <button className="primary" disabled={busy}>
            Guardar hogar
          </button>
        </div>
      </Form>
    </Card>
  );
}
export default function HomesPage() {
  const homes = useHomes();
  const [editing, setEditing] = useState<Home | "new" | null>(null);
  return (
    <Page
      title="Mis hogares"
      description="Cada hogar es el punto de partida de tu infraestructura energética."
      action={
        <button className="primary" onClick={() => setEditing("new")}>
          <Plus size={17} /> Registrar hogar
        </button>
      }
    >
      {editing && (
        <HomeEditor
          home={editing === "new" ? undefined : editing}
          done={() => {
            setEditing(null);
            void homes.refetch();
          }}
        />
      )}
      <QueryState query={homes}>
        {homes.data?.homes.length ? (
          <div className="community-grid">
            {homes.data.homes.map((h) => (
              <Card key={h.id}>
                <div className="card-icon">
                  <HomeIcon />
                </div>
                <h2>{h.name}</h2>
                <p>
                  {h.address} · {h.city}
                </p>
                <Badge value={h.status} />
                <dl className="detail-list">
                  <dt>
                    <Sun size={15} /> Capacidad instalada
                  </dt>
                  <dd>{h.installed_capacity_w.toLocaleString("es-CO")} W</dd>
                  <dt>Almacenamiento</dt>
                  <dd>{h.has_battery ? "Con batería" : "Sin batería"}</dd>
                  <dt>Zona horaria</dt>
                  <dd>{h.timezone}</dd>
                </dl>
                <button onClick={() => setEditing(h)}>
                  Ver y editar hogar
                </button>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <Empty title="Un hogar, muchas posibilidades">
              Registra tu hogar para conectar medidores y consultar energía
              verificada.
            </Empty>
          </Card>
        )}
      </QueryState>
    </Page>
  );
}
export function DeviceRegistration({
  homeId,
  onDone,
}: {
  homeId: string;
  onDone: () => void;
}) {
  const action = useAction("/device/device");
  const devices = useDevices(homeId);
  return (
    <Card title="Registrar dispositivo">
      <Form
        onSubmit={async (data) => {
          try {
            await action.mutateAsync({
              ...Object.fromEntries(data),
              home_id: homeId,
              mqtt_client_id: String(data.get("mqtt_client_id")),
            });
            await devices.refetch();
            onDone();
          } catch {
            /* Render mutation error below. */
          }
        }}
      >
        <Field label="Código del dispositivo">
          <input name="device_code" maxLength={100} required />
        </Field>
        <Field label="Tipo">
          <select name="device_type">
            <option value="SMART_METER">Medidor inteligente</option>
            <option value="INVERTER">Inversor solar</option>
            <option value="BATTERY">Batería</option>
            <option value="WEATHER_SENSOR">Sensor meteorológico</option>
          </select>
        </Field>
        <Field label="Fuente">
          <select name="telemetry_source">
            <option value="PHYSICAL">Física</option>
            <option value="SIMULATED">Simulada</option>
          </select>
        </Field>
        <Field
          label="Identificador MQTT"
          hint="Identidad única configurada en el dispositivo o simulador."
        >
          <input name="mqtt_client_id" required maxLength={150} />
        </Field>
        <Field label="Fabricante">
          <input name="manufacturer" />
        </Field>
        <Notice>
          El registro queda pendiente. La autorización del nodo y medidor
          requiere gobernanza y un operador autorizado.
        </Notice>
        {action.error && (
          <Notice tone="warning">{errorMessage(action.error)}</Notice>
        )}
        <button className="primary" disabled={action.isPending}>
          Registrar dispositivo pendiente
        </button>
      </Form>
    </Card>
  );
}
