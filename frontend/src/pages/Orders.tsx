import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Role } from "../api/auth";
import { createOrder, listOrders, listProducts, OrderApiError, previewOrder } from "../api/orders";
import type { Order, OrderFields, OrderPreview, Product, Requirement } from "../api/orders";
import { businessToday } from "../dates";
import { formatDecimal } from "../quantities";

const statusLabels: Record<Order["status"], string> = {
  planned: "Načrtovan", in_progress: "V teku", done: "Zaključen", cancelled: "Odpovedan",
};

function Requirements({ items }: { items: Requirement[] }) {
  return <div className="table-scroll"><table aria-label="Potrebne količine surovin">
    <thead><tr><th scope="col">Surovina ali embalaža</th><th scope="col">Potrebna količina</th></tr></thead>
    <tbody>{items.map(item => <tr key={item.material_id}><td>{item.material_name}</td><td>{formatDecimal(item.required_qty)} {item.unit}</td></tr>)}</tbody>
  </table></div>;
}

function NewOrder({ onCreated }: { onCreated: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [date, setDate] = useState(businessToday);
  const [loading, setLoading] = useState(true);
  const [productsError, setProductsError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [preview, setPreview] = useState<OrderPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fields, setFields] = useState<OrderFields>({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const previewRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setProductsError("");
    listProducts(controller.signal)
      .then(result => { if (!controller.signal.aborted) setProducts(result); })
      .catch(error => { if (!controller.signal.aborted) setProductsError(error instanceof Error ? error.message : "Izdelkov ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => () => previewRequest.current?.abort(), []);

  function invalidatePreview() {
    previewRequest.current?.abort();
    setPreview(null); setPreviewing(false); setMessage("");
  }

  function validate(withDate: boolean): boolean {
    const errors: OrderFields = {};
    if (!products.some(item => item.id === Number(productId))) errors.product_id = "Izberi izdelek z aktivno recepturo.";
    if (!/^\d+$/.test(quantity) || Number(quantity) <= 0 || Number(quantity) > 2147483647) errors.planned_qty = "Vnesi pozitivno celo količino, največ 2147483647.";
    if (withDate && (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < businessToday())) errors.planned_date = "Izberi današnji ali prihodnji datum.";
    setFields(errors);
    return Object.keys(errors).length === 0;
  }

  async function calculate() {
    if (saving || previewing || loading || !validate(false)) return;
    previewRequest.current?.abort();
    const controller = new AbortController();
    previewRequest.current = controller;
    setError(""); setMessage(""); setPreview(null); setPreviewing(true);
    try {
      const result = await previewOrder({ product_id: Number(productId), planned_qty: Number(quantity) }, controller.signal);
      if (!controller.signal.aborted) setPreview(result);
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof Error ? error.message : "Izračun ni uspel.");
        if (error instanceof OrderApiError) setFields(error.fields);
      }
    } finally {
      if (!controller.signal.aborted) setPreviewing(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || previewing || loading || !validate(true)) return;
    if (!preview || preview.product_id !== Number(productId) || preview.planned_qty !== Number(quantity)) {
      setError("Pred potrditvijo izračunaj potrebne količine.");
      return;
    }
    setSaving(true); setError(""); setMessage("");
    try {
      const created = await createOrder({ product_id: preview.product_id, planned_qty: preview.planned_qty, planned_date: date, recipe_id: preview.recipe_id });
      setMessage(`Proizvodni nalog #${created.id} je ustvarjen.`);
      setPreview(null); setQuantity("");
      onCreated();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Naloga ni mogoče ustvariti.");
      if (error instanceof OrderApiError) {
        setFields(error.fields);
        if (error.status === 409) setPreview(null);
      }
    } finally {
      setSaving(false);
    }
  }

  function fieldError(field: keyof OrderFields) {
    return fields[field] ? <small id={`order-${field}-error`} className="field-error" role="alert">{fields[field]}</small> : null;
  }

  return <section aria-labelledby="new-order-title">
    <div className="workspace-header"><h3 id="new-order-title">Nov proizvodni nalog</h3>
      <button className="secondary" disabled={loading || saving || previewing} onClick={() => { invalidatePreview(); setRefresh(value => value + 1); }}>Osveži izdelke</button>
    </div>
    {productsError && <p className="error" role="alert">{productsError}</p>}
    {loading && <p role="status">Nalaganje izdelkov …</p>}
    {!loading && !productsError && products.length === 0 && <p>Ni izdelkov z aktivno recepturo.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="success" role="status">{message}</p>}
    <form onSubmit={submit}>
      <fieldset disabled={loading || saving || !products.length}>
        <label htmlFor="order-product">Izdelek</label>
        <select id="order-product" value={productId} required aria-invalid={Boolean(fields.product_id)} aria-describedby={fields.product_id ? "order-product_id-error" : undefined}
          onChange={event => { setProductId(event.target.value); invalidatePreview(); }}>
          <option value="">Izberi …</option>{products.map(item => <option key={item.id} value={item.id}>{item.name} ({item.sku}, {item.unit})</option>)}
        </select>
        {fieldError("product_id")}
        <label htmlFor="order-quantity">Načrtovana količina</label>
        <input id="order-quantity" type="number" min="1" max="2147483647" step="1" required value={quantity}
          aria-invalid={Boolean(fields.planned_qty)} aria-describedby={fields.planned_qty ? "order-planned_qty-error" : undefined}
          onChange={event => { setQuantity(event.target.value); invalidatePreview(); }} />
        {fieldError("planned_qty")}
        <label htmlFor="order-date">Načrtovan datum</label>
        <input id="order-date" type="date" required min={businessToday()} value={date}
          aria-invalid={Boolean(fields.planned_date)} aria-describedby={fields.planned_date ? "order-planned_date-error" : undefined}
          onChange={event => setDate(event.target.value)} />
        {fieldError("planned_date")}
        <button type="button" disabled={previewing} onClick={() => void calculate()}>{previewing ? "Izračunavanje …" : "Izračunaj potrebne količine"}</button>
      </fieldset>
      {preview && <section aria-labelledby="order-preview-title">
        <h4 id="order-preview-title">Potrebne količine</h4>
        <p>{preview.product_name} · receptura v{preview.recipe_version} · {preview.planned_qty} {preview.product_unit}</p>
        <Requirements items={preview.requirements} />
      </section>}
      <button type="submit" disabled={!preview || previewing || saving || loading}>{saving ? "Ustvarjanje …" : "Potrdi nalog"}</button>
    </form>
  </section>;
}

export function Orders({ role }: { role: Role }) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setOrders([]);
    listOrders(controller.signal)
      .then(result => { if (!controller.signal.aborted) setOrders(result); })
      .catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Nalogov ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [role, refresh]);

  return <div className="users-content">
    {role === "planner" && <NewOrder onCreated={() => setRefresh(value => value + 1)} />}
    <section aria-labelledby="orders-list-title">
      <div className="workspace-header"><h3 id="orders-list-title">Seznam nalogov</h3>
        <button className="secondary" disabled={loading} onClick={() => setRefresh(value => value + 1)}>Osveži naloge</button>
      </div>
      {loading && <p role="status">Nalaganje nalogov …</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && (orders.length === 0 ? <p>Ni proizvodnih nalogov za prikaz.</p> : <div className="table-scroll"><table aria-label="Proizvodni nalogi">
        <thead><tr><th scope="col">Nalog</th><th scope="col">Izdelek</th><th scope="col">Količina</th><th scope="col">Datum</th><th scope="col">Stanje</th><th scope="col">Receptura</th></tr></thead>
        <tbody>{orders.map(order => <tr key={order.id}>
          <td>#{order.id}</td><td>{order.product_name}</td><td>{order.planned_qty.toLocaleString("sl-SI")} {order.product_unit}</td>
          <td>{order.planned_date.split("-").reverse().join(".")}</td><td>{statusLabels[order.status]}</td>
          <td><details><summary>Verzija {order.recipe_version}</summary><Requirements items={order.requirements} /></details></td>
        </tr>)}</tbody>
      </table></div>)}
    </section>
  </div>;
}
