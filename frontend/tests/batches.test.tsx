// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { User } from "../src/api/auth";
import { BatchApiError, finishBatch, getBatch, listBatches } from "../src/api/batches";
import type { Batch } from "../src/api/batches";
import { Batches } from "../src/pages/Batches";

vi.mock("../src/pages/QualityMeasurements", () => ({ QualityMeasurements: () => <p>Testni prikaz meritev kakovosti</p> }));

vi.mock("../src/api/batches", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/batches")>();
  return { ...actual, finishBatch: vi.fn(), getBatch: vi.fn(), listBatches: vi.fn() };
});

const operator: User = { id: 7, name: "Operater", email: "operator@pijacai.local", role: "operator", active: true };
const batch: Batch = {
  id: 6, batch_code: "2026-11-09-L10-01", order_id: 1, product_id: 2, product_name: "Sok", product_unit: "kos",
  recipe_id: 3, recipe_version: 1, line_id: 10, line_name: "Linija 1", operator_id: 7,
  status: "in_production", planned_qty: "500.000", produced_qty: 0, rejected_qty: 0,
  started_at: "2026-11-09T10:00:00Z", finished_at: null,
  consumptions: [{ material_lot_id: 30, material_id: 20, material_name: "Koncentrat", supplier_name: "Dobavitelj", supplier_lot_no: "SER-1", qty: "40", unit: "kg" }],
};
const finished: Batch = { ...batch, status: "awaiting_qc", produced_qty: 480, rejected_qty: 5, finished_at: "2026-11-09T11:00:00Z" };
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listBatches).mockReset().mockResolvedValue([batch]);
  vi.mocked(getBatch).mockReset().mockResolvedValue(batch);
  vi.mocked(finishBatch).mockReset().mockResolvedValue(finished);
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function render(user = operator) {
  await act(async () => root.render(<Batches user={user} />));
}
function button(text: string) {
  return Array.from(container.querySelectorAll("button")).find(item => item.textContent === text)!;
}
async function open() { await act(async () => button("Odpri").click()); }
function input(id: string, value: string) {
  act(() => {
    const control = container.querySelector<HTMLInputElement>(`#${id}`)!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(control, value);
    control.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function fill(produced = "480", rejected = "5") { input("finish-produced", produced); input("finish-rejected", rejected); }
async function submit() {
  await act(async () => { container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

it("naloži samo aktivne šarže in odpre podrobnosti s porabo", async () => {
  await render();
  expect(listBatches).toHaveBeenCalledWith("in_production", expect.any(AbortSignal));
  await open();
  expect(getBatch).toHaveBeenCalledWith(6, expect.any(AbortSignal));
  expect(container.textContent).toContain("SER-1");
  expect(container.textContent).toContain("40 kg");
  expect(container.querySelector("form")).not.toBeNull();
  expect(container.textContent).not.toContain("Testni prikaz meritev kakovosti");
  expect(document.activeElement).toBe(container.querySelector("#batch-detail-title"));
});

it("preda lastno šaržo, odstrani obrazec in osveži aktivni seznam", async () => {
  await render(); await open(); fill();
  vi.mocked(listBatches).mockResolvedValue([]);
  await submit();
  expect(finishBatch).toHaveBeenCalledWith(6, { produced_qty: 480, rejected_qty: 5 });
  expect(container.textContent).toContain(`Šarža ${batch.batch_code} je predana v kontrolo.`);
  expect(container.textContent).toContain("Čaka na kontrolo");
  expect(container.textContent).toContain("Proizvedeno: 480 kos");
  expect(container.textContent).toContain("Izmet: 5 kos");
  expect(container.textContent).toContain("Ni aktivnih šarž.");
  expect(container.querySelector("form")).toBeNull();
  expect(listBatches).toHaveBeenCalledTimes(2);
});

it.each([["0", "0"], ["500", "500"], ["2147483647", "0"]])("dovoli robni količini %s in %s", async (produced, rejected) => {
  await render(); await open(); fill(produced, rejected); await submit();
  expect(finishBatch).toHaveBeenCalledWith(6, { produced_qty: Number(produced), rejected_qty: Number(rejected) });
});

it.each([
  ["", "0", "produced"], ["500", "", "rejected"], ["-1", "0", "produced"],
  ["500", "-1", "rejected"], ["1.5", "0", "produced"], ["500", "1,5", "rejected"],
  ["2147483648", "0", "produced"], ["500", "2147483648", "rejected"], ["1e2", "0", "produced"],
])("pred API zavrne neveljavni količini %s in %s", async (produced, rejected, field) => {
  await render(); await open(); fill(produced, rejected); await submit();
  expect(finishBatch).not.toHaveBeenCalled();
  expect(container.querySelector(`#finish-${field}-error`)).not.toBeNull();
});

it("izmet nad proizvodnjo označi ob polju izmeta", async () => {
  await render(); await open(); fill("10", "11"); await submit();
  expect(finishBatch).not.toHaveBeenCalled();
  expect(container.querySelector("#finish-rejected-error")?.textContent).toBe("Izmet ne sme presegati proizvedene količine.");
});

it("drugi operater vidi podrobnosti brez možnosti zaključka", async () => {
  await render({ ...operator, id: 8 }); await open();
  expect(container.querySelector("form")).toBeNull();
  expect(container.textContent).toContain("Šaržo lahko zaključi samo operater, ki jo je zagnal.");
  expect(finishBatch).not.toHaveBeenCalled();
});

it("kontrolor vidi čakalno vrsto in podrobnosti brez obrazca zaključka", async () => {
  vi.mocked(listBatches).mockResolvedValue([finished]);
  vi.mocked(getBatch).mockResolvedValue(finished);
  await render({ ...operator, id: 8, role: "quality" }); await open();
  expect(listBatches).toHaveBeenCalledWith("awaiting_qc", expect.any(AbortSignal));
  expect(container.querySelector('table[aria-label="Čakalna vrsta kontrole"]')).not.toBeNull();
  expect(container.textContent).toContain("Testni prikaz meritev kakovosti");
  expect(container.textContent).toContain("Čaka na kontrolo");
  expect(container.querySelector("form")).toBeNull();
});

it.each(["awaiting_qc", "released", "rejected"] as const)("zastareli seznam ne omogoči zaključka šarže v stanju %s", async status => {
  vi.mocked(getBatch).mockResolvedValue({ ...finished, status });
  await render(); await open();
  expect(container.querySelector("form")).toBeNull();
});

it("validacijsko napako API prikaže ob polju in ohrani vnos", async () => {
  vi.mocked(finishBatch).mockRejectedValueOnce(new BatchApiError("Preveri podatke šarže.", { rejected_qty: "Napaka izmeta." }, 422));
  await render(); await open(); fill(); await submit();
  expect(container.querySelector("#finish-rejected-error")?.textContent).toBe("Napaka izmeta.");
  expect(container.querySelector<HTMLInputElement>("#finish-produced")!.value).toBe("480");
  expect(container.querySelector<HTMLInputElement>("#finish-rejected")!.value).toBe("5");
});

it("ob konfliktu osveži stanje in prepreči ponovno urejanje", async () => {
  await render(); await open(); fill();
  vi.mocked(finishBatch).mockRejectedValueOnce(new BatchApiError("Šarža je že zaključena.", {}, 409));
  vi.mocked(getBatch).mockResolvedValue(finished);
  vi.mocked(listBatches).mockResolvedValue([]);
  await submit();
  expect(container.textContent).toContain("Šarža je že zaključena.");
  expect(container.textContent).toContain("Čaka na kontrolo");
  expect(container.querySelector("form")).toBeNull();
  expect(getBatch).toHaveBeenCalledTimes(2);
});

it("med predajo onemogoči dvojno pošiljanje in zamenjavo šarže", async () => {
  let resolve!: (value: Batch) => void;
  vi.mocked(finishBatch).mockReturnValueOnce(new Promise<Batch>(done => { resolve = done; }));
  await render(); await open(); fill(); await submit(); await submit();
  expect(finishBatch).toHaveBeenCalledOnce();
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
  expect(button("Osveži šarže").disabled).toBe(true);
  await act(async () => resolve(finished));
  expect(container.querySelector("form")).toBeNull();
});

it("ignorira pozne podrobnosti prej izbrane šarže", async () => {
  const second = { ...batch, id: 9, batch_code: "DRUGA" };
  vi.mocked(listBatches).mockResolvedValue([batch, second]);
  let resolve!: (value: Batch) => void;
  vi.mocked(getBatch).mockReturnValueOnce(new Promise<Batch>(done => { resolve = done; })).mockResolvedValueOnce(second);
  await render(); await open();
  await act(async () => container.querySelector<HTMLButtonElement>('button[aria-label="Odpri šaržo DRUGA"]')!.click());
  await act(async () => resolve(batch));
  expect(container.querySelector("#batch-detail-title")?.textContent).toBe("Šarža DRUGA");
});

it("pokaže napako nalaganja in omogoči ponovno osvežitev", async () => {
  vi.mocked(listBatches).mockRejectedValueOnce(new Error("Povezava ni uspela."));
  await render();
  expect(container.textContent).toContain("Povezava ni uspela.");
  await act(async () => button("Osveži šarže").click());
  expect(container.textContent).not.toContain("Povezava ni uspela.");
  expect(button("Odpri")).toBeDefined();
});

it("neuspešno nalaganje podrobnosti ne prikaže obrazca", async () => {
  vi.mocked(getBatch).mockRejectedValueOnce(new BatchApiError("Šarža ni najdena.", {}, 404));
  await render(); await open();
  expect(container.textContent).toContain("Šarža ni najdena.");
  expect(container.querySelector("form")).toBeNull();
});
