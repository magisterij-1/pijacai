// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { listLines, previewBatch, startBatch } from "../src/api/batches";
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

it.each([
  { name: "linije", action: () => listLines() },
  { name: "predogled", action: () => previewBatch(42, { line_id: 10, qty: "500" }) },
  { name: "zagon", action: () => startBatch(42, { line_id: 10, qty: "500" }) },
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
