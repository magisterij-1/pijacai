import { useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { InventoryApiError, listMaterialLots, listMaterials, listSuppliers, receiveMaterial } from "../api/inventory";
import type { Material, MaterialLot, ReceiptFields, Supplier } from "../api/inventory";
import { formatQuantity, milli } from "../quantities";

const emptyForm = { material_id: "", supplier_id: "", supplier_lot_no: "", received_qty: "", unit_cost: "" };
type Form = typeof emptyForm;

function validDecimal(value: string, positive: boolean): boolean {
  if (!/^\d+(?:\.\d{1,3})?$/.test(value) || value.length > 32) return false;
  const amount = milli(value);
  return amount <= 999999999999n && (positive ? amount > 0n : amount >= 0n);
}

export function ReceiveMaterials() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [lots, setLots] = useState<MaterialLot[]>([]);
  const [form, setForm] = useState<Form>(emptyForm);
  const [fields, setFields] = useState<ReceiptFields>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load(signal?: AbortSignal) {
    setLoading(true);
    setLoadError("");
    try {
      const [newMaterials, newSuppliers, newLots] = await Promise.all([
        listMaterials(signal), listSuppliers(signal), listMaterialLots(signal),
      ]);
      if (!signal?.aborted) {
        setMaterials(newMaterials); setSuppliers(newSuppliers); setLots(newLots);
      }
    } catch (error) {
      if (!signal?.aborted) setLoadError(error instanceof Error ? error.message : "Podatkov ni mogoče naložiti.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || loading) return;
    setMessage(""); setError("");
    const errors: ReceiptFields = {};
    const quantity = form.received_qty.trim().replace(",", ".");
    const price = form.unit_cost.trim().replace(",", ".");
    if (!materials.some(item => item.id === Number(form.material_id))) errors.material_id = "Izberi surovino ali embalažo.";
    if (!suppliers.some(item => item.id === Number(form.supplier_id))) errors.supplier_id = "Izberi dobavitelja.";
    if (!form.supplier_lot_no.trim()) errors.supplier_lot_no = "Vnesi dobaviteljevo številko serije.";
    if (!validDecimal(quantity, true)) errors.received_qty = "Vnesi pozitivno količino z največ 3 decimalnimi mesti in 9 mesti pred vejico.";
    if (!validDecimal(price, false)) errors.unit_cost = "Vnesi nenegativno ceno z največ 3 decimalnimi mesti in 9 mesti pred vejico.";
    setFields(errors);
    if (Object.keys(errors).length) return;
    setSaving(true);
    try {
      const created = await receiveMaterial({
        material_id: Number(form.material_id), supplier_id: Number(form.supplier_id),
        supplier_lot_no: form.supplier_lot_no.trim(), received_qty: quantity, unit_cost: price,
      });
      setLots(current => [...current, created]);
      setForm(current => ({ ...current, supplier_lot_no: "", received_qty: "", unit_cost: "" }));
      setMessage("Prejem je shranjen.");
      await load();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Prejema ni mogoče shraniti.");
      if (error instanceof InventoryApiError) setFields(error.fields);
    } finally {
      setSaving(false);
    }
  }

  const selected = materials.find(item => item.id === Number(form.material_id));
  const total = selected ? lots.filter(item => item.material_id === selected.id).reduce((sum, item) => sum + milli(item.remaining_qty), 0n) : null;
  const disabled = loading || saving || !materials.length || !suppliers.length;

  function props(field: keyof Form) {
    return {
      id: `receipt-${field}`, name: field, value: form[field],
      onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [field]: event.target.value }),
      "aria-invalid": Boolean(fields[field]),
      "aria-describedby": fields[field] ? `receipt-${field}-error` : undefined,
    };
  }
  function fieldError(field: keyof Form) {
    return fields[field] ? <small id={`receipt-${field}-error`} className="field-error" role="alert">{fields[field]}</small> : null;
  }

  return (
    <div className="users-content">
      <div><button className="secondary" disabled={loading || saving} onClick={() => void load()}>Osveži podatke</button></div>
      {message && <p className="success" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {loadError && <p className="error" role="alert">{loadError}</p>}
      {loading && <p role="status">Nalaganje podatkov …</p>}
      {!loading && !loadError && (!materials.length || !suppliers.length) && <p>Za vnos prejema potrebujete vsaj eno surovino in dobavitelja.</p>}
      <form onSubmit={submit}>
        <fieldset disabled={disabled}>
          <label htmlFor="receipt-material_id">Surovina ali embalaža</label>
          <select {...props("material_id")} required>
            <option value="">Izberi …</option>
            {materials.map(item => <option key={item.id} value={item.id}>{item.name} ({item.type === "packaging" ? "embalaža" : "surovina"}, {item.unit})</option>)}
          </select>
          {fieldError("material_id")}
          <label htmlFor="receipt-supplier_id">Dobavitelj</label>
          <select {...props("supplier_id")} required><option value="">Izberi …</option>{suppliers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          {fieldError("supplier_id")}
          <label htmlFor="receipt-supplier_lot_no">Dobaviteljeva številka serije</label>
          <input {...props("supplier_lot_no")} required maxLength={80} />
          {fieldError("supplier_lot_no")}
          <label htmlFor="receipt-received_qty">Količina{selected ? ` (${selected.unit})` : ""}</label>
          <input {...props("received_qty")} required inputMode="decimal" maxLength={32} />
          {fieldError("received_qty")}
          <label htmlFor="receipt-unit_cost">Nabavna cena na enoto</label>
          <input {...props("unit_cost")} required inputMode="decimal" maxLength={32} />
          {fieldError("unit_cost")}
          <small className="muted">Količina in cena: največ 3 decimalna mesta; dovoljena je vejica ali pika.</small>
          <button type="submit">{saving ? "Shranjevanje …" : "Shrani prejem"}</button>
        </fieldset>
      </form>
      {!loading && !loadError && selected && total !== null && <p role="status">Trenutna zaloga za {selected.name}: <strong>{formatQuantity(total)} {selected.unit}</strong></p>}
      <section aria-labelledby="receipts-title">
        <h3 id="receipts-title">Prejete serije</h3>
        {!loading && !loadError && lots.length === 0 && <p>Ni evidentiranih prejemov.</p>}
        {lots.length > 0 && <div className="table-scroll"><table>
          <caption className="sr-only">Prejete serije in njihove preostale količine</caption>
          <thead><tr><th scope="col">Surovina</th><th scope="col">Dobavitelj</th><th scope="col">Serija</th><th scope="col">Prejeto</th><th scope="col">Preostalo</th><th scope="col">Cena/enoto</th><th scope="col">Prejem</th></tr></thead>
          <tbody>{lots.map(lot => {
            const material = materials.find(item => item.id === lot.material_id);
            return <tr key={lot.id}>
              <td>{material?.name || `#${lot.material_id}`}</td>
              <td>{suppliers.find(item => item.id === lot.supplier_id)?.name || `#${lot.supplier_id}`}</td>
              <td>{lot.supplier_lot_no}</td>
              <td>{formatQuantity(milli(lot.received_qty))} {material?.unit}</td>
              <td>{formatQuantity(milli(lot.remaining_qty))} {material?.unit}</td>
              <td>{formatQuantity(milli(lot.unit_cost))}</td>
              <td>{new Date(lot.received_at).toLocaleString("sl-SI")}</td>
            </tr>;
          })}</tbody>
        </table></div>}
      </section>
    </div>
  );
}
