const API_BASE = "/api";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("cleo_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handle401(): never {
  localStorage.removeItem("cleo_token");
  localStorage.removeItem("cleo_user");
  window.location.href = "/login";
  throw new Error("Unauthorized");
}

export async function fetchApi<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }

  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (res.status === 401) handle401();
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function postApi<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (res.status === 401) handle401();
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function mutateApi<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { ...authHeaders() };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) handle401();
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
