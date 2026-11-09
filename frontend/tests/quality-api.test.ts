// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getQuality, releaseBatch, saveQualityCheck } from "../src/api/quality";
import { readToken, saveToken, unauthorizedEvent } from "../src/api/auth";

const fetchMock = vi.fn<typeof fetch>();
const base = import.meta.env.VITE_API_URL || "http://localhost:8001/api";
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); sessionStorage.clear(); saveToken("quality-token"); });
afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });
function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

it("bere meritve z JWT, signalom preklica in brez predpomnilnika", async () => {
  respond({ batch_id: 42, parameters: [], checks: [] });
  const controller = new AbortController();
  await getQuality(42, controller.signal);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/batches/42/checks`);
  expect(options?.signal).toBe(controller.signal);
  expect(options?.cache).toBe("no-store");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer quality-token");
});

it("shrani parameter in natančni decimalni niz brez polj avtorstva ali ustreznosti", async () => {
  respond({ id: 9 }, 201);
  await saveQualityCheck(42, { parameter_id: 3, value: "-0.001" });
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/batches/42/checks`);
  expect(options?.method).toBe("POST");
  expect(JSON.parse(options?.body as string)).toEqual({ parameter_id: 3, value: "-0.001" });
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer quality-token");
});

it("422 preslika na parameter in vrednost ter prezre druga polja", async () => {
  respond({ detail: [
    { loc: ["body", "parameter_id"], type: "value_error", msg: "Parameter ne pripada izdelku šarže." },
    { loc: ["body", "value"], type: "decimal_max_places", msg: "invalid" },
    { loc: ["body", "passed"], type: "extra_forbidden", msg: "invalid" },
  ] }, 422);
  await expect(saveQualityCheck(42, { parameter_id: 3, value: "3.0001" })).rejects.toMatchObject({
    status: 422, fields: { parameter_id: "Parameter ne pripada izdelku šarže.", value: "Preveri vneseno vrednost." },
  });
});

it.each([403, 404, 409])("ohrani poslovno napako %s", async status => {
  respond({ detail: "Meritev ni dovoljena." }, status);
  await expect(saveQualityCheck(42, { parameter_id: 3, value: "3" })).rejects.toMatchObject({ status, message: "Meritev ni dovoljena." });
});

it.each([getQuality.bind(null, 42), () => saveQualityCheck(42, { parameter_id: 3, value: "3" }), () => releaseBatch(42)])("ob 401 odstrani žeton in sproži odjavo", async action => {
  respond({ detail: "Prijava ni veljavna." }, 401);
  const listener = vi.fn(); window.addEventListener(unauthorizedEvent, listener);
  try {
    await expect(action()).rejects.toThrow("Prijava je potekla ali ni veljavna.");
    expect(readToken()).toBeNull(); expect(listener).toHaveBeenCalledOnce();
  } finally { window.removeEventListener(unauthorizedEvent, listener); }
});

it("omrežno napako prikaže razumljivo", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  await expect(getQuality(42)).rejects.toThrow("Povezava s strežnikom ni uspela.");
});

it("zavrne prazen uspešen odgovor", async () => {
  respond(null);
  await expect(getQuality(42)).rejects.toThrow("Neveljaven odgovor strežnika.");
});

it("sprostitev pošlje kot POST z JWT in vrne podatke odločitve", async () => {
  const result = { id: 42, status: "released", decided_by: 8, decided_at: "2026-11-09T11:00:00Z" };
  respond(result);
  expect(await releaseBatch(42)).toEqual(result);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/batches/42/release`);
  expect(options?.method).toBe("POST");
  expect(options?.body).toBeUndefined();
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer quality-token");
});

it.each(["QUALITY_NOT_PASSED", "NO_QUALITY_PARAMETERS"])("ohrani strukturirano napako sprostitve %s", async code => {
  const missing = [{ parameter_id: 10, name: "pH" }];
  const invalid = [{ parameter_id: 11, name: "CO₂" }];
  respond({ detail: { code, message: "Pogoji niso izpolnjeni.", missing, invalid } }, 422);
  await expect(releaseBatch(42)).rejects.toMatchObject({ status: 422, message: "Pogoji niso izpolnjeni.", problems: { code, missing, invalid } });
});

it.each([403, 404, 409])("ohrani status in sporočilo napake sprostitve %s", async status => {
  respond({ detail: "Sprostitev ni dovoljena." }, status);
  await expect(releaseBatch(42)).rejects.toMatchObject({ status, message: "Sprostitev ni dovoljena." });
});
