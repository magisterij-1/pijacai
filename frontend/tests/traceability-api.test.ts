// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { findTraceLots, listTraceMaterials, traceBatchByCode, traceLot } from "../src/api/traceability";
import { readToken, saveToken, unauthorizedEvent } from "../src/api/auth";

const fetchMock = vi.fn<typeof fetch>();
const base = import.meta.env.VITE_API_URL || "http://localhost:8001/api";
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); sessionStorage.clear(); saveToken("planner-token"); });
afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });
function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

it("poišče po točni kodi z JWT, signalom in brez predpomnilnika", async () => {
  const result = { id: 42, batch_code: "ŠARŽA & +/#1", consumptions: [], totals: [] };
  respond(result);
  const controller = new AbortController();
  expect(await traceBatchByCode(result.batch_code, controller.signal)).toEqual(result);
  const [url, options] = fetchMock.mock.calls[0];
  const parsed = new URL(String(url));
  expect(parsed.origin + parsed.pathname).toBe(`${base}/traceability/batch`);
  expect(parsed.searchParams.get("batch_code")).toBe(result.batch_code);
  expect(Array.from(parsed.searchParams.keys())).toEqual(["batch_code"]);
  expect(options?.signal).toBe(controller.signal);
  expect(options?.cache).toBe("no-store");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer planner-token");
});

it("pri 404 vrne predpisano sporočilo", async () => {
  respond({ detail: "Šarža ni najdena." }, 404);
  await expect(traceBatchByCode("NEOBSTAJA")).rejects.toMatchObject({ status: 404, message: "Šarža ni najdena." });
});

it("pri 422 vrne napako za iskalno polje", async () => {
  respond({ detail: [] }, 422);
  await expect(traceBatchByCode("bad")).rejects.toMatchObject({ status: 422, codeError: "Vnesi kodo šarže z največ 80 znaki." });
});

it.each([403, 500])("ohrani status in sporočilo %s", async status => {
  respond({ detail: "Sledljivosti ni mogoče odpreti." }, status);
  await expect(traceBatchByCode("KODA")).rejects.toMatchObject({ status, message: "Sledljivosti ni mogoče odpreti." });
});

it("401 odstrani žeton in sproži odjavo", async () => {
  respond({ detail: "Prijava ni veljavna." }, 401);
  const listener = vi.fn(); window.addEventListener(unauthorizedEvent, listener);
  try {
    await expect(traceBatchByCode("KODA")).rejects.toThrow("Prijava je potekla ali ni veljavna.");
    expect(readToken()).toBeNull(); expect(listener).toHaveBeenCalledOnce();
  } finally { window.removeEventListener(unauthorizedEvent, listener); }
});

it("omrežno napako prikaže razumljivo", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await expect(traceBatchByCode("KODA")).rejects.toThrow("Povezava s strežnikom ni uspela.");
});

it("ohrani preklic zahtevka", async () => {
  fetchMock.mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));
  await expect(traceBatchByCode("KODA")).rejects.toMatchObject({ name: "AbortError" });
});

it("zavrne prazen uspešen odgovor", async () => {
  respond(null);
  await expect(traceBatchByCode("KODA")).rejects.toThrow("Neveljaven odgovor strežnika.");
});

it("prebere šifrant sledljivosti z JWT in signalom", async () => {
  respond([{ id: 1, name: "Koncentrat", unit: "kg", type: "ingredient" }]);
  const controller = new AbortController();
  await listTraceMaterials(controller.signal);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/traceability/materials`);
  expect(options?.signal).toBe(controller.signal);
  expect(options?.cache).toBe("no-store");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer planner-token");
});

it("poišče serije s točno kodiranim materialom in dobaviteljevo številko", async () => {
  respond([{ id: 30 }, { id: 31 }]);
  await findTraceLots({ material_id: 20, supplier_lot_no: "A & +/#1" });
  const [url, options] = fetchMock.mock.calls[0];
  const parsed = new URL(String(url));
  expect(parsed.pathname).toBe("/api/traceability/lots");
  expect(parsed.searchParams.get("material_id")).toBe("20");
  expect(parsed.searchParams.get("supplier_lot_no")).toBe("A & +/#1");
  expect(options?.cache).toBe("no-store");
});

it("prebere sledljivost izbrane enolične serije", async () => {
  const result = { id: 31, batches: [], total_consumed_qty: "0.000" };
  respond(result);
  const controller = new AbortController();
  expect(await traceLot(31, controller.signal)).toEqual(result);
  expect(fetchMock.mock.calls[0][0]).toBe(`${base}/traceability/lot/31`);
  expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
});

it.each([() => findTraceLots({ material_id: 20, supplier_lot_no: "MISSING" }), () => traceLot(31)])("pri 404 serije vrne pravilno sporočilo", async action => {
  respond({ detail: "Serija ni najdena." }, 404);
  await expect(action()).rejects.toMatchObject({ status: 404, message: "Serija ni najdena." });
});

it("napake iskanja 422 preslika na obe polji", async () => {
  respond({ detail: [{ loc: ["query", "material_id"] }, { loc: ["query", "supplier_lot_no"] }] }, 422);
  await expect(findTraceLots({ material_id: 0, supplier_lot_no: "" })).rejects.toMatchObject({ status: 422,
    fields: { material_id: "Preveri vneseno vrednost.", supplier_lot_no: "Preveri vneseno vrednost." } });
});

it.each([() => listTraceMaterials(), () => findTraceLots({ material_id: 20, supplier_lot_no: "A" }), () => traceLot(31)])("pri 401 lot operacije sprožijo odjavo", async action => {
  respond({ detail: "Prijava ni veljavna." }, 401);
  const listener = vi.fn(); window.addEventListener(unauthorizedEvent, listener);
  try {
    await expect(action()).rejects.toThrow("Prijava je potekla ali ni veljavna.");
    expect(readToken()).toBeNull(); expect(listener).toHaveBeenCalledOnce();
  } finally { window.removeEventListener(unauthorizedEvent, listener); }
});
