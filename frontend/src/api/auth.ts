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
