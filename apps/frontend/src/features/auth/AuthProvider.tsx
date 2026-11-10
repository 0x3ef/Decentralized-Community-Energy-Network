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
import { api, session } from "../../shared/api/client";
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
    if (session.access()) {
      try {
        setUser(await api<UserMeModel>("/auth/me"));
      } catch {
        session.clear();
        setUser(null);
      }
    }
    setLoading(false);
  }, []);
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- Asynchronous bootstrap synchronizes the external bearer session.
    void recover();
    const clear = () => {
      setUser(null);
      client.clear();
    };
    window.addEventListener("solar:logout", clear);
    return () => window.removeEventListener("solar:logout", clear);
  }, [client, recover]);
  async function login(email: string, password: string) {
    const tokens = await api<{ access_token: string; refresh_token: string }>(
      "/auth/login",
      { method: "POST", body: { email, password }, public: true },
    );
    session.save(tokens.access_token, tokens.refresh_token);
    try {
      setUser(await api<UserMeModel>("/auth/me"));
      setLoading(false);
    } catch (error) {
      session.clear();
      throw error;
    }
  }
  async function logout() {
    try {
      await api("/auth/logout");
    } finally {
      session.clear();
      setUser(null);
      client.clear();
    }
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
