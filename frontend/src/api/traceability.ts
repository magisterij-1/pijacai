// — iskanje šarž, materialov in dobaviteljevih serij.
import { authenticatedRequest } from "./auth";
import type { Batch } from "./batches";
import type { Material } from "./inventory";

export type MaterialConsumptionTotal = { material_id: number; material_name: string; unit: string; consumed_qty: string };
export type BatchTraceability = Batch & { totals: MaterialConsumptionTotal[] };
export type TraceLot = {
  id: number; material_id: number; material_name: string; unit: string; supplier_id: number; supplier_name: string;
  supplier_lot_no: string; received_qty: string; remaining_qty: string; received_at: string;
};
export type LotBatchConsumption = {
  batch_id: number; batch_code: string; product_id: number; product_name: string;
  started_at: string; status: Batch["status"]; consumed_qty: string;
};
export type LotTraceability = TraceLot & { batches: LotBatchConsumption[]; total_consumed_qty: string };
export type LotSearch = { material_id: number; supplier_lot_no: string };
export type LotSearchFields = Partial<Record<keyof LotSearch, string>>;

export class TraceabilityApiError extends Error {
  constructor(message: string, public status?: number, public codeError?: string, public fields: LotSearchFields = {}) { super(message); }
}

export async function traceBatchByCode(code: string, signal?: AbortSignal): Promise<BatchTraceability> {
  const query = new URLSearchParams({ batch_code: code });
  return read(`/traceability/batch?${query}`, "batch", signal);
}

async function read<T>(path: string, kind: "batch" | "lot" | "materials", signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedRequest(path, { signal, cache: "no-store" });
  } catch (error) {
    if (error instanceof TypeError) throw new TraceabilityApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 404 && kind !== "materials") throw new TraceabilityApiError(kind === "batch" ? "Šarža ni najdena." : "Serija ni najdena.", 404);
    if (response.status === 422 && kind === "batch") throw new TraceabilityApiError("Preveri kodo šarže.", 422, "Vnesi kodo šarže z največ 80 znaki.");
    if (response.status === 422 && kind === "lot") {
      const fields: LotSearchFields = {};
      for (const item of Array.isArray(body?.detail) ? body.detail : []) {
        const field: unknown = item.loc?.[item.loc.length - 1];
        if (field === "material_id" || field === "supplier_lot_no") fields[field] = "Preveri vneseno vrednost.";
      }
      throw new TraceabilityApiError("Preveri podatke serije.", 422, undefined, fields);
    }
    throw new TraceabilityApiError(typeof body?.detail === "string" ? body.detail : "Sledljivosti ni mogoče naložiti.", response.status);
  }
  if (body === null) throw new TraceabilityApiError("Neveljaven odgovor strežnika.");
  return body as T;
}

export function listTraceMaterials(signal?: AbortSignal): Promise<Material[]> {
  return read("/traceability/materials", "materials", signal);
}
export function findTraceLots(input: LotSearch, signal?: AbortSignal): Promise<TraceLot[]> {
  const query = new URLSearchParams({ material_id: String(input.material_id), supplier_lot_no: input.supplier_lot_no });
  return read(`/traceability/lots?${query}`, "lot", signal);
}
export function traceLot(lotId: number, signal?: AbortSignal): Promise<LotTraceability> {
  return read(`/traceability/lot/${lotId}`, "lot", signal);
}
