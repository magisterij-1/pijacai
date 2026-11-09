// — preverjanje zalog in potrjevanje zagona.
// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BatchApiError, listLines, previewBatch, startBatch } from "../src/api/batches";
import type { Batch, BatchPreview } from "../src/api/batches";
import type { Order } from "../src/api/orders";
import { StartBatch } from "../src/pages/StartBatch";

vi.mock("../src/api/batches", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/batches")>();
  return { ...actual, listLines: vi.fn(), previewBatch: vi.fn(), startBatch: vi.fn() };
});

const order: Order = {
  id: 1, product_id: 2, product_name: "Sok", product_unit: "kos", recipe_id: 3, recipe_version: 1,
  output_qty: "1000", planned_qty: 1000, planned_date: "2099-01-01", status: "planned", created_by: 5, requirements: [],
};
const orders = [order];
const preview: BatchPreview = {
  order_id: 1, recipe_id: 3, recipe_version: 1, line_id: 10, qty: "500.000", can_start: true,
  requirements: [{ material_id: 20, material_name: "Koncentrat", unit: "kg", required_qty: "40", available_qty: "90", missing_qty: "0", status: "OK" }],
};
const batch: Batch = {
  id: 6, batch_code: "2026-11-09-L10-01", order_id: 1, product_id: 2, product_name: "Sok", product_unit: "kos",
  recipe_id: 3, recipe_version: 1, line_id: 10, line_name: "Linija 1", operator_id: 7,
  status: "in_production", planned_qty: "500.000", produced_qty: 0, rejected_qty: 0,
  started_at: "2026-11-09T10:00:00Z", finished_at: null,
  decided_by: null, decided_at: null, decision_note: null,
  consumptions: [
    { material_lot_id: 30, material_id: 20, material_name: "Koncentrat", supplier_name: "Dobavitelj", supplier_lot_no: "STARA", qty: "30", unit: "kg" },
    { material_lot_id: 31, material_id: 20, material_name: "Koncentrat", supplier_name: "Dobavitelj", supplier_lot_no: "NOVA", qty: "10", unit: "kg" },
  ],
};
let container: HTMLDivElement;
let root: Root;
let onStarted: ReturnType<typeof vi.fn>;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listLines).mockReset().mockResolvedValue([{ id: 10, name: "Linija 1" }]);
  vi.mocked(previewBatch).mockReset().mockResolvedValue(preview);
  vi.mocked(startBatch).mockReset().mockResolvedValue(batch);
  onStarted = vi.fn();
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function render(values = orders) {
  await act(async () => root.render(<StartBatch orders={values} loadingOrders={false} onStarted={onStarted} />));
}
function button(text: string) { return Array.from(container.querySelectorAll("button")).find(item => item.textContent === text)!; }
function select(id: string, value: string) {
  act(() => {
    const control = container.querySelector<HTMLSelectElement>(`#${id}`)!;
    control.value = value;
    control.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
function quantity(value: string) {
  act(() => {
    const control = container.querySelector<HTMLInputElement>("#batch-qty")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(control, value);
    control.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function fill() { select("batch-order", "1"); select("batch-line", "10"); quantity("500"); }
async function check() { await act(async () => button("Preveri zaloge").click()); }
async function submit() {
  await act(async () => { container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

it("pred zagonom zahteva predogled in pokaže potrebno ter razpoložljivo zalogo", async () => {
  await render(); fill(); quantity("500,000");
  expect(button("Zaženi šaržo").disabled).toBe(true);
  await check();
  expect(previewBatch).toHaveBeenCalledWith(1, { line_id: 10, qty: "500.000" }, expect.any(AbortSignal));
  expect(container.textContent).toContain("40 kg");
  expect(container.textContent).toContain("90 kg");
  expect(container.textContent).toContain("OK");
  expect(button("Zaženi šaržo").disabled).toBe(false);
});

it("ob pomanjkanju zaloge onemogoči zagon", async () => {
  vi.mocked(previewBatch).mockResolvedValue({ ...preview, can_start: false, requirements: [{ ...preview.requirements[0], available_qty: "10", missing_qty: "30", status: "PREMALO" }] });
  await render(); fill(); await check();
  expect(container.textContent).toContain("PREMALO");
  expect(container.textContent).toContain("30 kg");
  expect(button("Zaženi šaržo").disabled).toBe(true);
  await submit();
  expect(startBatch).not.toHaveBeenCalled();
});

it("po uspešnem zagonu odpre kodo in FIFO porabo ter osveži naloge", async () => {
  await render(); fill(); await check(); await submit();
  expect(startBatch).toHaveBeenCalledWith(1, { line_id: 10, qty: "500" });
  expect(onStarted).toHaveBeenCalledOnce();
  expect(container.textContent).toContain(batch.batch_code);
  expect(container.textContent).toContain("STARA");
  expect(container.textContent).toContain("NOVA");
  expect(container.querySelectorAll('table[aria-label="Poraba zagnane šarže"] tbody tr').length).toBe(2);
  expect(document.activeElement).toBe(container.querySelector("#started-batch-title"));
});

it("sprememba količine odstrani predogled in prepreči zagon", async () => {
  await render(); fill(); await check(); quantity("1000");
  expect(container.querySelector("#batch-stock-title")).toBeNull();
  expect(button("Zaženi šaržo").disabled).toBe(true);
  await submit();
  expect(startBatch).not.toHaveBeenCalled();
});

it("ignorira predogled, ki prispe po spremembi vnosa", async () => {
  let resolve!: (result: BatchPreview) => void;
  vi.mocked(previewBatch).mockReturnValueOnce(new Promise<BatchPreview>(done => { resolve = done; }));
  await render(); fill(); await check(); quantity("1000");
  await act(async () => resolve(preview));
  expect(container.querySelector("#batch-stock-title")).toBeNull();
  expect(button("Zaženi šaržo").disabled).toBe(true);
});

it("ob zmanjšanju zaloge po predogledu pokaže manjkajoče količine in zahteva nov pregled", async () => {
  const missing = [{ ...preview.requirements[0], available_qty: "1", missing_qty: "39", status: "PREMALO" as const }];
  vi.mocked(startBatch).mockRejectedValueOnce(new BatchApiError("Za zagon šarže ni dovolj zaloge.", {}, 409, missing));
  await render(); fill(); await check(); await submit();
  expect(container.textContent).toContain("Za zagon šarže ni dovolj zaloge.");
  expect(container.textContent).toContain("39 kg");
  expect(container.textContent).toContain("PREMALO");
  expect(button("Zaženi šaržo").disabled).toBe(true);
  expect(onStarted).not.toHaveBeenCalled();
});

it.each(["0", "-1", "1.0001", "1000000000"])("pred API zavrne neveljavno količino %s", async value => {
  await render(); fill(); quantity(value); await check();
  expect(previewBatch).not.toHaveBeenCalled();
  expect(container.querySelector("#batch-qty-error")).not.toBeNull();
});

it("zahteva nalog, linijo in količino", async () => {
  await render(); await check();
  expect(previewBatch).not.toHaveBeenCalled();
  for (const id of ["batch-order_id-error", "batch-line_id-error", "batch-qty-error"]) expect(container.querySelector(`#${id}`)).not.toBeNull();
});

it("ne ponudi odpovedanih ali zaključenih nalogov", async () => {
  await render([order, { ...order, id: 2, status: "cancelled" }, { ...order, id: 3, status: "done" }]);
  expect(Array.from(container.querySelectorAll("#batch-order option"), item => item.getAttribute("value"))).toEqual(["", "1"]);
});

it("brez aktivnih linij onemogoči obrazec", async () => {
  vi.mocked(listLines).mockResolvedValue([]);
  await render();
  expect(container.textContent).toContain("Ni aktivnih proizvodnih linij.");
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
});

it("med zagonom prepreči ponovljen zahtevek", async () => {
  let resolve!: (result: Batch) => void;
  vi.mocked(startBatch).mockReturnValueOnce(new Promise<Batch>(done => { resolve = done; }));
  await render(); fill(); await check(); await submit(); await submit();
  expect(startBatch).toHaveBeenCalledOnce();
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
  await act(async () => resolve(batch));
  expect(onStarted).toHaveBeenCalledOnce();
});
