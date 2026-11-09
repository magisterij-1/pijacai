// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { traceBatchByCode, TraceabilityApiError } from "../src/api/traceability";
import type { BatchTraceability } from "../src/api/traceability";
import { Traceability } from "../src/pages/Traceability";

vi.mock("../src/api/traceability", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/traceability")>();
  return { ...actual, traceBatchByCode: vi.fn() };
});

const result: BatchTraceability = {
  id: 6, batch_code: "2026-11-09-L1-01", order_id: 1, product_id: 2, product_name: "Jabolčni sok", product_unit: "kos",
  recipe_id: 3, recipe_version: 2, line_id: 1, line_name: "Linija 1", operator_id: 7,
  status: "in_production", planned_qty: "100", produced_qty: 0, rejected_qty: 0,
  started_at: "2026-11-09T10:00:00Z", finished_at: null, decided_by: null, decided_at: null, decision_note: null,
  consumptions: [
    { material_lot_id: 30, material_id: 20, material_name: "Koncentrat", supplier_name: "Dobavitelj A", supplier_lot_no: "STARA", qty: "7.125", unit: "kg" },
    { material_lot_id: 31, material_id: 20, material_name: "Koncentrat", supplier_name: "Dobavitelj B", supplier_lot_no: "NOVA", qty: "0.875", unit: "kg" },
    { material_lot_id: 32, material_id: 21, material_name: "Plastenka", supplier_name: "Dobavitelj C", supplier_lot_no: "EMB", qty: "100", unit: "kos" },
  ],
  totals: [
    { material_id: 20, material_name: "Koncentrat", unit: "kg", consumed_qty: "8.000" },
    { material_id: 21, material_name: "Plastenka", unit: "kos", consumed_qty: "100.000" },
  ],
};
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(traceBatchByCode).mockReset().mockResolvedValue(result);
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<Traceability />));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

function code(value: string) {
  act(() => {
    const input = container.querySelector<HTMLInputElement>("#trace-batch-code")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function search() {
  await act(async () => { container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

it("pred iskanjem ne pošilja zahtevka", () => {
  expect(traceBatchByCode).not.toHaveBeenCalled();
  expect(container.querySelector("#trace-result-title")).toBeNull();
});

it("poišče obrezano kodo in vsako porabljeno serijo prikaže ločeno", async () => {
  code(`  ${result.batch_code}  `); await search();
  expect(traceBatchByCode).toHaveBeenCalledWith(result.batch_code, expect.any(AbortSignal));
  expect(container.textContent).toContain("Izdelek: Jabolčni sok");
  expect(container.textContent).toContain("Stanje: V proizvodnji");
  const rows = container.querySelectorAll('table[aria-label="Sledljivost šarže do uporabljenih serij"] tbody tr');
  expect(rows).toHaveLength(3);
  expect(rows[0].textContent).toContain("Dobavitelj A"); expect(rows[0].textContent).toContain("STARA");
  expect(rows[0].textContent).toContain("7,125 kg"); expect(rows[1].textContent).toContain("0,875 kg");
  expect(container.querySelector(".stock-totals")?.textContent).toContain("8 kg");
  expect(container.querySelector(".stock-totals")?.textContent).toContain("100 kos");
  expect(document.activeElement).toBe(container.querySelector("#trace-result-title"));
});

it.each([["awaiting_qc", "Čaka na kontrolo"], ["released", "Sproščena"], ["rejected", "Zavrnjena"]] as const)("prikaže stanje %s", async (status, label) => {
  vi.mocked(traceBatchByCode).mockResolvedValue({ ...result, status });
  code(result.batch_code); await search();
  expect(container.textContent).toContain(`Stanje: ${label}`);
});

it("prikaže odločitev in razlog zavrnitve kot besedilo", async () => {
  vi.mocked(traceBatchByCode).mockResolvedValue({ ...result, status: "rejected", decided_by: 8,
    decided_at: "2026-11-09T11:00:00Z", decision_note: "Neustrezna vrednost pH." });
  code(result.batch_code); await search();
  expect(container.textContent).toContain("Odločil kontrolor #8");
  expect(container.textContent).toContain("Razlog zavrnitve: Neustrezna vrednost pH.");
});

it.each(["", "   ", "a".repeat(81)])("pred API zavrne neveljavno kodo", async value => {
  code(value); await search();
  expect(traceBatchByCode).not.toHaveBeenCalled();
  expect(container.querySelector("#trace-code-error")).not.toBeNull();
});

it("pri neobstoječi šarži prikaže predpisano sporočilo brez starih rezultatov", async () => {
  code(result.batch_code); await search();
  vi.mocked(traceBatchByCode).mockRejectedValueOnce(new TraceabilityApiError("Šarža ni najdena.", 404));
  code("NEOBSTAJA"); await search();
  expect(container.textContent).toContain("Šarža ni najdena.");
  expect(container.querySelector("#trace-result-title")).toBeNull();
});

it("napako API 422 prikaže ob kodi", async () => {
  vi.mocked(traceBatchByCode).mockRejectedValueOnce(new TraceabilityApiError("Preveri kodo.", 422, "Napačna koda."));
  code("KODA"); await search();
  expect(container.querySelector("#trace-code-error")?.textContent).toBe("Napačna koda.");
});

it("prazno zgodovinsko porabo pojasni brez izmišljanja vrstic ali vsot", async () => {
  vi.mocked(traceBatchByCode).mockResolvedValue({ ...result, consumptions: [], totals: [] });
  code(result.batch_code); await search();
  expect(container.textContent).toContain("Za to šaržo ni zapisane porabe surovin.");
  expect(container.querySelector("table")).toBeNull();
  expect(container.querySelector(".stock-totals")).toBeNull();
});

it("sprememba kode odstrani prejšnji rezultat", async () => {
  code(result.batch_code); await search(); code("DRUGA");
  expect(container.querySelector("#trace-result-title")).toBeNull();
});

it("ignorira pozen rezultat po spremembi kode in novem iskanju", async () => {
  let resolve!: (result: BatchTraceability) => void;
  vi.mocked(traceBatchByCode).mockReturnValueOnce(new Promise<BatchTraceability>(done => { resolve = done; }));
  code(result.batch_code); await search();
  const signal = vi.mocked(traceBatchByCode).mock.calls[0][1]!;
  code("DRUGA");
  expect(signal.aborted).toBe(true);
  vi.mocked(traceBatchByCode).mockResolvedValueOnce({ ...result, batch_code: "DRUGA" });
  await search(); await act(async () => resolve(result));
  expect(container.querySelector("#trace-result-title")?.textContent).toBe("Šarža DRUGA");
});

it("med nespremenjenim iskanjem prepreči ponoven zahtevek", async () => {
  let resolve!: (result: BatchTraceability) => void;
  vi.mocked(traceBatchByCode).mockReturnValueOnce(new Promise<BatchTraceability>(done => { resolve = done; }));
  code(result.batch_code); await search(); await search();
  expect(traceBatchByCode).toHaveBeenCalledOnce();
  expect(container.querySelector("button")!.disabled).toBe(true);
  await act(async () => resolve(result));
});

it("po omrežni napaki omogoči ponovno iskanje", async () => {
  vi.mocked(traceBatchByCode).mockRejectedValueOnce(new Error("Povezava s strežnikom ni uspela."));
  code(result.batch_code); await search();
  expect(container.textContent).toContain("Povezava s strežnikom ni uspela.");
  await search();
  expect(container.querySelector("#trace-result-title")).not.toBeNull();
  expect(container.textContent).not.toContain("Povezava s strežnikom ni uspela.");
});
