// — prijava, shranjevanje JWT in zaščiteni zahtevki.
const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8001/api";

export type Role = "operator" | "quality" | "planner" | "warehouse" | "admin";

export type User = {
  id: number;
  name: string;
  email: string;
  role: Role;
  active: boolean;
};

export type LoginResult = {
  access_token: string;
  token_type: string;
  expires_in: number;
  expires_at: number;
  user: User;
};

export async function login(email: string, password: string): Promise<LoginResult> {
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
  } catch {
    throw new Error("Povezava s strežnikom ni uspela. Poskusi znova.");
  }

  if (response.status === 401) {
    throw new Error("Napačna e-pošta ali geslo.");
  }
  if (!response.ok) {
    throw new Error("Prijava trenutno ni uspela. Poskusi znova.");
  }
  return response.json();
}

const tokenKey = "pijacai.access_token";
export const unauthorizedEvent = "pijacai:unauthorized";

export function readToken(): string | null {
  return sessionStorage.getItem(tokenKey);
}

export function saveToken(token: string): void {
  sessionStorage.setItem(tokenKey, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(tokenKey);
}

// Vsi prihodnji zaščiteni API zahtevki naj uporabljajo ta skupni klic.
export async function authenticatedRequest(path: string, options: RequestInit = {}): Promise<Response> {
  const token = readToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiUrl}${path}`, { ...options, headers });
  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new Event(unauthorizedEvent));
    throw new Error("Prijava je potekla ali ni veljavna. Prijavi se znova.");
  }
  return response;
}

export async function restoreSession(): Promise<LoginResult | null> {
  const token = readToken();
  if (!token) return null;
  const response = await authenticatedRequest("/auth/me", { cache: "no-store" });
  if (!response.ok) throw new Error("Prijave ni mogoče preveriti. Poskusi znova.");
  const result: { user: User; expires_at: number } = await response.json();
  return {
    access_token: token,
    token_type: "bearer",
    expires_at: result.expires_at,
    expires_in: Math.max(0, result.expires_at - Math.floor(Date.now() / 1000)),
    user: result.user,
  };
}
