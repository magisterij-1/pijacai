// — izdelki, predogled, shranjevanje in odpoved nalogov.
import { authenticatedRequest } from "./auth";

export type Product = { id: number; name: string; sku: string; unit: string };
export type Requirement = { material_id: number; material_name: string; material_type: "ingredient" | "packaging"; unit: string; required_qty: string };
export type OrderPreviewInput = { product_id: number; planned_qty: number };
export type OrderCreate = OrderPreviewInput & { planned_date: string; recipe_id: number };
export type OrderPreview = OrderPreviewInput & {
  product_name: string; product_unit: string; recipe_id: number; recipe_version: number;
  output_qty: string; requirements: Requirement[];
};
export type Order = OrderPreview & {
  id: number; planned_date: string; status: "planned" | "in_progress" | "done" | "cancelled"; created_by: number;
};
export type OrderFields = Partial<Record<keyof OrderCreate, string>>;

export class OrderApiError extends Error {
  constructor(message: string, public fields: OrderFields = {}, public status?: number) { super(message); }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await authenticatedRequest(path, options);
  } catch (error) {
    if (error instanceof TypeError) throw new OrderApiError("Povezava s strežnikom ni uspela.");
    throw error;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 422 && Array.isArray(body?.detail)) {
      const fields: OrderFields = {};
      for (const item of body.detail) {
        const field = item.loc?.[item.loc.length - 1];
        if (["product_id", "planned_qty", "planned_date", "recipe_id"].includes(field)) fields[field as keyof OrderCreate] = "Preveri vneseno vrednost.";
      }
      throw new OrderApiError("Preveri podatke naloga.", fields, 422);
    }
    throw new OrderApiError(typeof body?.detail === "string" ? body.detail : "Zahtevek ni uspel. Poskusi znova.", {}, response.status);
  }
  if (body === null) throw new OrderApiError("Neveljaven odgovor strežnika.");
  return body as T;
}

export function listProducts(signal?: AbortSignal): Promise<Product[]> {
  return request("/lookup/products", { signal, cache: "no-store" });
}
export function listOrders(signal?: AbortSignal): Promise<Order[]> {
  return request("/orders", { signal, cache: "no-store" });
}
export function previewOrder(data: OrderPreviewInput, signal?: AbortSignal): Promise<OrderPreview> {
  return request("/orders/preview", { method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}
export function createOrder(data: OrderCreate): Promise<Order> {
  return request("/orders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
}

export function cancelOrder(id: number): Promise<Order> {
  return request(`/orders/${id}/cancel`, { method: "POST" });
}
