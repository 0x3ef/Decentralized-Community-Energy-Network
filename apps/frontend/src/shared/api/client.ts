import { localizedApiError } from "./errors";
const base = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
export class ApiError extends Error {
  status: number;
  detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}
export const session = {
  access: () => sessionStorage.getItem("solar.access"),
  refresh: () => sessionStorage.getItem("solar.refresh"),
  save: (access: string, refresh?: string) => {
    sessionStorage.setItem("solar.access", access);
    if (refresh) sessionStorage.setItem("solar.refresh", refresh);
  },
  clear: () => {
    sessionStorage.removeItem("solar.access");
    sessionStorage.removeItem("solar.refresh");
    window.dispatchEvent(new Event("solar:logout"));
  },
};
let refreshFlight: Promise<void> | null = null;
async function refreshSession() {
  if (!refreshFlight)
    refreshFlight = (async () => {
      const token = session.refresh();
      if (!token) {
        session.clear();
        throw new ApiError(
          401,
          "Tu sesión ha terminado. Inicia sesión de nuevo.",
        );
      }
      const response = await fetch(`${base}/auth/refresh_token`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        session.clear();
        throw new ApiError(401, "Tu sesión ha terminado.");
      }
      const data = (await response.json()) as { access_token: string };
      session.save(data.access_token);
    })().finally(() => {
      refreshFlight = null;
    });
  return refreshFlight;
}
export async function api<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    signal?: AbortSignal;
    public?: boolean;
  } = {},
  retry = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (!options.public && session.access())
    headers.Authorization = `Bearer ${session.access()}`;
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method: options.method ?? "GET",
      headers,
      signal: options.signal,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      "No se pudo conectar con el servidor. Comprueba tu conexión.",
    );
  }
  if (response.status === 401 && !options.public && retry) {
    await refreshSession();
    return api<T>(path, options, false);
  }
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as {
      detail?: unknown;
      message?: string;
    } | null;
    const detail =
      typeof data?.detail === "string" ? data.detail : data?.message;
    throw new ApiError(
      response.status,
      localizedApiError(response.status, detail),
      detail,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
export const communityPath = (id: string) =>
  `/communities/${encodeURIComponent(id)}`;
