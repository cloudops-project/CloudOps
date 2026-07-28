const API_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;
type AuthInvalidatedHandler = () => void;
let authInvalidatedHandler: AuthInvalidatedHandler | null = null;

export interface ApiErrorDetail {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
    readonly details: ApiErrorDetail[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function setAccessToken(value: string | null) {
  accessToken = value;
}

export function setAuthInvalidatedHandler(
  handler: AuthInvalidatedHandler | null,
) {
  authInvalidatedHandler = handler;
}

function invalidateAuthentication() {
  accessToken = null;
  authInvalidatedHandler?.();
}

async function refresh(): Promise<boolean> {
  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    invalidateAuthentication();
    return false;
  }
  accessToken = ((await response.json()) as { access_token: string })
    .access_token;
  return true;
}

export async function restoreAuthentication() {
  refreshPromise ??= refresh().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401 && retry && path !== "/api/v1/auth/refresh") {
    if (await restoreAuthentication()) return api<T>(path, init, false);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: {
        code?: string;
        message?: string;
        details?: ApiErrorDetail[];
      };
    } | null;
    throw new ApiError(
      response.status,
      body?.error?.message || "Request failed.",
      body?.error?.code,
      body?.error?.details,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiBlob(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Blob> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401 && retry && path !== "/api/v1/auth/refresh") {
    if (await restoreAuthentication()) return apiBlob(path, init, false);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string; details?: ApiErrorDetail[] };
    } | null;
    throw new ApiError(
      response.status,
      body?.error?.message || "Request failed.",
      body?.error?.code,
      body?.error?.details,
    );
  }
  return response.blob();
}
