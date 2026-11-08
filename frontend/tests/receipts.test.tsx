// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { InventoryApiError, listMaterialLots, listMaterials, listSuppliers, receiveMaterial } from "../src/api/inventory";
import type { MaterialLot } from "../src/api/inventory";
import { ReceiveMaterials } from "../src/pages/ReceiveMaterials";

vi.mock("../src/api/inventory", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/inventory")>();
  return { ...actual, listMaterialLots: vi.fn(), listMaterials: vi.fn(), listSuppliers: vi.fn(), receiveMaterial: vi.fn() };
});

const existing: MaterialLot = {
  id: 1, material_id: 10, supplier_id: 20, supplier_lot_no: "PRVA",
  received_qty: "0.100", remaining_qty: "0.100", unit_cost: "1.500",
  received_by: 2, received_at: "2026-11-08T10:00:00Z",
};
const created: MaterialLot = { ...existing, id: 2, supplier_lot_no: "NOVA", received_qty: "0.200", remaining_qty: "0.200", unit_cost: "0" };
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listMaterials).mockReset().mockResolvedValue([
    { id: 10, name: "Koncentrat", type: "ingredient", unit: "kg" },
    { id: 11, name: "Plastenka", type: "packaging", unit: "kos" },
  ]);
  vi.mocked(listSuppliers).mockReset().mockResolvedValue([{ id: 20, name: "Dobavitelj" }]);
  vi.mocked(listMaterialLots).mockReset().mockResolvedValue([existing]);
  vi.mocked(receiveMaterial).mockReset().mockResolvedValue(created);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function render() {
  await act(async () => root.render(<ReceiveMaterials />));
}

function fill(name: string, value: string) {
  const control = container.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`)!;
  act(() => {
    if (control instanceof HTMLSelectElement) {
      control.value = value;
      control.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(control, value);
      control.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
}

function fillForm() {
  fill("material_id", "10"); fill("supplier_id", "20"); fill("supplier_lot_no", " NOVA ");
  fill("received_qty", "0,200"); fill("unit_cost", "0");
}

async function submit() {
  await act(async () => {
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

it("naloži surovine, embalažo, dobavitelje in prejete serije", async () => {
  await render();
  expect(container.textContent).toContain("Koncentrat (surovina, kg)");
  expect(container.textContent).toContain("Plastenka (embalaža, kos)");
  expect(container.querySelectorAll("tbody tr").length).toBe(1);
  expect(container.querySelector("fieldset")!.disabled).toBe(false);
});

it("shrani decimalne nize, osveži serije in natančno sešteje zalogo", async () => {
  vi.mocked(listMaterialLots).mockResolvedValueOnce([existing]).mockResolvedValueOnce([existing, created]);
  await render(); fillForm(); await submit();
  expect(receiveMaterial).toHaveBeenCalledWith({
    material_id: 10, supplier_id: 20, supplier_lot_no: "NOVA", received_qty: "0.200", unit_cost: "0",
  });
  expect(listMaterialLots).toHaveBeenCalledTimes(2);
  expect(container.querySelectorAll("tbody tr").length).toBe(2);
  expect(container.querySelector("strong")?.textContent).toBe("0,300 kg");
  expect(container.textContent).toContain("Prejem je shranjen.");
  expect(container.querySelector<HTMLInputElement>('[name="supplier_lot_no"]')!.value).toBe("");
});

it("podvojeno serijo prikaže ob polju in ohrani vnos", async () => {
  vi.mocked(receiveMaterial).mockRejectedValue(new InventoryApiError("Ta serija je že vnesena.", { supplier_lot_no: "Ta serija je že vnesena." }));
  await render(); fillForm(); await submit();
  expect(container.querySelector("#receipt-supplier_lot_no-error")?.textContent).toBe("Ta serija je že vnesena.");
  expect(container.querySelector<HTMLInputElement>('[name="received_qty"]')!.value).toBe("0,200");
  expect(container.querySelectorAll("tbody tr").length).toBe(1);
});

it.each([
  ["received_qty", "0"], ["received_qty", "-1"], ["received_qty", "1.0001"],
  ["received_qty", "1000000000"], ["unit_cost", "-1"], ["unit_cost", "NaN"],
])("pred API zavrne neveljavno vrednost %s=%s", async (field, value) => {
  await render(); fillForm(); fill(field, value); await submit();
  expect(receiveMaterial).not.toHaveBeenCalled();
  expect(container.querySelector(`#receipt-${field}-error`)).not.toBeNull();
});

it("označi vsa manjkajoča polja", async () => {
  await render(); await submit();
  expect(receiveMaterial).not.toHaveBeenCalled();
  for (const field of ["material_id", "supplier_id", "supplier_lot_no", "received_qty", "unit_cost"]) {
    expect(container.querySelector(`#receipt-${field}-error`)).not.toBeNull();
  }
});

it("onemogoči obrazec, če ni dobaviteljev", async () => {
  vi.mocked(listSuppliers).mockResolvedValue([]);
  await render();
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
  expect(container.textContent).toContain("Za vnos prejema potrebujete vsaj eno surovino in dobavitelja.");
});

it("med shranjevanjem ne pošlje dvojnega prejema", async () => {
  let resolve!: (value: MaterialLot) => void;
  vi.mocked(receiveMaterial).mockReturnValue(new Promise<MaterialLot>(done => { resolve = done; }));
  await render(); fillForm(); await submit(); await submit();
  expect(receiveMaterial).toHaveBeenCalledOnce();
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
  await act(async () => { resolve(created); });
  expect(container.querySelector("fieldset")!.disabled).toBe(false);
});

it("ob neuspešni osvežitvi po uspešnem zapisu ne prijavi neuspešnega shranjevanja", async () => {
  vi.mocked(listMaterialLots).mockResolvedValueOnce([existing]).mockRejectedValueOnce(new Error("Osvežitev ni uspela."));
  await render(); fillForm(); await submit();
  expect(container.textContent).toContain("Prejem je shranjen.");
  expect(container.textContent).toContain("Osvežitev ni uspela.");
  expect(container.querySelectorAll("tbody tr").length).toBe(2);
  expect(container.querySelector("strong")).toBeNull();
});

it("pri zalogi ne združuje različnih surovin in merskih enot", async () => {
  vi.mocked(listMaterialLots).mockResolvedValue([
    existing, { ...existing, id: 2, material_id: 11, received_qty: "999.000", remaining_qty: "999.000" },
  ]);
  await render();
  fill("material_id", "10");
  expect(container.querySelector("strong")?.textContent).toBe("0,100 kg");
  fill("material_id", "11");
  expect(container.querySelector("strong")?.textContent).toBe("999,000 kos");
});

it("napako nalaganja odpravi s ponovnim poskusom", async () => {
  vi.mocked(listMaterials).mockRejectedValueOnce(new Error("Šifranta ni mogoče naložiti."));
  await render();
  expect(container.textContent).toContain("Šifranta ni mogoče naložiti.");
  const refresh = Array.from(container.querySelectorAll("button")).find(item => item.textContent === "Osveži podatke")!;
  await act(async () => refresh.click());
  expect(container.querySelector("fieldset")!.disabled).toBe(false);
  expect(container.textContent).not.toContain("Šifranta ni mogoče naložiti.");
});

it("neuspešno shranjevanje ohrani polja in ne spremeni zaloge", async () => {
  vi.mocked(receiveMaterial).mockRejectedValueOnce(new Error("Povezava s strežnikom ni uspela."));
  await render(); fillForm(); await submit();
  expect(container.querySelector<HTMLInputElement>('[name="supplier_lot_no"]')!.value).toBe(" NOVA ");
  expect(container.querySelector<HTMLInputElement>('[name="received_qty"]')!.value).toBe("0,200");
  expect(container.querySelector("strong")?.textContent).toBe("0,100 kg");
  expect(container.querySelector("fieldset")!.disabled).toBe(false);
  expect(container.querySelector(".success")).toBeNull();
});

it("napako validacije iz API prikaže ob količini", async () => {
  vi.mocked(receiveMaterial).mockRejectedValueOnce(new InventoryApiError("Preveri podatke prejema.", { received_qty: "Preveri vneseno vrednost." }));
  await render(); fillForm(); await submit();
  expect(container.querySelector("#receipt-received_qty-error")?.textContent).toBe("Preveri vneseno vrednost.");
  expect(container.querySelector('[name="received_qty"]')?.getAttribute("aria-invalid")).toBe("true");
});
