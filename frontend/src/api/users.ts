import { authenticatedRequest } from "./auth";
import type { Role, User } from "./auth";

export type UserCreate = { name: string; email: string; password: string; role: Role };
export type UserFields = Partial<Record<keyof UserCreate, string>>;

export class UserApiError extends Error {
  constructor(message: string, public fields: UserFields = {}) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedRequest(path, options);
  } catch (error) {
    if (error instanceof TypeError) throw new UserApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 409) {
      throw new UserApiError("Uporabnik s to e-pošto že obstaja.", { email: "Uporabnik s to e-pošto že obstaja." });
    }
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const fields: UserFields = {};
      for (const item of body.detail) {
        const field = item.loc?.[item.loc.length - 1];
        if (["name", "email", "password", "role"].includes(field)) {
          fields[field as keyof UserCreate] = "Preveri vneseno vrednost.";
        }
      }
      throw new UserApiError("Preveri podatke v obrazcu.", fields);
    }
    throw new UserApiError(typeof body?.detail === "string" ? body.detail : "Zahtevek ni uspel. Poskusi znova.");
  }
  return body as T;
}

export function listUsers(signal?: AbortSignal): Promise<User[]> {
  return request("/users", { signal, cache: "no-store" });
}

export function createUser(data: UserCreate): Promise<User> {
  return request("/users", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
}

export function deactivateUser(id: number): Promise<User> {
  return request(`/users/${id}/deactivate`, { method: "POST" });
}
