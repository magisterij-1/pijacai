// — izbor serije in prikaz povezanih šarž.
// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { findTraceLots, listTraceMaterials, traceLot, TraceabilityApiError } from "../src/api/traceability";
import type { LotTraceability as LotResult, TraceLot } from "../src/api/traceability";
import { LotTraceability } from "../src/pages/LotTraceability";

vi.mock("../src/api/traceability", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/traceability")>();
  return { ...actual, findTraceLots: vi.fn(), listTraceMaterials: vi.fn(), traceLot: vi.fn() };
});
const lot: TraceLot = { id: 30, material_id: 20, material_name: "Koncentrat", unit: "kg", supplier_id: 1, supplier_name: "Dobavitelj A",
  supplier_lot_no: "SER-1", received_qty: "60.000", remaining_qty: "19.875", received_at: "2026-11-01T10:00:00Z" };
const result: LotResult = { ...lot, total_consumed_qty: "40.125", batches: [
  { batch_id: 6, batch_code: "STAREJŠA", product_id: 2, product_name: "Sok", started_at: "2026-11-02T10:00:00Z", status: "released", consumed_qty: "30.000" },
  { batch_id: 7, batch_code: "NOVEJŠA", product_id: 2, product_name: "Sok", started_at: "2026-11-03T10:00:00Z", status: "rejected", consumed_qty: "10.125" },
] };
let container: HTMLDivElement;
let root: Root;
beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listTraceMaterials).mockReset().mockResolvedValue([{ id: 20, name: "Koncentrat", type: "ingredient", unit: "kg" }, { id: 21, name: "Plastenka", type: "packaging", unit: "kos" }]);
  vi.mocked(findTraceLots).mockReset().mockResolvedValue([lot]);
  vi.mocked(traceLot).mockReset().mockResolvedValue(result);
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<LotTraceability />));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

function select(id: string, value: string) {
  act(() => {
    const control = container.querySelector<HTMLSelectElement>(`#${id}`)!;
    control.value = value; control.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
function code(value: string) {
  act(() => {
    const control = container.querySelector<HTMLInputElement>("#trace-lot-code")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(control, value);
    control.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function fill() { select("trace-material", "20"); code("  SER-1  "); }
async function search() {
  await act(async () => { container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}
function button(text: string) { return Array.from(container.querySelectorAll("button")).find(item => item.textContent === text)!; }

it("naloži materiale in embalažo brez samodejnega iskanja serije", () => {
  expect(listTraceMaterials).toHaveBeenCalledWith(expect.any(AbortSignal));
  expect(container.querySelector("#trace-material")?.textContent).toContain("Plastenka (kos)");
  expect(findTraceLots).not.toHaveBeenCalled();
});

it("poišče serijo in prikaže vse povezane šarže v vrstnem redu API", async () => {
  fill(); await search();
  expect(findTraceLots).toHaveBeenCalledWith({ material_id: 20, supplier_lot_no: "SER-1" }, expect.any(AbortSignal));
  expect(traceLot).toHaveBeenCalledWith(30, expect.any(AbortSignal));
  const rows = container.querySelectorAll('table[aria-label="Sledljivost serije do šarž"] tbody tr');
  expect(rows).toHaveLength(2);
  expect(rows[0].textContent).toContain("STAREJŠA"); expect(rows[0].textContent).toContain("Sproščena");
  expect(rows[1].textContent).toContain("NOVEJŠA"); expect(rows[1].textContent).toContain("Zavrnjena");
  expect(rows[1].textContent).toContain("10,125 kg");
  expect(container.textContent).toContain("Skupna poraba: 40,125 kg");
  expect(container.textContent).toContain("Dobavitelj: Dobavitelj A");
  expect(document.activeElement).toBe(container.querySelector("#lot-trace-title"));
});

it("več dobaviteljev zahteva izrecno izbiro konkretne serije", async () => {
  const other = { ...lot, id: 31, supplier_id: 2, supplier_name: "Dobavitelj B" };
  vi.mocked(findTraceLots).mockResolvedValue([lot, other]);
  vi.mocked(traceLot).mockResolvedValue({ ...result, ...other });
  fill(); await search();
  expect(traceLot).not.toHaveBeenCalled();
  expect(container.textContent).toContain("Ista številka pripada več serijam.");
  await act(async () => select("trace-lot-choice", "31"));
  expect(traceLot).toHaveBeenCalledWith(31, expect.any(AbortSignal));
  expect(container.textContent).toContain("Dobavitelj: Dobavitelj B");
});

it("za neporabljeno serijo prikaže predpisano sporočilo", async () => {
  vi.mocked(traceLot).mockResolvedValue({ ...result, batches: [], total_consumed_qty: "0.000" });
  fill(); await search();
  expect(container.textContent).toContain("Ta serija še ni bila uporabljena v nobeni šarži.");
  expect(container.querySelector("table")).toBeNull();
});

it("popolnoma porabljeno serijo prikaže s preostankom nič", async () => {
  vi.mocked(traceLot).mockResolvedValue({ ...result, remaining_qty: "0.000" });
  fill(); await search();
  expect(container.textContent).toContain("Preostalo: 0 kg");
  expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
});

it.each(["", "   ", "a".repeat(81)])("pred API zavrne neveljavno številko serije", async value => {
  select("trace-material", "20"); code(value); await search();
  expect(findTraceLots).not.toHaveBeenCalled();
  expect(container.querySelector("#trace-lot-code-error")).not.toBeNull();
});

it("zahteva izbor materiala", async () => {
  code("SER-1"); await search();
  expect(findTraceLots).not.toHaveBeenCalled();
  expect(container.querySelector("#trace-material-error")).not.toBeNull();
});

it("404 odstrani prejšnji rezultat in prikaže predpisano sporočilo", async () => {
  fill(); await search();
  code("MISSING");
  vi.mocked(findTraceLots).mockRejectedValueOnce(new TraceabilityApiError("Serija ni najdena.", 404));
  await search();
  expect(container.textContent).toContain("Serija ni najdena.");
  expect(container.querySelector("#lot-trace-title")).toBeNull();
});

it("napake API 422 prikaže ob poljih", async () => {
  vi.mocked(findTraceLots).mockRejectedValueOnce(new TraceabilityApiError("Preveri podatke.", 422, undefined, { material_id: "Napačen material.", supplier_lot_no: "Napačna serija." }));
  fill(); await search();
  expect(container.querySelector("#trace-material-error")?.textContent).toBe("Napačen material.");
  expect(container.querySelector("#trace-lot-code-error")?.textContent).toBe("Napačna serija.");
});

it("sprememba materiala odstrani rezultat in kandidate", async () => {
  fill(); await search(); select("trace-material", "21");
  expect(container.querySelector("#lot-trace-title")).toBeNull();
  expect(container.querySelector("#trace-lot-choice")).toBeNull();
});

it("pozno prispelo iskanje po spremembi številke ignorira", async () => {
  let resolve!: (items: TraceLot[]) => void;
  vi.mocked(findTraceLots).mockReturnValueOnce(new Promise<TraceLot[]>(done => { resolve = done; }));
  fill(); await search(); code("DRUGA");
  await act(async () => resolve([lot]));
  expect(traceLot).not.toHaveBeenCalled();
  expect(container.querySelector("#lot-trace-title")).toBeNull();
});

it("pri menjavi dobavitelja ignorira prepozno prispele podrobnosti", async () => {
  const other = { ...lot, id: 31, supplier_name: "Dobavitelj B" };
  vi.mocked(findTraceLots).mockResolvedValue([lot, other]);
  let resolve!: (item: LotResult) => void;
  vi.mocked(traceLot).mockReturnValueOnce(new Promise<LotResult>(done => { resolve = done; })).mockResolvedValueOnce({ ...result, ...other });
  fill(); await search();
  await act(async () => select("trace-lot-choice", "30"));
  await act(async () => select("trace-lot-choice", "31"));
  await act(async () => resolve(result));
  expect(container.textContent).toContain("Dobavitelj: Dobavitelj B");
  expect(container.textContent).not.toContain("Dobavitelj: Dobavitelj A");
});

it("po napaki branja podrobnosti omogoči ponovitev iskanja", async () => {
  vi.mocked(traceLot).mockRejectedValueOnce(new Error("Povezava ni uspela."));
  fill(); await search();
  expect(container.textContent).toContain("Povezava ni uspela.");
  await search();
  expect(container.querySelector("#lot-trace-title")).not.toBeNull();
});

it("ponovno osveži šifrant surovin", async () => {
  await act(async () => button("Osveži surovine").click());
  expect(listTraceMaterials).toHaveBeenCalledTimes(2);
});

it("po napaki šifranta omogoči ponovno nalaganje", async () => {
  vi.mocked(listTraceMaterials).mockRejectedValueOnce(new Error("Šifranta ni mogoče naložiti."));
  await act(async () => button("Osveži surovine").click());
  expect(container.textContent).toContain("Šifranta ni mogoče naložiti.");
  expect(button("Poišči serijo").disabled).toBe(true);
  await act(async () => button("Osveži surovine").click());
  expect(container.textContent).not.toContain("Šifranta ni mogoče naložiti.");
  expect(container.querySelector("#trace-material")?.textContent).toContain("Koncentrat");
});

it("prazen šifrant pojasni in onemogoči iskanje", async () => {
  vi.mocked(listTraceMaterials).mockResolvedValueOnce([]);
  await act(async () => button("Osveži surovine").click());
  expect(container.textContent).toContain("Ni surovin ali embalaže za izbor.");
  expect(button("Poišči serijo").disabled).toBe(true);
});

it("med nespremenjenim iskanjem prepreči podvojen zahtevek", async () => {
  let resolve!: (items: TraceLot[]) => void;
  vi.mocked(findTraceLots).mockReturnValueOnce(new Promise<TraceLot[]>(done => { resolve = done; }));
  fill(); await search(); await search();
  expect(findTraceLots).toHaveBeenCalledOnce();
  await act(async () => resolve([lot]));
});
