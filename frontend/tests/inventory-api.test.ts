// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getStock, InventoryApiError, listMaterialLots, listMaterials, listSuppliers, receiveMaterial } from "../src/api/inventory";
import { readToken, saveToken, unauthorizedEvent } from "../src/api/auth";
import type { MaterialLot, ReceiptCreate } from "../src/api/inventory";

const fetchMock = vi.fn<typeof fetch>();
const base = import.meta.env.VITE_API_URL || "http://localhost:8001/api";
const receipt: ReceiptCreate = { material_id: 1, supplier_id: 2, supplier_lot_no: "TEST-1", received_qty: "0.125", unit_cost: "0" };
const saved: MaterialLot = { ...receipt, id: 3, remaining_qty: "0.125", received_by: 4, received_at: "2026-11-08T10:00:00Z" };

function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.clear();
  saveToken("warehouse-token");
});

afterEach(() => {
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

it.each([
  { path: "/lookup/materials", action: listMaterials },
  { path: "/lookup/suppliers", action: listSuppliers },
  { path: "/material-lots", action: listMaterialLots },
])("bralna pot $path pošlje JWT in ohrani signal preklica", async ({ path, action }) => {
  respond([]);
  const controller = new AbortController();
  await expect(action(controller.signal)).resolves.toEqual([]);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(base + path);
  expect(options?.cache).toBe("no-store");
  expect(options?.signal).toBe(controller.signal);
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer warehouse-token");
});

it("shrani prejem z decimalnimi nizi in samo dovoljenimi vhodnimi polji", async () => {
  respond(saved, 201);
  await expect(receiveMaterial(receipt)).resolves.toEqual(saved);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/material-lots`);
  expect(options?.method).toBe("POST");
  expect(new Headers(options?.headers).get("Content-Type")).toBe("application/json");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer warehouse-token");
  expect(JSON.parse(options?.body as string)).toEqual(receipt);
});

it.each([
  { name: "surovine", action: () => listMaterials() },
  { name: "dobavitelji", action: () => listSuppliers() },
  { name: "serije", action: () => listMaterialLots() },
  { name: "prejem", action: () => receiveMaterial(receipt) },
])("ob 401 počisti prijavo in sproži odjavo: $name", async ({ action }) => {
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

it("ob 403 ohrani prijavo in vrne zavrnitev dostopa", async () => {
  respond({ detail: "Nimate dostopa." }, 403);
  await expect(receiveMaterial(receipt)).rejects.toThrow("Nimate dostopa.");
  expect(readToken()).toBe("warehouse-token");
});

it("podvojeno serijo preslika v napako ob polju", async () => {
  respond({ detail: "Ta serija je že vnesena." }, 409);
  await expect(receiveMaterial(receipt)).rejects.toMatchObject({
    message: "Ta serija je že vnesena.", fields: { supplier_lot_no: "Ta serija je že vnesena." },
  });
});

it("validacijske napake preslika samo v polja prejema", async () => {
  respond({ detail: [
    { loc: ["body", "received_qty"], msg: "Invalid quantity", type: "value_error" },
    { loc: ["body", "unit_cost"], msg: "Invalid cost", type: "value_error" },
    { loc: ["body", "received_by"], msg: "Extra input", type: "extra_forbidden" },
  ] }, 422);
  await expect(receiveMaterial(receipt)).rejects.toMatchObject({
    message: "Preveri podatke prejema.",
    fields: { received_qty: "Preveri vneseno vrednost.", unit_cost: "Preveri vneseno vrednost." },
  });
});

it.each(["Surovina ni najdena.", "Dobavitelj ni najden."])("ohrani sporočilo 404: %s", async detail => {
  respond({ detail }, 404);
  await expect(receiveMaterial(receipt)).rejects.toThrow(detail);
});

it("omrežna napaka ne počisti prijave", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await expect(listMaterialLots()).rejects.toThrow("Povezava s strežnikom ni uspela.");
  expect(readToken()).toBe("warehouse-token");
});

it("zavrne prazen uspešen odgovor in ohrani napako brez JSON", async () => {
  fetchMock.mockResolvedValueOnce(new Response("", { status: 201 }));
  await expect(receiveMaterial(receipt)).rejects.toThrow("Neveljaven odgovor strežnika.");
  fetchMock.mockResolvedValueOnce(new Response("Service unavailable", { status: 503 }));
  await expect(listMaterialLots()).rejects.toBeInstanceOf(InventoryApiError);
});

it.each([
  { options: {}, material: null, consumed: "false" },
  { options: { material_id: 10, include_consumed: true }, material: "10", consumed: "true" },
])("pregled zalog pravilno zapiše filter in stikalo v URL: $consumed", async ({ options, material, consumed }) => {
  respond({ lots: [], totals: [] });
  const controller = new AbortController();
  await expect(getStock(options, controller.signal)).resolves.toEqual({ lots: [], totals: [] });
  const [url, request] = fetchMock.mock.calls[0];
  const parsed = new URL(String(url));
  expect(parsed.pathname).toBe("/api/stock");
  expect(parsed.searchParams.get("material_id")).toBe(material);
  expect(parsed.searchParams.get("include_consumed")).toBe(consumed);
  expect(request?.signal).toBe(controller.signal);
  expect(request?.cache).toBe("no-store");
  expect(new Headers(request?.headers).get("Authorization")).toBe("Bearer warehouse-token");
});
