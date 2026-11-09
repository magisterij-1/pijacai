import { authenticatedRequest } from "./auth";

export type Line = { id: number; name: string };
export type BatchStartInput = { line_id: number; qty: string };
export type StockRequirement = {
  material_id: number; material_name: string; unit: string;
  required_qty: string; available_qty: string; missing_qty: string; status: "OK" | "PREMALO";
};
export type BatchPreview = {
  order_id: number; recipe_id: number; recipe_version: number; line_id: number;
  qty: string; can_start: boolean; requirements: StockRequirement[];
};
export type Consumption = { material_lot_id: number; material_id: number; material_name: string; supplier_name: string; supplier_lot_no: string; qty: string; unit: string };
export type Batch = {
  id: number; batch_code: string; order_id: number; product_id: number; product_name: string; product_unit: string;
  recipe_id: number; recipe_version: number; line_id: number; line_name: string; operator_id: number;
  status: "in_production" | "awaiting_qc" | "released" | "rejected";
  planned_qty: string; produced_qty: number; rejected_qty: number; started_at: string; finished_at: string | null;
  consumptions: Consumption[];
};
export type BatchSummary = Omit<Batch, "consumptions">;
export type BatchFinishInput = { produced_qty: number; rejected_qty: number };
export type BatchFields = Partial<Record<keyof BatchStartInput | keyof BatchFinishInput, string>>;

export class BatchApiError extends Error {
  constructor(message: string, public fields: BatchFields = {}, public status?: number, public missing: StockRequirement[] = []) { super(message); }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedRequest(path, options);
  } catch (error) {
    if (error instanceof TypeError) throw new BatchApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 409 && body?.detail?.code === "INSUFFICIENT_STOCK") {
      throw new BatchApiError(body.detail.message, {}, 409, Array.isArray(body.detail.missing) ? body.detail.missing : []);
    }
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const fields: BatchFields = {};
      for (const item of body.detail) {
        const field: unknown = item.loc?.[item.loc.length - 1];
        if (field === "line_id" || field === "qty" || field === "produced_qty" || field === "rejected_qty") {
          fields[field] = item.type === "value_error" && typeof item.msg === "string" ? item.msg : "Preveri vneseno vrednost.";
        }
      }
      throw new BatchApiError("Preveri podatke šarže.", fields, 422);
    }
    throw new BatchApiError(typeof body?.detail === "string" ? body.detail : "Zahtevek ni uspel. Poskusi znova.", {}, response.status);
  }
  if (body === null) throw new BatchApiError("Neveljaven odgovor strežnika.");
  return body as T;
}

export function listLines(signal?: AbortSignal): Promise<Line[]> {
  return request("/lookup/lines", { signal, cache: "no-store" });
}
export function previewBatch(orderId: number, data: BatchStartInput, signal?: AbortSignal): Promise<BatchPreview> {
  return request(`/orders/${orderId}/batches/preview`, { method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}
export function startBatch(orderId: number, data: BatchStartInput): Promise<Batch> {
  return request(`/orders/${orderId}/batches`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}

export function listBatches(status: Batch["status"], signal?: AbortSignal): Promise<BatchSummary[]> {
  return request(`/batches?status_filter=${status}`, { signal, cache: "no-store" });
}
export function getBatch(batchId: number, signal?: AbortSignal): Promise<Batch> {
  return request(`/batches/${batchId}`, { signal, cache: "no-store" });
}
export function finishBatch(batchId: number, data: BatchFinishInput): Promise<Batch> {
  return request(`/batches/${batchId}/finish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}
