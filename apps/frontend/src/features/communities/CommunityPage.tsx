import { useState } from "react";
import { Plus, Users, MapPin } from "lucide-react";
import {
  useCommunity,
  useCommunities,
  useAction,
  useApi,
} from "../../shared/api/hooks";
import { api, communityPath } from "../../shared/api/client";
import type {
  Community,
  Policy,
  Prepared,
  Node,
} from "../../shared/api/models";
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
import { useTransactions } from "../../shared/blockchain/transactions";
import { useWallet } from "../../shared/blockchain/WalletProvider";
import { eth, errorMessage } from "../../shared/utils/format";
export default function CommunityPage() {
  const communities = useCommunities(),
    { id, select, community } = useCommunity(),
    { begin, journal } = useTransactions(),
    wallet = useWallet();
  const [create, setCreate] = useState(false),
    [message, setMessage] = useState("");
  const [pendingProposal, setPendingProposal] = useState<Prepared | null>(
    () => {
      try {
        return JSON.parse(
          sessionStorage.getItem(`solar.proposal.${id}`) ?? "null",
        ) as Prepared | null;
      } catch {
        return null;
      }
    },
  );
  const proposalConfirmed = journal.some(
    (entry) =>
      entry.community === id &&
      entry.action === "propose" &&
      entry.state === "CONFIRMED",
  );
  const signProposal = async (prepared: Prepared) =>
    begin({
      action: "propose",
      label: "Registrar propuesta de comunidad; no concede autoridad.",
      track: false,
      prepare: async () => prepared,
    });
  const proposal = useAction<Community>("/communities");
  const policy = useApi<Policy>(`${communityPath(id)}/settlement-policy`, !!id);
  const nodes = useApi<Node[]>(`${communityPath(id)}/nodes`, !!id);
  async function propose() {
    try {
      const result = await api<{
        community: Community;
        transaction: { to: string; data: string } | null;
      }>(`${communityPath(id)}/propose`, { method: "POST" });
      await communities.refetch();
      if (result.transaction) {
        const prepared = {
          ...result.transaction,
          value: "0",
          chain_id: wallet.expectedChain,
          status: "AWAITING_USER_SIGNATURE",
        };
        sessionStorage.setItem(
          `solar.proposal.${id}`,
          JSON.stringify(prepared),
        );
        setPendingProposal(prepared);
        await signProposal(prepared);
      } else
        setMessage(
          "Propuesta guardada. El registro de gobernanza aún no está configurado.",
        );
    } catch (e) {
      setMessage(errorMessage(e));
    }
  }
  async function apply(data: FormData) {
    const target = String(data.get("community_id"));
    try {
      await api(`${communityPath(target)}/memberships/apply`, {
        method: "POST",
      });
      setMessage(
        "Solicitud pendiente registrada. La gobernanza debe autorizar la membresía en cadena.",
      );
      if (wallet.linked)
        await begin({
          action: "apply_membership",
          label: "Solicitar membresía en el registro de la comunidad.",
          track: false,
          prepare: () =>
            api<Prepared>(`${communityPath(target)}/governance/prepare`, {
              method: "POST",
              body: { action: "apply_membership" },
            }),
        });
    } catch (e) {
      setMessage(errorMessage(e));
    }
  }
  return (
    <Page
      title="Mi comunidad"
      description="Personas e infraestructura conectadas por reglas verificables."
      action={
        <button className="primary" onClick={() => setCreate(!create)}>
          <Plus size={17} /> Proponer comunidad
        </button>
      }
    >
      {message && <Notice>{message}</Notice>}
      {create && (
        <Card title="Nueva propuesta">
          <Form
            onSubmit={async (data) => {
              try {
                const row = await proposal.mutateAsync({
                  name: data.get("name"),
                  boundary_description: data.get("boundary_description"),
                  topology: "SIMULATED_GRID_CONNECTED",
                  interval_seconds: 900,
                  allow_simulated_telemetry: data.get("simulation") === "on",
                  sun_per_kwh: "1",
                  loss_factor: "0",
                });
                select(row.id);
                setCreate(false);
              } catch (e) {
                setMessage(errorMessage(e));
              }
            }}
          >
            <Field label="Nombre">
              <input name="name" required maxLength={100} />
            </Field>
            <Field label="Límite físico de la comunidad">
              <textarea name="boundary_description" required />
            </Field>
            <label className="check">
              <input type="checkbox" name="simulation" /> Permitir telemetría
              simulada claramente identificada
            </label>
            <Notice>
              La propuesta comienza en borrador. Solo la gobernanza autorizada
              puede aprobar y activar comunidades.
            </Notice>
            <button className="primary" disabled={proposal.isPending}>
              Guardar propuesta
            </button>
          </Form>
        </Card>
      )}
      <QueryState query={communities}>
        {communities.data?.length ? (
          <div className="community-grid">
            {communities.data.map((c) => (
              <button
                className={`community-card ${c.id === id ? "selected" : ""}`}
                key={c.id}
                onClick={() => select(c.id)}
              >
                <Users size={24} />
                <Badge value={c.status} />
                <h2>{c.name}</h2>
                <p>{c.boundary_description || "Sin descripción territorial"}</p>
                <span>
                  <MapPin size={14} /> Intervalos de {c.interval_seconds / 60}{" "}
                  min
                </span>
              </button>
            ))}
          </div>
        ) : (
          <Card>
            <Empty title="Tu comunidad empieza aquí">
              Propón una comunidad o solicita acceso con su identificador.
            </Empty>
          </Card>
        )}
      </QueryState>
      {community && (
        <div className="two-col">
          <Card title="Estado y reglas">
            <Badge value={community.status} />
            <dl className="detail-list">
              <dt>Identificador</dt>
              <dd>
                <code>{id}</code>
              </dd>
              <dt>Topología</dt>
              <dd>{community.topology}</dd>
              <dt>Conversión SUN</dt>
              <dd>1 SUN = 1 kWh elegible verificado</dd>
              <dt>Fuentes simuladas</dt>
              <dd>
                {community.allow_simulated_telemetry
                  ? "Permitidas e identificadas"
                  : "No admitidas"}
              </dd>
              <dt>Compromiso de política</dt>
              <dd>
                <code>{community.policy_hash ?? "Pendiente de propuesta"}</code>
              </dd>
            </dl>
            {community.status === "DRAFT" && (
              <button className="primary" onClick={() => void propose()}>
                Enviar propuesta al registro
              </button>
            )}
            {pendingProposal && !proposalConfirmed && (
              <button
                className="primary"
                onClick={() => void signProposal(pendingProposal)}
              >
                Firmar propuesta pendiente
              </button>
            )}
            <button
              onClick={async () => {
                try {
                  await api(`${communityPath(id)}/memberships/sync`, {
                    method: "POST",
                  });
                  await communities.refetch();
                  setMessage("Membresía sincronizada con el registro.");
                } catch (e) {
                  setMessage(errorMessage(e));
                }
              }}
            >
              Sincronizar mi membresía
            </button>
          </Card>
          <Card title="Política de liquidación">
            <QueryState query={policy}>
              {policy.data && (
                <dl className="detail-list">
                  <dt>Precio</dt>
                  <dd>{eth(policy.data.price_wei_per_kwh)}/kWh</dd>
                  <dt>Intervalo</dt>
                  <dd>{policy.data.interval_seconds / 60} minutos</dd>
                  <dt>Versión</dt>
                  <dd>
                    <code>{policy.data.id}</code>
                  </dd>
                  <dt>Referencia de gobernanza</dt>
                  <dd>
                    <code>{policy.data.governance_reference}</code>
                  </dd>
                </dl>
              )}
            </QueryState>
            <h3>Nodos de la comunidad</h3>
            <QueryState query={nodes}>
              {nodes.data?.length ? (
                <ul className="plain-list">
                  {nodes.data.map((n) => (
                    <li key={n.id}>
                      <code>{n.id}</code>
                      <Badge value={n.authorized ? "APPROVED" : "PENDING"} />
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="Sin nodos registrados" />
              )}
            </QueryState>
          </Card>
        </div>
      )}
      <Card title="Solicitar membresía">
        <p>
          El servicio muestra tus comunidades activas y propuestas propias. El
          directorio público y el listado de solicitudes pendientes todavía no
          están disponibles.
        </p>
        <Form onSubmit={apply}>
          <Field
            label="Identificador de comunidad"
            hint="Pide el UUID a la persona que coordina tu comunidad."
          >
            <input
              name="community_id"
              required
              pattern="[0-9a-fA-F-]{36}"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
          </Field>
          <button className="primary">Registrar solicitud</button>
        </Form>
      </Card>
    </Page>
  );
}
