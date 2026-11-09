import { authenticatedRequest } from "./auth";
import type { Batch } from "./batches";

export type QualityCheck = {
  id: number; batch_id: number; parameter_id: number; value: string;
  passed: boolean; checked_by: number; checked_at: string;
};
export type QualityParameter = {
  id: number; product_id: number; name: string; unit: string;
  min_value: string; max_value: string; latest_check: QualityCheck | null;
};
export type QualityOverview = { batch_id: number; parameters: QualityParameter[]; checks: QualityCheck[] };
export type QualityInput = { parameter_id: number; value: string };
export type QualityFields = Partial<Record<keyof QualityInput | "decision_note", string>>;
export type ParameterProblem = { parameter_id: number; name: string };
export type ReleaseProblems = {
  code: "QUALITY_NOT_PASSED" | "NO_QUALITY_PARAMETERS";
  missing: ParameterProblem[]; invalid: ParameterProblem[];
};

export class QualityApiError extends Error {
  constructor(message: string, public fields: QualityFields = {}, public status?: number, public problems: ReleaseProblems | null = null) { super(message); }
}

async function request<T>(path: string, options: RequestInit): Promise<T> {
  let response: Response;
  try { response = await authenticatedRequest(path, options); }
  catch (error) {
    if (error instanceof TypeError) throw new QualityApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 422 && (body?.detail?.code === "QUALITY_NOT_PASSED" || body?.detail?.code === "NO_QUALITY_PARAMETERS")) {
      throw new QualityApiError(body.detail.message, {}, 422, {
        code: body.detail.code,
        missing: Array.isArray(body.detail.missing) ? body.detail.missing : [],
        invalid: Array.isArray(body.detail.invalid) ? body.detail.invalid : [],
      });
    }
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const fields: QualityFields = {};
      for (const item of body.detail) {
        const field: unknown = item.loc?.[item.loc.length - 1];
        if (field === "parameter_id" || field === "value" || field === "decision_note") {
          fields[field] = item.type === "value_error" && typeof item.msg === "string" ? item.msg : "Preveri vneseno vrednost.";
        }
      }
      throw new QualityApiError("Preveri vnesene podatke.", fields, 422);
    }
    throw new QualityApiError(typeof body?.detail === "string" ? body.detail : "Podatkov kakovosti ni mogoče obdelati.", {}, response.status);
  }
  if (body === null) throw new QualityApiError("Neveljaven odgovor strežnika.");
  return body as T;
}

export function getQuality(batchId: number, signal?: AbortSignal): Promise<QualityOverview> {
  return request(`/batches/${batchId}/checks`, { signal, cache: "no-store" });
}
export function saveQualityCheck(batchId: number, data: QualityInput): Promise<QualityCheck> {
  return request(`/batches/${batchId}/checks`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
}
export function releaseBatch(batchId: number): Promise<Batch> {
  return request(`/batches/${batchId}/release`, { method: "POST" });
}
export function rejectBatch(batchId: number, decisionNote: string): Promise<Batch> {
  return request(`/batches/${batchId}/reject`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision_note: decisionNote }),
  });
}
