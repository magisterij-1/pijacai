// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { finishBatch, getBatch, listBatches, listLines, previewBatch, startBatch } from "../src/api/batches";
import { readToken, saveToken, unauthorizedEvent } from "../src/api/auth";

const fetchMock = vi.fn<typeof fetch>();
const base = import.meta.env.VITE_API_URL || "http://localhost:8001/api";
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); sessionStorage.clear(); saveToken("operator-token"); });
afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });
function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

it("prebere aktivne linije z JWT in signalom preklica", async () => {
  respond([{ id: 1, name: "Linija 1" }]);
  const controller = new AbortController();
  await listLines(controller.signal);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/lookup/lines`);
  expect(options?.signal).toBe(controller.signal);
  expect(options?.cache).toBe("no-store");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer operator-token");
});

it("predogled in zagon pošljeta izbrani nalog, linijo in decimalni niz", async () => {
  respond({ can_start: true });
  const body = { line_id: 10, qty: "500.125" };
  await previewBatch(42, body);
  respond({ id: 1 }, 201);
  await startBatch(42, body);
  expect(fetchMock.mock.calls[0][0]).toBe(`${base}/orders/42/batches/preview`);
  expect(fetchMock.mock.calls[1][0]).toBe(`${base}/orders/42/batches`);
  for (const [, options] of fetchMock.mock.calls) {
    expect(options?.method).toBe("POST");
    expect(JSON.parse(options?.body as string)).toEqual(body);
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer operator-token");
  }
});

it("iz strukturirane napake 409 ohrani manjkajoče količine", async () => {
  const missing = [{ material_id: 20, material_name: "Koncentrat", unit: "kg", required_qty: "40", available_qty: "1", missing_qty: "39", status: "PREMALO" }];
  respond({ detail: { code: "INSUFFICIENT_STOCK", message: "Za zagon šarže ni dovolj zaloge.", missing } }, 409);
  await expect(startBatch(42, { line_id: 10, qty: "500" })).rejects.toMatchObject({ message: "Za zagon šarže ni dovolj zaloge.", status: 409, missing });
});

it("natančno omejitev odpisa iz 422 prikaže ob količini", async () => {
  const msg = "Izberi količino šarže, ki omogoča natančen odpis na 0,001 kg.";
  respond({ detail: [{ loc: ["body", "qty"], msg, type: "value_error" }] }, 422);
  await expect(previewBatch(42, { line_id: 10, qty: "1" })).rejects.toMatchObject({ fields: { qty: msg }, status: 422 });
});

it.each(["in_production", "awaiting_qc"] as const)("seznam šarž filtrira po stanju %s", async status => {
  respond([]);
  const controller = new AbortController();
  await listBatches(status, controller.signal);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/batches?status_filter=${status}`);
  expect(options?.signal).toBe(controller.signal);
  expect(options?.cache).toBe("no-store");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer operator-token");
});

it("prebere podrobnosti s signalom in pošlje zaključek s celimi količinami", async () => {
  respond({ id: 42 });
  const controller = new AbortController();
  await getBatch(42, controller.signal);
  expect(fetchMock.mock.calls[0][0]).toBe(`${base}/batches/42`);
  expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  expect(fetchMock.mock.calls[0][1]?.cache).toBe("no-store");
  respond({ id: 42, status: "awaiting_qc" });
  await finishBatch(42, { produced_qty: 480, rejected_qty: 5 });
  const [url, options] = fetchMock.mock.calls[1];
  expect(url).toBe(`${base}/batches/42/finish`);
  expect(options?.method).toBe("POST");
  expect(JSON.parse(options?.body as string)).toEqual({ produced_qty: 480, rejected_qty: 5 });
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer operator-token");
});

it("napake zaključka 422 preslika na obe količini in prezre nedovoljene ključe", async () => {
  const msg = "Izmet ne sme presegati proizvedene količine.";
  respond({ detail: [
    { loc: ["body", "produced_qty"], msg: "invalid", type: "int_type" },
    { loc: ["body", "rejected_qty"], msg, type: "value_error" },
    { loc: ["body", "status"], msg: "invalid", type: "extra_forbidden" },
  ] }, 422);
  await expect(finishBatch(42, { produced_qty: 10, rejected_qty: 11 })).rejects.toMatchObject({
    status: 422, fields: { produced_qty: "Preveri vneseno vrednost.", rejected_qty: msg },
  });
});

it.each([403, 404, 409])("ohrani status in sporočilo neuspešnega zaključka %s", async status => {
  respond({ detail: "Zaključek ni dovoljen." }, status);
  await expect(finishBatch(42, { produced_qty: 10, rejected_qty: 0 })).rejects.toMatchObject({ status, message: "Zaključek ni dovoljen." });
});

it.each([
  { name: "linije", action: () => listLines() },
  { name: "predogled", action: () => previewBatch(42, { line_id: 10, qty: "500" }) },
  { name: "zagon", action: () => startBatch(42, { line_id: 10, qty: "500" }) },
  { name: "seznam šarž", action: () => listBatches("in_production") },
  { name: "podrobnosti šarže", action: () => getBatch(42) },
  { name: "zaključek", action: () => finishBatch(42, { produced_qty: 500, rejected_qty: 0 }) },
])("ob 401 sproži odjavo: $name", async ({ action }) => {
  respond({ detail: "Prijava ni veljavna." }, 401);
  const listener = vi.fn();
  window.addEventListener(unauthorizedEvent, listener);
  try {
    await expect(action()).rejects.toThrow("Prijava je potekla ali ni veljavna.");
    expect(readToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
  } finally { window.removeEventListener(unauthorizedEvent, listener); }
});
