// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { traceBatchByCode } from "../src/api/traceability";
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
