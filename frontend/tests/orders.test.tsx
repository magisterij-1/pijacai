// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createOrder, listOrders, listProducts, OrderApiError, previewOrder } from "../src/api/orders";
import type { Order, OrderPreview } from "../src/api/orders";
import { Orders } from "../src/pages/Orders";
import { formatDecimal } from "../src/quantities";

vi.mock("../src/api/orders", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/orders")>();
  return { ...actual, createOrder: vi.fn(), listOrders: vi.fn(), listProducts: vi.fn(), previewOrder: vi.fn() };
});

const preview: OrderPreview = {
  product_id: 10, product_name: "Jabolčni sok", product_unit: "kos", planned_qty: 500,
  recipe_id: 20, recipe_version: 1, output_qty: "1000.000",
  requirements: [
    { material_id: 1, material_name: "Koncentrat", material_type: "ingredient", unit: "kg", required_qty: "40.000" },
    { material_id: 2, material_name: "Sladkor", material_type: "ingredient", unit: "kg", required_qty: "12.500" },
    { material_id: 3, material_name: "Plastenka", material_type: "packaging", unit: "kos", required_qty: "500" },
  ],
};
const existing: Order = { ...preview, id: 1, planned_date: "2099-01-01", status: "planned", created_by: 5 };
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listProducts).mockReset().mockResolvedValue([{ id: 10, name: "Jabolčni sok", sku: "SOK", unit: "kos" }]);
  vi.mocked(listOrders).mockReset().mockResolvedValue([existing]);
  vi.mocked(previewOrder).mockReset().mockResolvedValue(preview);
  vi.mocked(createOrder).mockReset().mockResolvedValue({ ...existing, id: 2 });
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
});

afterEach(() => { act(() => root.unmount()); container.remove(); });

async function render(role: "planner" | "operator" = "planner") {
  await act(async () => root.render(<Orders role={role} />));
}

function button(text: string): HTMLButtonElement {
  return Array.from(container.querySelectorAll("button")).find(item => item.textContent === text)!;
}

function input(id: string, value: string) {
  const element = container.querySelector<HTMLInputElement>(`#${id}`)!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function fillForm() {
  act(() => {
    const select = container.querySelector<HTMLSelectElement>("#order-product")!;
    select.value = "10";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  input("order-quantity", "500"); input("order-date", "2099-01-01");
}

async function calculate() { await act(async () => button("Izračunaj potrebne količine").click()); }
async function submit() {
  await act(async () => {
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

it("zahteva predogled pred potrditvijo in prikaže potrebne količine", async () => {
  await render(); fillForm();
  expect(button("Potrdi nalog").disabled).toBe(true);
  await calculate();
  expect(previewOrder).toHaveBeenCalledWith({ product_id: 10, planned_qty: 500 }, expect.any(AbortSignal));
  const result = container.querySelector('[aria-labelledby="order-preview-title"]')!;
  expect(result.textContent).toContain("40 kg");
  expect(result.textContent).toContain("12,5 kg");
  expect(result.textContent).toContain("500 kos");
  expect(button("Potrdi nalog").disabled).toBe(false);
});

it("po spremembi količine zahteva nov predogled", async () => {
  await render(); fillForm(); await calculate();
  input("order-quantity", "1000");
  expect(container.querySelector("#order-preview-title")).toBeNull();
  expect(button("Potrdi nalog").disabled).toBe(true);
  await submit();
  expect(createOrder).not.toHaveBeenCalled();
});

it("ustvari nalog s predogledano recepturo in osveži seznam", async () => {
  vi.mocked(listOrders).mockResolvedValueOnce([existing]).mockResolvedValueOnce([existing, { ...existing, id: 2 }]);
  await render(); fillForm(); await calculate(); await submit();
  expect(createOrder).toHaveBeenCalledWith({ product_id: 10, planned_qty: 500, planned_date: "2099-01-01", recipe_id: 20 });
  expect(listOrders).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain("Proizvodni nalog #2 je ustvarjen.");
  const table = container.querySelector('table[aria-label="Proizvodni nalogi"]')!;
  expect(table.querySelector("tbody")!.children.length).toBe(2);
});

it("operaterju prikaže seznam brez obrazca in brez branja izdelkov", async () => {
  await render("operator");
  expect(container.querySelector("form")).toBeNull();
  expect(listProducts).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Načrtovan");
  expect(container.textContent).toContain("Verzija 1");
});

it.each(["0", "1.5"])("zavrne neveljavno celo količino %s", async quantity => {
  await render(); fillForm(); input("order-quantity", quantity); await calculate();
  expect(previewOrder).not.toHaveBeenCalled();
  expect(container.querySelector("#order-planned_qty-error")).not.toBeNull();
});

it("ne potrdi naloga s preteklim datumom", async () => {
  await render(); fillForm(); await calculate(); input("order-date", "2000-01-01"); await submit();
  expect(createOrder).not.toHaveBeenCalled();
  expect(container.querySelector("#order-planned_date-error")).not.toBeNull();
});

it("ob spremenjeni recepturi odstrani predogled in zahteva ponovni izračun", async () => {
  vi.mocked(createOrder).mockRejectedValueOnce(new OrderApiError("Receptura se je spremenila. Ponovno preveri potrebne količine.", {}, 409));
  await render(); fillForm(); await calculate(); await submit();
  expect(container.textContent).toContain("Receptura se je spremenila.");
  expect(container.querySelector("#order-preview-title")).toBeNull();
  expect(button("Potrdi nalog").disabled).toBe(true);
});

it("ignorira star predogled po spremembi količine med nalaganjem", async () => {
  let resolve!: (value: OrderPreview) => void;
  vi.mocked(previewOrder).mockReturnValueOnce(new Promise<OrderPreview>(done => { resolve = done; }));
  await render(); fillForm(); await calculate(); input("order-quantity", "1000");
  await act(async () => resolve(preview));
  expect(container.querySelector("#order-preview-title")).toBeNull();
  expect(button("Potrdi nalog").disabled).toBe(true);
});

it("onemogoči obrazec, če ni izdelkov z aktivno recepturo", async () => {
  vi.mocked(listProducts).mockResolvedValue([]);
  await render();
  expect(container.textContent).toContain("Ni izdelkov z aktivno recepturo.");
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
});

it("po napaki seznama omogoči osvežitev", async () => {
  vi.mocked(listOrders).mockRejectedValueOnce(new Error("Nalaganje ni uspelo."));
  await render("operator");
  expect(container.textContent).toContain("Nalaganje ni uspelo.");
  await act(async () => button("Osveži naloge").click());
  expect(container.querySelector('table[aria-label="Proizvodni nalogi"]')).not.toBeNull();
});

it.each([
  ["1.23456", "1,23456"], ["1E-7", "0,0000001"],
  ["9007199254740.993", "9.007.199.254.740,993"],
])("natančno oblikuje količino %s", (value, expected) => {
  expect(formatDecimal(value)).toBe(expected);
});
