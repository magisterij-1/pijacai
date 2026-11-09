import { authenticatedRequest } from "./auth";
import type { Batch } from "./batches";

export type MaterialConsumptionTotal = { material_id: number; material_name: string; unit: string; consumed_qty: string };
export type BatchTraceability = Batch & { totals: MaterialConsumptionTotal[] };

export class TraceabilityApiError extends Error {
  constructor(message: string, public status?: number, public codeError?: string) { super(message); }
}

export async function traceBatchByCode(code: string, signal?: AbortSignal): Promise<BatchTraceability> {
  let response: Response;
  try {
    const query = new URLSearchParams({ batch_code: code });
    response = await authenticatedRequest(`/traceability/batch?${query}`, { signal, cache: "no-store" });
  } catch (error) {
    if (error instanceof TypeError) throw new TraceabilityApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 404) throw new TraceabilityApiError("Šarža ni najdena.", 404);
    if (response.status === 422) throw new TraceabilityApiError("Preveri kodo šarže.", 422, "Vnesi kodo šarže z največ 80 znaki.");
    throw new TraceabilityApiError(typeof body?.detail === "string" ? body.detail : "Sledljivosti ni mogoče naložiti.", response.status);
  }
  if (body === null) throw new TraceabilityApiError("Neveljaven odgovor strežnika.");
  return body as BatchTraceability;
}
