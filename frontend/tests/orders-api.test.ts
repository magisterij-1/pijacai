// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cancelOrder, createOrder, listOrders, listProducts, previewOrder } from "../src/api/orders";
import { readToken, saveToken, unauthorizedEvent } from "../src/api/auth";

const fetchMock = vi.fn<typeof fetch>();
const base = import.meta.env.VITE_API_URL || "http://localhost:8001/api";
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); sessionStorage.clear(); saveToken("planner-token"); });
afterEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });

function respond(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

it.each([
  { path: "/lookup/products", action: listProducts }, { path: "/orders", action: listOrders },
])("pravilno prebere $path z JWT in signalom", async ({ path, action }) => {
  respond([]);
  const controller = new AbortController();
  await expect(action(controller.signal)).resolves.toEqual([]);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(base + path);
  expect(options?.signal).toBe(controller.signal);
  expect(options?.cache).toBe("no-store");
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer planner-token");
});

it("predogled pošlje samo izdelek in celo količino, potrditev pa tudi recepturo in datum", async () => {
  respond({ requirements: [] });
  await previewOrder({ product_id: 10, planned_qty: 500 });
  expect(fetchMock.mock.calls[0][0]).toBe(`${base}/orders/preview`);
  expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toEqual({ product_id: 10, planned_qty: 500 });
  respond({ id: 1 }, 201);
  const body = { product_id: 10, planned_qty: 500, planned_date: "2099-01-01", recipe_id: 20 };
  await createOrder(body);
  expect(fetchMock.mock.calls[1][0]).toBe(`${base}/orders`);
  expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toEqual(body);
  expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("Content-Type")).toBe("application/json");
});

it("ohrani konflikt recepture in njegov status", async () => {
  respond({ detail: "Receptura se je spremenila." }, 409);
  await expect(createOrder({ product_id: 10, planned_qty: 500, planned_date: "2099-01-01", recipe_id: 20 })).rejects.toMatchObject({ message: "Receptura se je spremenila.", status: 409 });
});

it("ob 401 odstrani JWT in sproži odjavo", async () => {
  respond({ detail: "Prijava ni veljavna." }, 401);
  const listener = vi.fn();
  window.addEventListener(unauthorizedEvent, listener);
  try {
    await expect(listOrders()).rejects.toThrow("Prijava je potekla ali ni veljavna.");
    expect(readToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
  } finally {
    window.removeEventListener(unauthorizedEvent, listener);
  }
});

it("odpoved pošlje POST na ID naloga z JWT in brez spremembe polj", async () => {
  respond({ id: 42, status: "cancelled" });
  await expect(cancelOrder(42)).resolves.toEqual({ id: 42, status: "cancelled" });
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe(`${base}/orders/42/cancel`);
  expect(options?.method).toBe("POST");
  expect(options?.body).toBeUndefined();
  expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer planner-token");
});

it("odpoved ohrani sporočilo in status konflikta API", async () => {
  respond({ detail: "Naloga ni mogoče odpovedati, ker je šarža že zagnana." }, 409);
  await expect(cancelOrder(42)).rejects.toMatchObject({ message: "Naloga ni mogoče odpovedati, ker je šarža že zagnana.", status: 409 });
});
