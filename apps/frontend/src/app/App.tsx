import { SystemStatus } from "../features/settings/SystemStatus";
import { lazy, Suspense, useState, useEffect, useRef } from "react";
import {
  BrowserRouter,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Sun,
  LayoutDashboard,
  Users,
  House,
  Radio,
  Activity,
  Leaf,
  Layers,
  ArrowDownUp,
  ShieldCheck,
  History,
  Settings,
  LogOut,
  Menu,
  X,
  Moon,
  ChevronDown,
  Wallet,
} from "lucide-react";
import { AuthProvider, useAuth } from "../features/auth/AuthProvider";
import AuthPage from "../features/auth/AuthPage";
import {
  CommunityProvider,
  useCommunity,
  useCommunities,
} from "../shared/api/hooks";
import {
  WalletProvider,
  useRoles,
  useWallet,
} from "../shared/blockchain/WalletProvider";
import { TransactionProvider } from "../shared/blockchain/transactions";
import { Card, Page, Notice, ErrorBoundary } from "../shared/ui/components";
import { t } from "../shared/ui/i18n";
import { short, date } from "../shared/utils/format";
const Dashboard = lazy(() => import("../features/dashboard/DashboardPage")),
  Communities = lazy(() => import("../features/communities/CommunityPage")),
  Homes = lazy(() => import("../features/homes/HomesPage")),
  Devices = lazy(() => import("../features/energy/DevicesPage")),
  Energy = lazy(() => import("../features/energy/EnergyPage")),
  Credits = lazy(() => import("../features/credits/CreditsPage")),
  Settlement = lazy(() => import("../features/settlement/SettlementPage")),
  Detail = lazy(() =>
    import("../features/settlement/SettlementPage").then((m) => ({
      default: m.SettlementDetail,
    })),
  ),
  Deposits = lazy(() => import("../features/wallet/DepositsPage")),
  Compensation = lazy(() => import("../features/credits/CompensationPage")),
  Transactions = lazy(() => import("../features/wallet/TransactionsPage")),
  Governance = lazy(() => import("../features/governance/GovernancePage"));
const navigation = [
  ["/", "overview", LayoutDashboard],
  ["/comunidad", "community", Users],
  ["/hogares", "homes", House],
  ["/dispositivos", "devices", Radio],
  ["/energia", "energy", Activity],
  ["/creditos", "credits", Leaf],
  ["/liquidacion", "settlement", Layers],
  ["/depositos", "deposits", ArrowDownUp],
  ["/compensacion", "compensation", ShieldCheck],
  ["/transacciones", "transactions", History],
] as const;
function SettingsPage() {
  const { user } = useAuth();
  return (
    <Page
      title="Configuración"
      description="Tu cuenta, preferencias y capacidades del despliegue."
    >
      <SystemStatus />
      <Card title="Perfil de cuenta">
        <dl className="detail-list">
          <dt>Nombre</dt>
          <dd>
            {user?.first_name} {user?.last_name}
          </dd>
          <dt>Usuario</dt>
          <dd>{user?.username}</dd>
          <dt>Correo</dt>
          <dd>{user?.email}</dd>
          <dt>Registro</dt>
          <dd>{date(user?.created_at)}</dd>
        </dl>
        <Notice>
          El API actual ofrece lectura del perfil. La edición del perfil aún no
          está disponible.
        </Notice>
      </Card>
      <Card title="Idioma y zona horaria">
        <p>
          Español · fechas en America/Bogota. Las consultas energéticas envían
          tiempos UTC al servidor.
        </p>
      </Card>
      <Card title="Capacidades del protocolo">
        <p>
          Comunidades, telemetría, créditos SUN, liquidación en ETH nativo y
          retiro contra consumo elegible.
        </p>
        <Notice>
          El marketplace P2P con ETH nativo no está soportado por los contratos
          actuales. El directorio público, el manifiesto completo de evidencia y
          el historial SUN por evento requieren ampliar el API.
        </Notice>
      </Card>
    </Page>
  );
}
function Shell() {
  const { user, logout } = useAuth(),
    { id, select } = useCommunity(),
    communities = useCommunities(),
    wallet = useWallet(),
    roles = useRoles();
  const [mobilePath, setMobilePath] = useState<string | null>(null),
    [dark, setDark] = useState(
      () => localStorage.getItem("solar.theme") === "dark",
    );
  const location = useLocation();
  const mobile = mobilePath === location.pathname;
  const asideRef = useRef<HTMLElement>(null),
    menuRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!mobile) return;
    const menuButton = menuRef.current;
    asideRef.current?.querySelector<HTMLAnchorElement>("a")?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobilePath(null);
        return;
      }
      if (event.key === "Tab") {
        const items = Array.from(
          asideRef.current?.querySelectorAll<HTMLElement>("a,button") ?? [],
        ).filter((el) => el.offsetParent !== null);
        const first = items[0],
          last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      menuButton?.focus();
    };
  }, [mobile]);
  const setMobile = (open: boolean) =>
    setMobilePath(open ? location.pathname : null);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("solar.theme", dark ? "dark" : "light");
  }, [dark]);
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Saltar al contenido
      </a>
      {mobile && (
        <button
          aria-label="Cerrar navegación"
          className="sidebar-overlay"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        ref={asideRef}
        role={mobile ? "dialog" : undefined}
        aria-modal={mobile ? true : undefined}
        aria-label="Menú principal"
        className={`sidebar ${mobile ? "open" : ""}`}
      >
        <NavLink to="/" className="brand">
          <div className="brand-mark">
            <Sun size={27} />
          </div>
          <span>
            solar<span className="brand-small">ENERGY MARKET</span>
          </span>
        </NavLink>
        <button
          className="mobile-close icon-button"
          aria-label="Cerrar menú"
          onClick={() => setMobile(false)}
        >
          <X />
        </button>
        <p className="nav-label">ESPACIO COMUNITARIO</p>
        <nav aria-label="Navegación principal">
          {navigation.map(([path, label, Icon]) => (
            <NavLink key={path} to={path} end={path === "/"}>
              <Icon size={18} />
              <span>{t(label)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <p className="nav-label">ADMINISTRACIÓN</p>
          <nav aria-label="Navegación secundaria">
            {roles.data?.governance && (
              <NavLink to="/gobernanza" onClick={() => setMobile(false)}>
                <ShieldCheck size={18} />
                {t("governance")}
              </NavLink>
            )}
            <NavLink to="/configuracion" onClick={() => setMobile(false)}>
              <Settings size={18} />
              {t("settings")}
            </NavLink>
          </nav>
          <div className="network-note">
            <span className="live-dot" />
            <span>
              {wallet.expectedChain === 11155111 ? "Sepolia" : "Anvil"} · Red de
              prueba<small>ETH sin valor monetario real</small>
            </span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            ref={menuRef}
            aria-expanded={mobile}
            aria-label="Abrir menú"
            onClick={() => setMobile(true)}
          >
            <Menu />
          </button>
          <div className="community-switch">
            <span className="community-avatar">
              <Users size={17} />
            </span>
            <label className="sr-only" htmlFor="community-select">
              Comunidad activa
            </label>
            <select
              id="community-select"
              value={id}
              onChange={(e) => select(e.target.value)}
            >
              <option value="" disabled>
                Selecciona tu comunidad
              </option>
              {communities.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          <div className="topbar-actions">
            <button
              className="icon-button"
              onClick={() => setDark(!dark)}
              aria-label={dark ? "Activar tema claro" : "Activar tema oscuro"}
            >
              <Moon size={18} />
            </button>
            <button
              className="wallet-button"
              onClick={() => void wallet.connect().catch(() => {})}
            >
              <Wallet size={16} />
              <span>
                {wallet.address ? short(wallet.address) : "Conectar wallet"}
              </span>
            </button>
            <span
              className="user-avatar"
              title={`${user?.first_name} ${user?.last_name}`}
            >
              {user?.first_name?.slice(0, 1)}
              {user?.last_name?.slice(0, 1)}
            </span>
            <button
              className="icon-button"
              aria-label="Cerrar sesión"
              onClick={() => void logout()}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1} key={user?.uid}>
          <Suspense
            fallback={
              <div className="loading" role="status">
                Cargando pantalla…
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/comunidad" element={<Communities key={id} />} />
              <Route path="/hogares" element={<Homes />} />
              <Route path="/dispositivos" element={<Devices />} />
              <Route path="/energia" element={<Energy />} />
              <Route path="/creditos" element={<Credits />} />
              <Route path="/liquidacion" element={<Settlement key={id} />} />
              <Route
                path="/liquidacion/:batchId"
                element={<Detail key={`${id}:${location.pathname}`} />}
              />
              <Route path="/depositos" element={<Deposits />} />
              <Route path="/compensacion" element={<Compensation key={id} />} />
              <Route
                path="/transacciones"
                element={<Transactions key={id} />}
              />
              <Route path="/gobernanza" element={<Governance key={id} />} />
              <Route path="/configuracion" element={<SettingsPage />} />
              <Route
                path="*"
                element={
                  <Page
                    title="Página no encontrada"
                    description="Selecciona una sección del menú para continuar."
                  >
                    <NavLink to="/">Ir al resumen</NavLink>
                  </Page>
                }
              />
            </Routes>
          </Suspense>
        </main>
        <footer className="app-footer">
          <span>
            Solar Energy Market · Infraestructura energética comunitaria
          </span>
          <span>Medir. Compartir. Verificar.</span>
        </footer>
      </div>
    </div>
  );
}
function SessionGate() {
  const { loading, user } = useAuth();
  if (loading)
    return (
      <div className="loading full-height" role="status">
        Recuperando tu sesión…
      </div>
    );
  return user ? (
    <CommunityProvider>
      <WalletProvider>
        <TransactionProvider>
          <Shell />
        </TransactionProvider>
      </WalletProvider>
    </CommunityProvider>
  ) : (
    <AuthPage />
  );
}
const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});
export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <SessionGate />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
