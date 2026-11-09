// — prejemi, šifranti in pregled zalog.
import { authenticatedRequest } from "./auth";

export type Material = { id: number; name: string; type: "ingredient" | "packaging"; unit: string };
export type Supplier = { id: number; name: string };
export type ReceiptCreate = {
  material_id: number; supplier_id: number; supplier_lot_no: string;
  received_qty: string; unit_cost: string;
};
export type MaterialLot = ReceiptCreate & {
  id: number; remaining_qty: string; received_at: string; received_by: number;
};
export type ReceiptFields = Partial<Record<keyof ReceiptCreate, string>>;
export type StockLot = MaterialLot & {
  material_name: string; material_type: Material["type"]; unit: string; supplier_name: string;
};
export type StockTotal = { material_id: number; material_name: string; unit: string; remaining_qty: string };
export type Stock = { lots: StockLot[]; totals: StockTotal[] };
export type StockOptions = { material_id?: number; include_consumed?: boolean };

export class InventoryApiError extends Error {
  constructor(message: string, public fields: ReceiptFields = {}) { super(message); }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedRequest(path, options);
  } catch (error) {
    if (error instanceof TypeError) throw new InventoryApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 409) {
      throw new InventoryApiError("Ta serija je že vnesena.", { supplier_lot_no: "Ta serija je že vnesena." });
    }
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const fields: ReceiptFields = {};
      for (const item of body.detail) {
        const field = item.loc?.[item.loc.length - 1];
        if (["material_id", "supplier_id", "supplier_lot_no", "received_qty", "unit_cost"].includes(field)) {
          fields[field as keyof ReceiptCreate] = "Preveri vneseno vrednost.";
        }
      }
      throw new InventoryApiError("Preveri podatke prejema.", fields);
    }
    throw new InventoryApiError(typeof body?.detail === "string" ? body.detail : "Zahtevek ni uspel. Poskusi znova.");
  }
  if (body === null) throw new InventoryApiError("Neveljaven odgovor strežnika.");
  return body as T;
}

export function listMaterials(signal?: AbortSignal): Promise<Material[]> {
  return request("/lookup/materials", { signal, cache: "no-store" });
}
export function listSuppliers(signal?: AbortSignal): Promise<Supplier[]> {
  return request("/lookup/suppliers", { signal, cache: "no-store" });
}
export function listMaterialLots(signal?: AbortSignal): Promise<MaterialLot[]> {
  return request("/material-lots", { signal, cache: "no-store" });
}
export function receiveMaterial(data: ReceiptCreate): Promise<MaterialLot> {
  return request("/material-lots", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
}

export function getStock(options: StockOptions = {}, signal?: AbortSignal): Promise<Stock> {
  const params = new URLSearchParams();
  if (options.material_id !== undefined) params.set("material_id", String(options.material_id));
  params.set("include_consumed", String(options.include_consumed ?? false));
  return request(`/stock?${params}`, { signal, cache: "no-store" });
}
