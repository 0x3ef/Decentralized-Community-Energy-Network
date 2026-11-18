/* oxlint-disable react/only-export-components -- Context providers intentionally export their associated hooks. */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, session, ApiError } from "../../shared/api/client";
import type { UserMeModel } from "../../shared/api/models";
interface Auth {
  user: UserMeModel | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  recover: () => Promise<void>;
}
const Context = createContext<Auth | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserMeModel | null>(null),
    [loading, setLoading] = useState(true);
  const client = useQueryClient();
  const recover = useCallback(async () => {
    await Promise.resolve();
    const version = session.version();
    if (session.access()) {
      try {
        const recovered = await api<UserMeModel>("/auth/me");
        if (session.version() === version) setUser(recovered);
      } catch (error) {
        if (
          session.version() === version &&
          error instanceof ApiError &&
          [401, 403].includes(error.status)
        )
          session.clear();
      }
    }
    if (session.version() === version || !session.access()) setLoading(false);
  }, []);
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- Asynchronous bootstrap synchronizes the external bearer session.
    void recover();
    const clear = () => {
      setUser(null);
      setLoading(false);
      client.clear();
    };
    window.addEventListener("solar:logout", clear);
    return () => window.removeEventListener("solar:logout", clear);
  }, [client, recover]);
  async function login(email: string, password: string) {
    session.clear();
    const pendingVersion = session.version();
    const tokens = await api<{ access_token: string; refresh_token: string }>(
      "/auth/login",
      { method: "POST", body: { email, password }, public: true },
    );
    if (session.version() !== pendingVersion) return;
    session.save(tokens.access_token, tokens.refresh_token);
    const version = session.version();
    try {
      const authenticated = await api<UserMeModel>("/auth/me");
      if (session.version() === version) {
        setUser(authenticated);
        setLoading(false);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (session.version() === version) session.clear();
      throw error;
    }
  }
  async function logout() {
    const revocation = api("/auth/logout", {}, false);
    session.clear();
    // Local logout must finish even when remote revocation is unavailable.
    await revocation.catch(() => undefined);
  }
  return (
    <Context.Provider value={{ user, loading, login, logout, recover }}>
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("AuthProvider missing");
  return value;
}
