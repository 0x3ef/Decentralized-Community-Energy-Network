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
let sessionVersion = 0;
export const session = {
  version: () => sessionVersion,
  access: () => sessionStorage.getItem("solar.access"),
  refresh: () => sessionStorage.getItem("solar.refresh"),
  save: (access: string, refresh?: string) => {
    if (refresh !== undefined) sessionVersion++;
    sessionStorage.setItem("solar.access", access);
    if (refresh) sessionStorage.setItem("solar.refresh", refresh);
  },
  clear: () => {
    sessionVersion++;
    sessionStorage.removeItem("solar.access");
    sessionStorage.removeItem("solar.refresh");
    window.dispatchEvent(new Event("solar:logout"));
  },
};
function assertSession(version: number) {
  if (version !== session.version())
    throw new DOMException("La sesión cambió.", "AbortError");
}
let refreshFlight: { version: number; promise: Promise<void> } | null = null;
async function refreshSession(version: number) {
  assertSession(version);
  if (!refreshFlight || refreshFlight.version !== version) {
    const flight = { version, promise: Promise.resolve() };
    flight.promise = (async () => {
      const token = session.refresh();
      if (!token) {
        session.clear();
        throw new ApiError(
          401,
          "Tu sesión ha terminado. Inicia sesión de nuevo.",
        );
      }
      let response: Response;
      try {
        response = await fetch(`${base}/auth/refresh_token`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch (error) {
        assertSession(version);
        throw error;
      }
      assertSession(version);
      if (!response.ok) {
        if ([401, 403].includes(response.status)) {
          session.clear();
          throw new ApiError(401, "Tu sesión ha terminado.");
        }
        throw new ApiError(response.status, localizedApiError(response.status));
      }
      const data = (await response.json()) as { access_token: string };
      assertSession(version);
      session.save(data.access_token);
    })().finally(() => {
      if (refreshFlight === flight) refreshFlight = null;
    });
    refreshFlight = flight;
  }
  return refreshFlight.promise;
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
  const version = session.version();
  const access = session.access();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (!options.public && access) headers.Authorization = `Bearer ${access}`;
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
    if (!options.public) assertSession(version);
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      0,
      "No se pudo conectar con el servidor. Comprueba tu conexión.",
    );
  }
  if (!options.public) assertSession(version);
  if (response.status === 401 && !options.public && retry) {
    if (access === session.access()) await refreshSession(version);
    assertSession(version);
    return api<T>(path, options, false);
  }
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as {
      detail?: unknown;
      message?: string;
    } | null;
    if (!options.public) assertSession(version);
    const detail =
      typeof data?.detail === "string" ? data.detail : data?.message;
    throw new ApiError(
      response.status,
      localizedApiError(response.status, detail),
      detail,
    );
  }
  const data = response.status === 204 ? undefined : await response.json();
  if (!options.public) assertSession(version);
  return data as T;
}
export const communityPath = (id: string) =>
  `/communities/${encodeURIComponent(id)}`;
