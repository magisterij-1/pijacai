// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Batch } from "../src/api/batches";
import { getQuality, QualityApiError, rejectBatch, releaseBatch, saveQualityCheck } from "../src/api/quality";
import type { QualityCheck, QualityOverview } from "../src/api/quality";
import { QualityMeasurements } from "../src/pages/QualityMeasurements";

vi.mock("../src/api/quality", async importOriginal => {
  const actual = await importOriginal<typeof import("../src/api/quality")>();
  return { ...actual, getQuality: vi.fn(), saveQualityCheck: vi.fn(), releaseBatch: vi.fn(), rejectBatch: vi.fn() };
});

const overview: QualityOverview = {
  batch_id: 6, checks: [], parameters: [
    { id: 10, product_id: 2, name: "pH", unit: "pH", min_value: "2.800", max_value: "4.000", latest_check: null },
    { id: 11, product_id: 2, name: "CO₂", unit: "g/L", min_value: "0.000", max_value: "1.000", latest_check: null },
  ],
};
const check: QualityCheck = { id: 20, batch_id: 6, parameter_id: 10, value: "3.125", passed: true, checked_by: 8, checked_at: "2026-11-09T10:00:00Z" };
let container: HTMLDivElement;
let root: Root;
let onSaving: ReturnType<typeof vi.fn>;
let onConflict: ReturnType<typeof vi.fn>;
let onReleased: ReturnType<typeof vi.fn>;
let onRejected: ReturnType<typeof vi.fn>;
const ready: QualityOverview = {
  ...overview, parameters: overview.parameters.map(item => ({ ...item, latest_check: { ...check, parameter_id: item.id, passed: true } })),
};
const released: Batch = {
  id: 6, batch_code: "QC-6", order_id: 1, product_id: 2, product_name: "Sok", product_unit: "kos",
  recipe_id: 3, recipe_version: 1, line_id: 10, line_name: "Linija 1", operator_id: 7,
  status: "released", planned_qty: "500.000", produced_qty: 480, rejected_qty: 5,
  started_at: "2026-11-09T09:00:00Z", finished_at: "2026-11-09T10:00:00Z", consumptions: [],
  decided_by: 8, decided_at: "2026-11-09T11:00:00Z", decision_note: null,
};

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(getQuality).mockReset().mockResolvedValue(overview);
  vi.mocked(saveQualityCheck).mockReset().mockResolvedValue(check);
  vi.mocked(releaseBatch).mockReset().mockResolvedValue(released);
  vi.mocked(rejectBatch).mockReset().mockResolvedValue({ ...released, status: "rejected", decision_note: "Neustrezna vrednost pH." });
  onSaving = vi.fn(); onConflict = vi.fn();
  onReleased = vi.fn();
  onRejected = vi.fn();
  container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function render(id = 6, status: Batch["status"] = "awaiting_qc") {
  await act(async () => root.render(<QualityMeasurements batch={{ id, status }} onSaving={onSaving} onConflict={onConflict} onReleased={onReleased} onRejected={onRejected} />));
}
function button(text: string) { return Array.from(container.querySelectorAll("button")).find(item => item.textContent === text)!; }
function select(value = "10") {
  act(() => {
    const control = container.querySelector<HTMLSelectElement>("#quality-parameter")!;
    control.value = value; control.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
function value(value: string) {
  act(() => {
    const control = container.querySelector<HTMLInputElement>("#quality-value")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(control, value);
    control.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function submit() {
  await act(async () => { container.querySelector("#quality-measurement-form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

it("prikaže vse parametre, enote, meje in manjkajoče meritve", async () => {
  await render();
  expect(getQuality).toHaveBeenCalledWith(6, expect.any(AbortSignal));
  const table = container.querySelector('table[aria-label="Zahtevani parametri kakovosti"]')!;
  expect(table.textContent).toContain("pH"); expect(table.textContent).toContain("CO₂");
  expect(table.textContent).toContain("g/L"); expect(table.textContent).toContain("2,8–4");
  expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
  expect(table.textContent?.match(/Manjka meritev/g)).toHaveLength(2);
});

it.each([["2,800", "ustreza"], ["4.000", "ustreza"], ["2.799", "ne ustreza"], ["4.001", "ne ustreza"]])("v predogledu pravilno primerja %s", async (input, result) => {
  await render(); select(); value(input);
  expect(container.textContent).toContain(`Predogled: ${result}. Meritev še ni shranjena.`);
  expect(saveQualityCheck).not.toHaveBeenCalled();
});

it("shrani decimalno vejico kot niz, osveži zadnjo meritev in pokaže zgodovino", async () => {
  await render(); select(); value("3,125");
  vi.mocked(getQuality).mockResolvedValue({ ...overview, checks: [check], parameters: [{ ...overview.parameters[0], latest_check: check }, overview.parameters[1]] });
  await submit();
  expect(saveQualityCheck).toHaveBeenCalledWith(6, { parameter_id: 10, value: "3.125" });
  expect(getQuality).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain("Meritev pH je shranjena: ustreza.");
  expect(container.querySelector('table[aria-label="Zahtevani parametri kakovosti"]')?.textContent).toContain("3,125");
  expect(container.querySelector('table[aria-label="Zgodovina meritev kakovosti"] tbody tr')?.textContent).toContain("#8");
  expect(container.querySelector<HTMLInputElement>("#quality-value")!.value).toBe("");
});

it.each(["", "abc", "NaN", "Infinity", "3.0001", "1000000000", "1e2"])("pred API zavrne vrednost %s", async input => {
  await render(); select(); value(input); await submit();
  expect(saveQualityCheck).not.toHaveBeenCalled();
  expect(container.querySelector("#quality-value-error")).not.toBeNull();
});

it("zahteva izbiro parametra", async () => {
  await render(); value("3"); await submit();
  expect(saveQualityCheck).not.toHaveBeenCalled();
  expect(container.querySelector("#quality-parameter-error")).not.toBeNull();
});

it.each(["0", "-0.001"])("dovoli numerično vrednost %s in pri rezultatu upošteva strežnik", async input => {
  vi.mocked(saveQualityCheck).mockResolvedValue({ ...check, parameter_id: 11, value: input, passed: false });
  await render(); select("11"); value(input); await submit();
  expect(saveQualityCheck).toHaveBeenCalledWith(6, { parameter_id: 11, value: input });
  expect(container.textContent).toContain("Meritev CO₂ je shranjena: ne ustreza.");
});

it("menjava parametra počisti vrednost in predogled", async () => {
  await render(); select(); value("3"); select("11");
  expect(container.querySelector<HTMLInputElement>("#quality-value")!.value).toBe("");
  expect(container.textContent).not.toContain("Predogled:");
});

it("prikaže neuspešno zadnjo meritev, čeprav je prejšnja ustrezala", async () => {
  const last = { ...check, id: 21, value: "5.000", passed: false };
  vi.mocked(getQuality).mockResolvedValue({ ...overview, checks: [last, check], parameters: [{ ...overview.parameters[0], latest_check: last }] });
  await render();
  const row = container.querySelector('table[aria-label="Zahtevani parametri kakovosti"] tbody tr')!;
  expect(row.textContent).toContain("5"); expect(row.textContent).toContain("Ne ustreza");
  expect(container.querySelectorAll('table[aria-label="Zgodovina meritev kakovosti"] tbody tr')).toHaveLength(2);
});

it("ohrani vnos in prikaže napake 422 ob poljih", async () => {
  vi.mocked(saveQualityCheck).mockRejectedValueOnce(new QualityApiError("Preveri podatke meritve.", { value: "Neveljavna vrednost.", parameter_id: "Napačen parameter." }, 422));
  await render(); select(); value("3"); await submit();
  expect(container.querySelector("#quality-value-error")?.textContent).toBe("Neveljavna vrednost.");
  expect(container.querySelector("#quality-parameter-error")?.textContent).toBe("Napačen parameter.");
  expect(container.querySelector<HTMLInputElement>("#quality-value")!.value).toBe("3");
});

it.each([403, 404, 409])("ob napaki %s zahteva osvežitev stanja šarže", async status => {
  vi.mocked(saveQualityCheck).mockRejectedValueOnce(new QualityApiError("Meritev ni dovoljena.", {}, status));
  await render(); select(); value("3"); await submit();
  expect(onConflict).toHaveBeenCalledWith("Meritev ni dovoljena.");
});

it("med shranjevanjem blokira dvojni zahtevek in osvežitev", async () => {
  let resolve!: (check: QualityCheck) => void;
  vi.mocked(saveQualityCheck).mockReturnValueOnce(new Promise<QualityCheck>(done => { resolve = done; }));
  await render(); select(); value("3"); await submit(); await submit();
  expect(saveQualityCheck).toHaveBeenCalledOnce();
  expect(container.querySelector("fieldset")!.disabled).toBe(true);
  expect(button("Osveži meritve").disabled).toBe(true);
  expect(onSaving).toHaveBeenCalledWith(true);
  await act(async () => resolve(check));
  expect(onSaving).toHaveBeenLastCalledWith(false);
});

it("napaka osvežitve po uspešnem shranjevanju ohrani potrditev", async () => {
  await render(); select(); value("3");
  vi.mocked(getQuality).mockRejectedValueOnce(new Error("Osvežitev ni uspela."));
  await submit();
  expect(container.textContent).toContain("Meritev pH je shranjena: ustreza.");
  expect(container.textContent).toContain("Osvežitev ni uspela.");
  expect(container.querySelector("#quality-measurement-form")).toBeNull();
  await act(async () => button("Osveži meritve").click());
  expect(container.querySelector("#quality-measurement-form")).not.toBeNull();
  expect(saveQualityCheck).toHaveBeenCalledOnce();
});

it("ignorira pozno prispelo branje druge šarže", async () => {
  let resolve!: (overview: QualityOverview) => void;
  vi.mocked(getQuality).mockReturnValueOnce(new Promise<QualityOverview>(done => { resolve = done; }));
  await render(6);
  vi.mocked(getQuality).mockResolvedValue({ batch_id: 9, checks: [], parameters: [] });
  await render(9);
  await act(async () => resolve(overview));
  expect(container.textContent).toContain("Za izdelek ni določenih parametrov kakovosti.");
  expect(container.querySelector("#quality-measurement-form")).toBeNull();
  expect(container.querySelector("#quality-reject-form")).not.toBeNull();
});

it.each(["in_production", "released", "rejected"] as const)("stanje %s omogoča le pregled", async status => {
  await render(6, status);
  expect(container.querySelector("form")).toBeNull();
  expect(container.textContent).toContain("Meritve je mogoče vnašati samo za šaržo, ki čaka na kontrolo.");
});

it("blokira sprostitev ob manjkajočih meritvah", async () => {
  await render();
  expect(button("Sprosti šaržo").disabled).toBe(true);
  expect(container.textContent).toContain("Manjkajoče meritve: pH, CO₂.");
  await act(async () => button("Sprosti šaržo").click());
  expect(releaseBatch).not.toHaveBeenCalled();
});

it("blokira sprostitev, ko zadnja meritev ne ustreza, čeprav zgodovina vsebuje ustrezno", async () => {
  vi.mocked(getQuality).mockResolvedValue({ ...ready, checks: [check], parameters: [
    { ...ready.parameters[0], latest_check: { ...check, id: 21, passed: false, value: "5" } }, ready.parameters[1],
  ] });
  await render();
  expect(button("Sprosti šaržo").disabled).toBe(true);
  expect(container.textContent).toContain("Neustrezne meritve: pH.");
});

it("prazen šifrant ne omogoči sprostitve", async () => {
  vi.mocked(getQuality).mockResolvedValue({ batch_id: 6, parameters: [], checks: [] });
  await render();
  expect(button("Sprosti šaržo").disabled).toBe(true);
});

it("sprosti šaržo z vsemi ustreznimi shranjenimi meritvami", async () => {
  vi.mocked(getQuality).mockResolvedValue(ready);
  await render();
  expect(button("Sprosti šaržo").disabled).toBe(false);
  await act(async () => button("Sprosti šaržo").click());
  expect(releaseBatch).toHaveBeenCalledWith(6);
  expect(onReleased).toHaveBeenCalledWith(released);
  expect(onSaving).toHaveBeenLastCalledWith(false);
});

it("sprostitev omogoči šele po uspešnem shranjevanju in osvežitvi zadnje meritve", async () => {
  vi.mocked(getQuality).mockResolvedValueOnce({ ...ready, parameters: [ready.parameters[0], overview.parameters[1]] }).mockResolvedValue(ready);
  await render();
  expect(button("Sprosti šaržo").disabled).toBe(true);
  select("11"); value("0.5"); await submit();
  expect(button("Sprosti šaržo").disabled).toBe(false);
  expect(releaseBatch).not.toHaveBeenCalled();
});

it("422 prikaže sezname API in ponovno prebere meritve", async () => {
  vi.mocked(getQuality).mockResolvedValueOnce(ready).mockResolvedValue(overview);
  vi.mocked(releaseBatch).mockRejectedValueOnce(new QualityApiError("Pogoji za sprostitev niso izpolnjeni.", {}, 422, {
    code: "QUALITY_NOT_PASSED", missing: [{ parameter_id: 11, name: "CO₂" }], invalid: [{ parameter_id: 10, name: "pH" }],
  }));
  await render(); await act(async () => button("Sprosti šaržo").click());
  expect(container.textContent).toContain("Pogoji za sprostitev niso izpolnjeni.");
  expect(container.textContent).toContain("Manjkajoči parametri ob sprostitvi:");
  expect(container.textContent).toContain("Neustrezni parametri ob sprostitvi:");
  expect(container.querySelectorAll('div[role="alert"] li')).toHaveLength(2);
  expect(getQuality).toHaveBeenCalledTimes(2);
  expect(button("Sprosti šaržo").disabled).toBe(true);
  expect(onReleased).not.toHaveBeenCalled();
});

it.each([403, 404, 409])("pri napaki sprostitve %s zahteva osvežitev stanja šarže", async status => {
  vi.mocked(getQuality).mockResolvedValue(ready);
  vi.mocked(releaseBatch).mockRejectedValueOnce(new QualityApiError("Sprostitev ni dovoljena.", {}, status));
  await render(); await act(async () => button("Sprosti šaržo").click());
  expect(onConflict).toHaveBeenCalledWith("Sprostitev ni dovoljena.");
  expect(onReleased).not.toHaveBeenCalled();
});

it("med sproščanjem prepreči dvojni zahtevek in vnos meritve", async () => {
  let resolve!: (batch: Batch) => void;
  vi.mocked(getQuality).mockResolvedValue(ready);
  vi.mocked(releaseBatch).mockReturnValueOnce(new Promise<Batch>(done => { resolve = done; }));
  await render(); select(); value("3");
  await act(async () => button("Sprosti šaržo").click());
  expect(button("Sproščanje …").disabled).toBe(true);
  expect(button("Osveži meritve").disabled).toBe(true);
  await submit();
  await act(async () => button("Sproščanje …").click());
  expect(releaseBatch).toHaveBeenCalledOnce();
  expect(saveQualityCheck).not.toHaveBeenCalled();
  await act(async () => resolve(released));
});

it("med shranjevanjem meritve je sprostitev onemogočena", async () => {
  let resolve!: (check: QualityCheck) => void;
  vi.mocked(getQuality).mockResolvedValue(ready);
  vi.mocked(saveQualityCheck).mockReturnValueOnce(new Promise<QualityCheck>(done => { resolve = done; }));
  await render(); select(); value("3"); await submit();
  expect(button("Sprosti šaržo").disabled).toBe(true);
  await act(async () => button("Sprosti šaržo").click());
  expect(releaseBatch).not.toHaveBeenCalled();
  await act(async () => resolve(check));
});

it("sproščena šarža ob ponovnem prikazu nima gumba ali obrazca meritve", async () => {
  vi.mocked(getQuality).mockResolvedValue(ready);
  await render(6, "released");
  expect(container.querySelector("form")).toBeNull();
  expect(button("Sprosti šaržo")).toBeUndefined();
});

function reason(text: string) {
  act(() => {
    const control = container.querySelector<HTMLTextAreaElement>("#quality-reason")!;
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(control, text);
    control.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function reject() {
  await act(async () => { container.querySelector("#quality-reject-form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

it.each(["", "   ", "kratko", "123456789", "a".repeat(501)])("zavrne neveljaven razlog dolžine %s", async text => {
  await render(); reason(text); await reject();
  expect(rejectBatch).not.toHaveBeenCalled();
  expect(container.querySelector("#quality-reason-error")?.textContent).toBe("Razlog mora vsebovati od 10 do 500 znakov.");
});

it.each(["1234567890", "ž".repeat(500), "😀".repeat(500)])("dovoli robno dolžino razloga", async text => {
  await render(); reason(text); await reject();
  expect(rejectBatch).toHaveBeenCalledWith(6, text);
  expect(onRejected).toHaveBeenCalledOnce();
});

it("zavrne brez meritev in obreže zunanje presledke razloga", async () => {
  await render(); reason("  Neustrezna vrednost pH. \n"); await reject();
  expect(rejectBatch).toHaveBeenCalledWith(6, "Neustrezna vrednost pH.");
  expect(onRejected).toHaveBeenCalledWith(expect.objectContaining({ status: "rejected", decision_note: "Neustrezna vrednost pH." }));
  expect(onSaving).toHaveBeenLastCalledWith(false);
});

it("dovoli zavrnitev tudi ob napaki nalaganja meritev", async () => {
  vi.mocked(getQuality).mockRejectedValueOnce(new Error("Meritev ni mogoče prebrati."));
  await render(); reason("Neustrezna embalaža izdelka."); await reject();
  expect(rejectBatch).toHaveBeenCalledWith(6, "Neustrezna embalaža izdelka.");
});

it("dovoli zavrnitev pri praznem šifrantu parametrov", async () => {
  vi.mocked(getQuality).mockResolvedValue({ batch_id: 6, parameters: [], checks: [] });
  await render(); reason("Neustrezna embalaža izdelka."); await reject();
  expect(rejectBatch).toHaveBeenCalledWith(6, "Neustrezna embalaža izdelka.");
});

it("ohrani razlog in prikaže napako API ob polju", async () => {
  vi.mocked(rejectBatch).mockRejectedValueOnce(new QualityApiError("Preveri vnesene podatke.", { decision_note: "Razlog ni veljaven." }, 422));
  await render(); reason("Neustrezna vrednost pH."); await reject();
  expect(container.querySelector("#quality-reason-error")?.textContent).toBe("Razlog ni veljaven.");
  expect(container.querySelector<HTMLTextAreaElement>("#quality-reason")!.value).toBe("Neustrezna vrednost pH.");
  expect(onRejected).not.toHaveBeenCalled();
});

it.each([403, 404, 409])("ob zavrnitvi %s osveži stanje prek nadrejene strani", async status => {
  vi.mocked(rejectBatch).mockRejectedValueOnce(new QualityApiError("Zavrnitev ni dovoljena.", {}, status));
  await render(); reason("Neustrezna vrednost pH."); await reject();
  expect(onConflict).toHaveBeenCalledWith("Zavrnitev ni dovoljena.");
  expect(onRejected).not.toHaveBeenCalled();
});

it("med zavračanjem prepreči dvojni zahtevek, meritev in sprostitev", async () => {
  let resolve!: (batch: Batch) => void;
  vi.mocked(getQuality).mockResolvedValue(ready);
  vi.mocked(rejectBatch).mockReturnValueOnce(new Promise<Batch>(done => { resolve = done; }));
  await render(); select(); value("3"); reason("Neustrezna vrednost pH."); await reject(); await reject();
  await submit(); await act(async () => button("Sprosti šaržo").click());
  expect(rejectBatch).toHaveBeenCalledOnce();
  expect(saveQualityCheck).not.toHaveBeenCalled(); expect(releaseBatch).not.toHaveBeenCalled();
  expect(container.querySelector<HTMLFieldSetElement>("#quality-reject-form fieldset")!.disabled).toBe(true);
  expect(button("Osveži meritve").disabled).toBe(true);
  await act(async () => resolve({ ...released, status: "rejected", decision_note: "Neustrezna vrednost pH." }));
});

it.each(["measurement", "release"])("med akcijo %s prepreči zavrnitev", async operation => {
  let resolve!: (value: QualityCheck & Batch) => void;
  const pending = new Promise<QualityCheck & Batch>(done => { resolve = done; });
  vi.mocked(getQuality).mockResolvedValue(ready);
  if (operation === "measurement") vi.mocked(saveQualityCheck).mockReturnValueOnce(pending);
  else vi.mocked(releaseBatch).mockReturnValueOnce(pending);
  await render(); select(); value("3"); reason("Neustrezna vrednost pH.");
  if (operation === "measurement") await submit();
  else await act(async () => button("Sprosti šaržo").click());
  await reject();
  expect(rejectBatch).not.toHaveBeenCalled();
  await act(async () => resolve({ ...released, ...check }));
});

it("zavrnjena šarža nima obrazcev ali gumba sprostitve", async () => {
  await render(6, "rejected");
  expect(container.querySelector("#quality-reject-form")).toBeNull();
  expect(container.querySelector("#quality-measurement-form")).toBeNull();
  expect(button("Sprosti šaržo")).toBeUndefined();
});
