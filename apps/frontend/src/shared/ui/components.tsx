import {
  Component,
  useEffect,
  useRef,
  useId,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
  type ErrorInfo,
  type FormEvent,
} from "react";
import { AlertTriangle, ArrowUpRight, Inbox, LoaderCircle } from "lucide-react";
import { statusLabel } from "./i18n";
import { errorMessage } from "../utils/format";
export function Page({
  eyebrow = "COMUNIDAD · ENERGÍA · CONFIANZA",
  title,
  description,
  children,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p className="description">{description}</p>
        </div>
        {action}
      </header>
      {children}
    </>
  );
}
export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "warning" | "success";
}) {
  return (
    <div
      className={`notice ${tone}`}
      role={tone === "warning" ? "alert" : "status"}
    >
      <AlertTriangle size={18} />
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  title = "Todavía no hay datos",
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={30} />
      <h3>{title}</h3>
      <p>
        {children ??
          "Los datos aparecerán cuando el protocolo confirme actividad."}
      </p>
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  return (
    <span
      className={`badge ${["ACTIVE", "VALID", "CONFIRMED", "FINALIZED", "SETTLED", "PHYSICAL", "ISSUED"].includes(value) ? "green" : ["FAILED", "REJECTED", "SUSPENDED", "DISABLED"].includes(value) ? "red" : "amber"}`}
    >
      {statusLabel(value)}
    </span>
  );
}
export function Metric({
  label,
  value,
  hint,
  tone = "green",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: string;
}) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint ?? "Información confirmada por el protocolo"}</small>
    </div>
  );
}
export function QueryState({
  query,
  children,
}: {
  query: {
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
  };
  children: ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="loading" role="status">
        <LoaderCircle className="spin" size={20} /> Consultando datos…
      </div>
    );
  if (query.isError)
    return (
      <Notice tone="warning">
        {errorMessage(query.error)}{" "}
        <button className="text-button" onClick={() => query.refetch()}>
          Reintentar
        </button>
      </Notice>
    );
  return <>{children}</>;
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {isValidElement(children)
        ? cloneElement(
            children as ReactElement<{
              id: string;
              "aria-describedby"?: string;
            }>,
            { id, "aria-describedby": hint ? `${id}-hint` : undefined },
          )
        : children}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
export function Form({
  onSubmit,
  children,
}: {
  onSubmit: (data: FormData) => void | Promise<void>;
  children: ReactNode;
}) {
  return (
    <form
      className="form-grid"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        void onSubmit(new FormData(event.currentTarget));
      }}
    >
      {children}
    </form>
  );
}
export function Dialog({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (open && !el?.open) el?.showModal();
    if (!open && el?.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog-heading">
        <h2 id="dialog-title">{title}</h2>
        <button
          aria-label="Cerrar diálogo"
          className="icon-button"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Hash({ value, chainId }: { value: string; chainId?: number }) {
  return (
    <span className="hash" title={value}>
      {chainId === 11155111 ? (
        <a
          href={`https://sepolia.etherscan.io/tx/${value}`}
          target="_blank"
          rel="noreferrer"
        >
          {value.slice(0, 10)}…{value.slice(-6)} <ArrowUpRight size={12} />
        </a>
      ) : (
        <code>{value}</code>
      )}{" "}
      <button
        className="text-button"
        aria-label="Copiar referencia"
        onClick={() => void navigator.clipboard?.writeText(value)}
      >
        Copiar
      </button>
    </span>
  );
}
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* Do not log session or wallet data. */
  }
  render() {
    return this.state.error ? (
      <main className="auth-main">
        <Card title="No se pudo mostrar esta pantalla">
          <p>Recarga la aplicación para recuperar la sesión.</p>
          <button onClick={() => window.location.reload()}>Recargar</button>
        </Card>
      </main>
    ) : (
      this.props.children
    );
  }
}

export function Pagination({
  offset,
  count,
  onChange,
  pageSize = 20,
  label = "Páginas",
}: {
  offset: number;
  count: number;
  onChange: (offset: number) => void;
  pageSize?: number;
  label?: string;
}) {
  return (
    <nav className="pagination" aria-label={label}>
      <button
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - pageSize))}
      >
        Anterior
      </button>
      <span>Página {offset / pageSize + 1}</span>
      <button
        disabled={count < pageSize}
        onClick={() => onChange(offset + pageSize)}
      >
        Siguiente
      </button>
    </nav>
  );
}
