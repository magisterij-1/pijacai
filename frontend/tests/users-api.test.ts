// — zahtevki API za uporabnike.
// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createUser, deactivateUser, listUsers, UserApiError } from "../src/api/users";
import { readToken, saveToken, unauthorizedEvent } from "../src/api/auth";
import type { User } from "../src/api/auth";

// API modulov ne nadomestimo: zahtevek gre skozi pravi authenticatedRequest.
const fetchMock = vi.fn<typeof fetch>();
const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8001/api";
const account: User = { id: 2, name: "Planer", email: "planner@pijacai.local", role: "planner", active: true };
const form = { name: account.name, email: account.email, password: "TestnoGeslo2026!", role: account.role };

function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.clear();
  saveToken("test-token");
});

afterEach(() => {
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

it("pridobi seznam s pravilno potjo, JWT in onemogočenim predpomnjenjem", async () => {
  respond([account]);
  const controller = new AbortController();
  await expect(listUsers(controller.signal)).resolves.toEqual([account]);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${apiUrl}/users`);
  expect(options?.cache).toBe("no-store");
  expect(options?.signal).toBe(controller.signal);
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer test-token");
});

it("pošlje podatke ustvarjanja kot JSON brez shranjevanja gesla v brskalnik", async () => {
  respond(account, 201);
  await expect(createUser(form)).resolves.toEqual(account);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${apiUrl}/users`);
  expect(options?.method).toBe("POST");
  expect(new Headers(options?.headers).get("Content-Type")).toBe("application/json");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer test-token");
  expect(JSON.parse(options?.body as string)).toEqual(form);
  expect(sessionStorage.length).toBe(1);
  expect(readToken()).toBe("test-token");
});

it("deaktivira izbrani ID prek pravilne poti", async () => {
  respond({ ...account, active: false });
  await expect(deactivateUser(2)).resolves.toEqual({ ...account, active: false });
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${apiUrl}/users/2/deactivate`);
  expect(options?.method).toBe("POST");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer test-token");
});

it.each([
  { name: "seznam", action: () => listUsers() },
  { name: "ustvarjanje", action: () => createUser(form) },
  { name: "deaktivacija", action: () => deactivateUser(2) },
])("ob 401 počisti JWT in sproži odjavo: $name", async ({ action }) => {
  respond({ detail: "Prijava ni veljavna." }, 401);
  const listener = vi.fn();
  window.addEventListener(unauthorizedEvent, listener);
  try {
    await expect(action()).rejects.toThrow("Prijava je potekla ali ni veljavna.");
    expect(readToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
  } finally {
    window.removeEventListener(unauthorizedEvent, listener);
  }
});

it("ob 403 prikaže zavrnitev in ohrani veljavno prijavo", async () => {
  respond({ detail: "Nimate dostopa." }, 403);
  await expect(listUsers()).rejects.toThrow("Nimate dostopa.");
  expect(readToken()).toBe("test-token");
});

it("preslika podvojeno e-pošto v napako polja", async () => {
  respond({ detail: "Uporabnik s to e-pošto že obstaja." }, 409);
  await expect(createUser(form)).rejects.toMatchObject({
    message: "Uporabnik s to e-pošto že obstaja.",
    fields: { email: "Uporabnik s to e-pošto že obstaja." },
  });
});

it("preslika validacijske napake 422 samo v znana polja", async () => {
  respond({ detail: [
    { loc: ["body", "password"], msg: "Invalid password", type: "value_error" },
    { loc: ["body", "role"], msg: "Invalid role", type: "enum" },
    { loc: ["body", "unexpected"], msg: "Extra input", type: "extra_forbidden" },
  ] }, 422);
  await expect(createUser(form)).rejects.toMatchObject({
    message: "Preveri podatke v obrazcu.",
    fields: { password: "Preveri vneseno vrednost.", role: "Preveri vneseno vrednost." },
  });
});

it("ohrani opis napake za neobstoječega uporabnika", async () => {
  respond({ detail: "Uporabnik ni najden." }, 404);
  await expect(deactivateUser(999)).rejects.toThrow("Uporabnik ni najden.");
});

it("omrežno napako pretvori v razumljivo sporočilo brez izgube JWT", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await expect(listUsers()).rejects.toThrow("Povezava s strežnikom ni uspela.");
  expect(readToken()).toBe("test-token");
});

it("pri napaki brez JSON vrne splošno sporočilo", async () => {
  fetchMock.mockResolvedValueOnce(new Response("Service unavailable", { status: 503 }));
  await expect(listUsers()).rejects.toBeInstanceOf(UserApiError);
});
