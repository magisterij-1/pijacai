// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getStock, listMaterials } from "../src/api/inventory";
import type { Stock as StockData, StockLot } from "../src/api/inventory";
import { Stock } from "../src/pages/Stock";

vi.mock("../src/api/inventory", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/inventory")>();
  return { ...actual, getStock: vi.fn(), listMaterials: vi.fn() };
});

const early: StockLot = {
  id: 1, material_id: 10, material_name: "Koncentrat", material_type: "ingredient", unit: "kg",
  supplier_id: 20, supplier_name: "Dobavitelj", supplier_lot_no: "ZGODNJA",
  received_qty: "0.100", remaining_qty: "0.100", unit_cost: "1.000", received_by: 2,
  received_at: "2026-11-01T10:00:00Z",
};
const late: StockLot = { ...early, id: 2, supplier_lot_no: "POZNA", received_qty: "0.200", remaining_qty: "0.200", received_at: "2026-11-02T10:00:00Z" };
const data: StockData = {
  lots: [early, late],
  totals: [{ material_id: 10, material_name: "Koncentrat", unit: "kg", remaining_qty: "0.300" }],
};
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listMaterials).mockReset().mockResolvedValue([
    { id: 10, name: "Koncentrat", type: "ingredient", unit: "kg" },
    { id: 11, name: "Plastenka", type: "packaging", unit: "kos" },
  ]);
  vi.mocked(getStock).mockReset().mockResolvedValue(data);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function render() {
  await act(async () => root.render(<Stock />));
}

async function selectMaterial(value: string) {
  await act(async () => {
    const select = container.querySelector("select")!;
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

it("prikaže imena, dobavitelja, količine in vrstni red serij iz API", async () => {
  await render();
  const rows = container.querySelectorAll("tbody tr");
  expect(rows.length).toBe(2);
  expect(rows[0].textContent).toContain("ZGODNJA");
  expect(rows[1].textContent).toContain("POZNA");
  expect(rows[0].textContent).toContain("Dobavitelj");
  expect(container.querySelector("strong")?.textContent).toBe("0,300 kg");
  expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(false);
});

it("sprememba in odstranitev filtra zahtevata pravo surovino", async () => {
  await render();
  await selectMaterial("10");
  expect(getStock).toHaveBeenLastCalledWith({ material_id: 10, include_consumed: false }, expect.any(AbortSignal));
  expect(container.textContent).toContain("Skupna zaloga izbrane surovine");
  await selectMaterial("");
  expect(getStock).toHaveBeenLastCalledWith({ material_id: undefined, include_consumed: false }, expect.any(AbortSignal));
});

it("stikalo vključi porabljene serije brez spremembe vsote", async () => {
  const consumed = { ...early, id: 3, supplier_lot_no: "PORABLJENA", remaining_qty: "0.000" };
  vi.mocked(getStock).mockResolvedValueOnce(data).mockResolvedValueOnce({ ...data, lots: [early, late, consumed] });
  await render();
  await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  expect(getStock).toHaveBeenLastCalledWith({ material_id: undefined, include_consumed: true }, expect.any(AbortSignal));
  expect(container.querySelectorAll("tbody tr").length).toBe(3);
  expect(container.querySelector("strong")?.textContent).toBe("0,300 kg");
});

it("prazno zalogo izbrane surovine prikaže z ničelno vsoto", async () => {
  vi.mocked(getStock).mockResolvedValue({ lots: [], totals: [{ material_id: 10, material_name: "Koncentrat", unit: "kg", remaining_qty: "0.000" }] });
  await render(); await selectMaterial("10");
  expect(container.textContent).toContain("Ni serij za izbrane pogoje.");
  expect(container.querySelector("strong")?.textContent).toBe("0,000 kg");
  expect(container.querySelector("table")).toBeNull();
});

it("vsote različnih surovin in enot ostanejo ločene", async () => {
  vi.mocked(getStock).mockResolvedValue({ ...data, totals: [
    ...data.totals, { material_id: 11, material_name: "Plastenka", unit: "kos", remaining_qty: "7.000" },
  ] });
  await render();
  expect(Array.from(container.querySelectorAll("strong"), item => item.textContent)).toEqual(["0,300 kg", "7,000 kos"]);
});

it("po napaki omogoči ponovno nalaganje", async () => {
  vi.mocked(getStock).mockRejectedValueOnce(new Error("Zalog ni mogoče naložiti."));
  await render();
  expect(container.textContent).toContain("Zalog ni mogoče naložiti.");
  const refresh = container.querySelector("button")!;
  await act(async () => refresh.click());
  expect(container.querySelectorAll("tbody tr").length).toBe(2);
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

it("ob neuspešni osvežitvi ne prikazuje prejšnje zaloge kot aktualne", async () => {
  vi.mocked(getStock).mockResolvedValueOnce(data).mockRejectedValueOnce(new Error("Osvežitev ni uspela."));
  await render();
  await act(async () => container.querySelector("button")!.click());
  expect(container.textContent).toContain("Osvežitev ni uspela.");
  expect(container.querySelector("table")).toBeNull();
  expect(container.querySelector("strong")).toBeNull();
});

it("po hitri spremembi filtra ignorira starejši odgovor", async () => {
  const pending: Array<(value: StockData) => void> = [];
  vi.mocked(getStock).mockImplementation(() => new Promise(resolve => pending.push(resolve)));
  await render();
  await selectMaterial("10");
  expect(pending.length).toBe(2);
  await act(async () => pending[1](data));
  expect(container.querySelector("strong")?.textContent).toBe("0,300 kg");
  await act(async () => pending[0]({ ...data, totals: [{ ...data.totals[0], remaining_qty: "999.000" }] }));
  expect(container.querySelector("strong")?.textContent).toBe("0,300 kg");
});

it("pri praznem pregledu vseh surovin ne izmisli skupne vsote", async () => {
  vi.mocked(getStock).mockResolvedValue({ lots: [], totals: [] });
  await render();
  expect(container.textContent).toContain("Ni serij za izbrane pogoje.");
  expect(container.querySelector("strong")).toBeNull();
  expect(container.querySelector("table")).toBeNull();
});

it("ročna osvežitev ohrani filter in vključitev porabljenih serij", async () => {
  await render();
  await selectMaterial("10");
  await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  await act(async () => container.querySelector("button")!.click());
  expect(getStock).toHaveBeenLastCalledWith({ material_id: 10, include_consumed: true }, expect.any(AbortSignal));
  expect(container.querySelector<HTMLSelectElement>("select")!.value).toBe("10");
  expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(true);
});

it("velike decimalne vsote prikaže brez izgube zadnjih tisočink", async () => {
  vi.mocked(getStock).mockResolvedValue({ ...data, totals: [{ ...data.totals[0], remaining_qty: "9007199254740.993" }] });
  await render();
  expect(container.querySelector("strong")?.textContent).toBe("9.007.199.254.740,993 kg");
});

it("napako šifranta prikaže ločeno od uspešno naložene zaloge", async () => {
  vi.mocked(listMaterials).mockRejectedValueOnce(new Error("Šifranta ni mogoče naložiti."));
  await render();
  expect(container.textContent).toContain("Šifranta ni mogoče naložiti.");
  expect(container.querySelectorAll("tbody tr").length).toBe(2);
  await act(async () => container.querySelector("button")!.click());
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(container.querySelectorAll("option").length).toBe(3);
});

it("izbrisana izbrana surovina prikaže napako namesto stare zaloge", async () => {
  vi.mocked(getStock).mockResolvedValueOnce(data).mockRejectedValueOnce(new Error("Surovina ni najdena."));
  await render(); await selectMaterial("10");
  expect(container.textContent).toContain("Surovina ni najdena.");
  expect(container.querySelector("table")).toBeNull();
  expect(container.querySelector("strong")).toBeNull();
});

it("napaka stare zahteve ne prepiše novega uspešnega filtra", async () => {
  let rejectOld!: (error: Error) => void;
  vi.mocked(getStock).mockReturnValueOnce(new Promise((_resolve, reject) => { rejectOld = reject; })).mockResolvedValueOnce(data);
  await render(); await selectMaterial("10");
  await act(async () => rejectOld(new Error("Zastarela napaka.")));
  expect(container.textContent).not.toContain("Zastarela napaka.");
  expect(container.querySelector("strong")?.textContent).toBe("0,300 kg");
});
