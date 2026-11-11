import { useState } from "react";
import { Sun, ArrowRight, ShieldCheck, Leaf } from "lucide-react";
import { useAuth } from "./AuthProvider";
import { api } from "../../shared/api/client";
import { Field, Form, Notice } from "../../shared/ui/components";
import { errorMessage } from "../../shared/utils/format";
export default function AuthPage() {
  const { login } = useAuth();
  const [register, setRegister] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(data: FormData) {
    setError("");
    setBusy(true);
    try {
      const fields = Object.fromEntries(data);
      if (register)
        await api("/auth/signup", {
          method: "POST",
          public: true,
          body: fields,
        });
      await login(String(fields.email), String(fields.password));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <aside className="auth-story">
        <div className="brand">
          <Sun />
          <span>
            solar<span className="brand-small">ENERGY MARKET</span>
          </span>
        </div>
        <div>
          <p className="eyebrow">EL FUTURO ES COMUNITARIO</p>
          <h1>
            Tu energía.
            <br />
            Nuestra comunidad.
          </h1>
          <p>
            Conecta tu hogar a una red de energía solar verificada, transparente
            y compartida.
          </p>
          <div className="auth-orbit">
            <Sun size={100} />
            <span>
              <Leaf /> Energía con propósito
            </span>
          </div>
        </div>
        <p className="auth-foot">
          <ShieldCheck size={18} /> Infraestructura real. Evidencia verificable.
        </p>
      </aside>
      <main className="auth-main">
        <div className="auth-form">
          <span className="badge green">PLATAFORMA DePIN</span>
          <h1>{register ? "Comienza a conectar" : "Bienvenido de nuevo"}</h1>
          <p className="description">
            {register
              ? "Crea tu cuenta para participar en una comunidad energética."
              : "Accede a tu comunidad y sigue el recorrido de tu energía."}
          </p>
          {error && <Notice tone="warning">{error}</Notice>}
          <Form onSubmit={submit}>
            {register && (
              <>
                <Field label="Nombre">
                  <input
                    name="first_name"
                    autoComplete="given-name"
                    maxLength={25}
                    required
                  />
                </Field>
                <Field label="Apellido">
                  <input
                    name="last_name"
                    autoComplete="family-name"
                    maxLength={25}
                    required
                  />
                </Field>
                <Field label="Nombre de usuario">
                  <input
                    name="username"
                    autoComplete="username"
                    maxLength={8}
                    required
                  />
                </Field>
              </>
            )}
            <Field label="Correo electrónico">
              <input
                name="email"
                type="email"
                autoComplete="email"
                maxLength={40}
                required
                placeholder="tu@correo.com"
              />
            </Field>
            <Field label="Contraseña">
              <input
                name="password"
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                minLength={6}
                maxLength={72}
                required
                placeholder="Tu contraseña"
              />
            </Field>
            <button disabled={busy} className="primary">
              {busy
                ? "Conectando…"
                : register
                  ? "Crear cuenta"
                  : "Iniciar sesión"}
              <ArrowRight size={18} />
            </button>
          </Form>
          <p>
            {register ? "¿Ya tienes una cuenta?" : "¿Primera vez aquí?"}{" "}
            <button
              className="text-button"
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Inicia sesión" : "Crea tu cuenta"}
            </button>
          </p>
          <p className="fine-print">
            La cuenta de la aplicación y tu wallet se verifican por separado.
            Nunca solicitamos claves privadas.
          </p>
        </div>
      </main>
    </div>
  );
}
