import {
  useAllowances,
  useConnectedBalance,
} from "../../shared/blockchain/read-hooks";
import { Wallet, Link as LinkIcon } from "lucide-react";
import { useWallet } from "../../shared/blockchain/WalletProvider";
import { useNativeWallet } from "../../shared/api/hooks";
import { Card, Notice, Badge, Metric } from "../../shared/ui/components";
import { eth, units, short } from "../../shared/utils/format";
export function WalletPanel({ balances = false }: { balances?: boolean }) {
  const allowance = useAllowances(),
    connectedBalance = useConnectedBalance();
  const wallet = useWallet(),
    native = useNativeWallet();
  const run = (action: () => Promise<void>) => void action().catch(() => {});
  return (
    <>
      <Card>
        <div className="wallet-heading">
          <div className="card-icon">
            <Wallet />
          </div>
          <div>
            <h2>
              {wallet.address ? short(wallet.address) : "Conecta tu wallet"}
            </h2>
            <p>
              {wallet.chainId === 11155111
                ? "Sepolia ETH"
                : wallet.chainId
                  ? `Anvil ETH · red ${wallet.chainId}`
                  : "MetaMask · sin conexión"}
            </p>
          </div>
          <div className="actions">
            {!wallet.address ? (
              <button className="primary" onClick={() => run(wallet.connect)}>
                Conectar MetaMask
              </button>
            ) : (
              <>
                <Badge value={wallet.linked ? "CONFIRMED" : "PENDING"} />
                {wallet.chainId !== wallet.expectedChain && (
                  <button onClick={() => run(wallet.switchNetwork)}>
                    Cambiar de red
                  </button>
                )}
                {!wallet.linked && (
                  <button className="primary" onClick={() => run(wallet.link)}>
                    <LinkIcon size={15} /> Verificar propiedad
                  </button>
                )}
              </>
            )}
          </div>
        </div>
        {wallet.error && <Notice tone="warning">{wallet.error}</Notice>}
        {wallet.address && wallet.chainId !== wallet.expectedChain && (
          <Notice tone="warning">
            Red incorrecta. Las operaciones requieren{" "}
            {wallet.expectedChain === 11155111
              ? "Sepolia"
              : `Anvil ${wallet.expectedChain}`}
            .
          </Notice>
        )}
        <p className="fine-print">
          La sesión de la aplicación es independiente de MetaMask. La
          verificación solo firma un mensaje de propiedad; no requiere claves
          privadas.
        </p>
      </Card>
      {balances &&
        wallet.address &&
        native.data &&
        wallet.address.toLowerCase() !== native.data.address.toLowerCase() && (
          <Notice tone="warning">
            Los depósitos y créditos del servidor pertenecen a{" "}
            <code>{native.data.address}</code>. Conecta esa wallet verificada
            para operar con estos fondos.
          </Notice>
        )}
      {balances && (
        <>
          <div className="metrics">
            <Metric
              label="ETH en wallet"
              value={eth(
                connectedBalance.data?.toString() ??
                  (!wallet.address ||
                  wallet.address.toLowerCase() ===
                    native.data?.address.toLowerCase()
                    ? native.data?.wallet_wei
                    : undefined),
              )}
              hint="Saldo para depósitos y gas"
              tone="blue"
            />
            <Metric
              label="Depósito disponible"
              value={eth(native.data?.available_wei)}
              hint="Fondos retirables no reservados"
            />
            <Metric
              label="ETH reservado"
              value={eth(native.data?.reserved_wei)}
              hint="Comprometido con asignaciones"
              tone="amber"
            />
            <Metric
              label="Ingresos reclamables"
              value={eth(native.data?.earnings_wei)}
              hint="Compensación del productor"
            />
          </div>
          <div className="metrics">
            <Metric
              label="SUN en wallet"
              value={native.data ? `${units(native.data.sun_units)} SUN` : "—"}
            />
            <Metric
              label="SUN disponibles en depósito"
              value={
                native.data ? `${units(native.data.escrow_sun_units)} SUN` : "—"
              }
            />
            <Metric
              label="SUN reservados"
              value={
                native.data
                  ? `${units(native.data.reserved_sun_units)} SUN`
                  : "—"
              }
            />
            <Metric
              label="Precio de comunidad"
              value={
                native.data ? `${eth(native.data.price_wei_per_kwh)}/kWh` : "—"
              }
            />
          </div>
          <Card title="Autorizaciones SUN confirmadas">
            <dl className="detail-list">
              <dt>ETH total en depósito</dt>
              <dd>
                {native.data
                  ? eth(
                      (
                        BigInt(native.data.available_wei) +
                        BigInt(native.data.reserved_wei)
                      ).toString(),
                    )
                  : "—"}
              </dd>
              <dt>Vault · allowance SUN</dt>
              <dd>
                {allowance.data ? `${units(allowance.data.vault)} SUN` : "—"}
              </dd>
              <dt>Contrato de retiro</dt>
              <dd>
                {allowance.data
                  ? `${units(allowance.data.retirement)} SUN`
                  : "—"}
              </dd>
            </dl>
            <p className="fine-print">
              Balances del servidor para la wallet verificada:{" "}
              <code>{native.data?.address ?? "No disponible"}</code>. Las
              autorizaciones consultan la cuenta conectada en su red.
            </p>
          </Card>
          {native.isError && (
            <Notice tone="warning">
              No se pudieron consultar los balances confirmados. Revisa tu
              membresía, la wallet verificada y el despliegue de la comunidad.
            </Notice>
          )}
        </>
      )}
    </>
  );
}
