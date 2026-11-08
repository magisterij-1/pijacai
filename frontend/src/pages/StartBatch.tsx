import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { BatchApiError, listLines, previewBatch, startBatch } from "../api/batches";
import type { Batch, BatchFields, BatchPreview, Line, StockRequirement } from "../api/batches";
import type { Order } from "../api/orders";
import { formatDecimal, milli } from "../quantities";

export function StartBatch({ orders, loadingOrders, onStarted }: {
  orders: Order[]; loadingOrders: boolean; onStarted: () => void;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [loadingLines, setLoadingLines] = useState(true);
  const [linesError, setLinesError] = useState("");
  const [refreshLines, setRefreshLines] = useState(0);
  const [orderId, setOrderId] = useState("");
  const [lineId, setLineId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [fields, setFields] = useState<BatchFields & { order_id?: string }>({});
  const [preview, setPreview] = useState<BatchPreview | null>(null);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState<StockRequirement[]>([]);
  const [created, setCreated] = useState<Batch | null>(null);
  const previewRequest = useRef<AbortController | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const eligible = orders.filter(order => order.status === "planned" || order.status === "in_progress");
  const normalizedQty = quantity.trim().replace(",", ".");

  function invalidate() {
    previewRequest.current?.abort();
    setPreview(null); setChecking(false); setMissing([]);
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoadingLines(true); setLinesError("");
    listLines(controller.signal)
      .then(result => { if (!controller.signal.aborted) setLines(result); })
      .catch(error => { if (!controller.signal.aborted) setLinesError(error instanceof Error ? error.message : "Linij ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoadingLines(false); });
    return () => controller.abort();
  }, [refreshLines]);

  useEffect(() => { previewRequest.current?.abort(); setPreview(null); setChecking(false); }, [orders]);
  useEffect(() => () => previewRequest.current?.abort(), []);
  useEffect(() => { if (created) resultHeading.current?.focus(); }, [created]);

  function validate() {
    const errors: BatchFields & { order_id?: string } = {};
    if (!eligible.some(order => order.id === Number(orderId))) errors.order_id = "Izberi načrtovan ali tekoč nalog.";
    if (!lines.some(line => line.id === Number(lineId))) errors.line_id = "Izberi aktivno linijo.";
    if (!/^\d+(?:\.\d{1,3})?$/.test(normalizedQty) || normalizedQty.length > 32 || milli(normalizedQty) <= 0n || milli(normalizedQty) > 999999999999n) {
      errors.qty = "Vnesi pozitivno količino z največ 3 decimalnimi mesti in 9 mesti pred vejico.";
    }
    setFields(errors);
    return Object.keys(errors).length === 0;
  }

  async function checkStock() {
    if (starting || checking || loadingLines || loadingOrders || !validate()) return;
    previewRequest.current?.abort();
    const controller = new AbortController();
    previewRequest.current = controller;
    setChecking(true); setPreview(null); setError(""); setMissing([]);
    try {
      const result = await previewBatch(Number(orderId), { line_id: Number(lineId), qty: normalizedQty }, controller.signal);
      if (!controller.signal.aborted) setPreview(result);
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof Error ? error.message : "Preverjanje ni uspelo.");
        if (error instanceof BatchApiError) setFields(error.fields);
      }
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (starting || checking || loadingLines || loadingOrders || !validate()) return;
    if (!preview?.can_start || preview.order_id !== Number(orderId) || preview.line_id !== Number(lineId) || milli(preview.qty) !== milli(normalizedQty)) {
      setError("Pred zagonom preveri zaloge. Vseh sestavin mora biti dovolj.");
      return;
    }
    setStarting(true); setError(""); setMissing([]);
    try {
      const result = await startBatch(Number(orderId), { line_id: Number(lineId), qty: normalizedQty });
      setCreated(result); setPreview(null); onStarted();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Zagon šarže ni uspel.");
      setPreview(null);
      if (error instanceof BatchApiError) { setFields(error.fields); setMissing(error.missing); }
    } finally {
      setStarting(false);
    }
  }

  if (created) return <section aria-labelledby="started-batch-title">
    <p className="success" role="status">Šarža je uspešno zagnana.</p>
    <h3 id="started-batch-title" tabIndex={-1} ref={resultHeading}>Šarža {created.batch_code}</h3>
    <p>{created.product_name} · {formatDecimal(created.planned_qty)} {created.product_unit} · {created.line_name}</p>
    <p>Stanje: V proizvodnji · Nalog #{created.order_id} · Receptura v{created.recipe_version}</p>
    <h4>Porabljene serije surovin</h4>
    <div className="table-scroll"><table aria-label="Poraba zagnane šarže">
      <thead><tr><th scope="col">Surovina</th><th scope="col">Dobavitelj</th><th scope="col">Serija dobavitelja</th><th scope="col">Porabljeno</th></tr></thead>
      <tbody>{created.consumptions.map(item => <tr key={item.material_lot_id}>
        <td>{item.material_name}</td><td>{item.supplier_name}</td><td>{item.supplier_lot_no}</td><td>{formatDecimal(item.qty)} {item.unit}</td>
      </tr>)}</tbody>
    </table></div>
    <button className="secondary" onClick={() => { setCreated(null); setQuantity(""); invalidate(); }}>Nazaj na zagon</button>
  </section>;

  const requirements = preview?.requirements ?? missing;
  const disabled = starting || loadingLines || loadingOrders || !eligible.length || !lines.length;
  const fieldError = (field: keyof typeof fields) => fields[field] ? <small id={`batch-${field}-error`} className="field-error" role="alert">{fields[field]}</small> : null;

  return <section aria-labelledby="start-batch-title">
    <div className="workspace-header"><h3 id="start-batch-title">Zagon šarže</h3>
      <button className="secondary" disabled={loadingLines || starting || checking} onClick={() => { invalidate(); setRefreshLines(value => value + 1); }}>Osveži linije</button>
    </div>
    {linesError && <p className="error" role="alert">{linesError}</p>}
    {loadingLines && <p role="status">Nalaganje linij …</p>}
    {!loadingLines && !linesError && !lines.length && <p>Ni aktivnih proizvodnih linij.</p>}
    {!loadingOrders && !eligible.length && <p>Ni načrtovanih ali tekočih nalogov za zagon.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <form onSubmit={submit}>
      <fieldset disabled={disabled}>
        <label htmlFor="batch-order">Proizvodni nalog</label>
        <select id="batch-order" required value={orderId} aria-invalid={Boolean(fields.order_id)} aria-describedby={fields.order_id ? "batch-order_id-error" : undefined}
          onChange={event => { setOrderId(event.target.value); invalidate(); }}>
          <option value="">Izberi …</option>{eligible.map(order => <option key={order.id} value={order.id}>#{order.id} · {order.product_name} · {order.planned_qty} {order.product_unit}</option>)}
        </select>{fieldError("order_id")}
        <label htmlFor="batch-line">Proizvodna linija</label>
        <select id="batch-line" required value={lineId} aria-invalid={Boolean(fields.line_id)} aria-describedby={fields.line_id ? "batch-line_id-error" : undefined}
          onChange={event => { setLineId(event.target.value); invalidate(); }}>
          <option value="">Izberi …</option>{lines.map(line => <option key={line.id} value={line.id}>{line.name}</option>)}
        </select>{fieldError("line_id")}
        <label htmlFor="batch-qty">Količina šarže</label>
        <input id="batch-qty" required inputMode="decimal" maxLength={32} value={quantity} aria-invalid={Boolean(fields.qty)} aria-describedby={fields.qty ? "batch-qty-error" : undefined}
          onChange={event => { setQuantity(event.target.value); invalidate(); }} />{fieldError("qty")}
        <button type="button" disabled={checking} onClick={() => void checkStock()}>{checking ? "Preverjanje …" : "Preveri zaloge"}</button>
      </fieldset>
      {requirements.length > 0 && <section aria-labelledby="batch-stock-title">
        <h4 id="batch-stock-title">Zaloge sestavin</h4>
        {preview && !preview.can_start && <p className="error" role="alert">Za zagon ni dovolj vseh sestavin.</p>}
        <div className="table-scroll"><table aria-label="Preverjanje zalog za šaržo">
          <thead><tr><th scope="col">Sestavina</th><th scope="col">Potrebno</th><th scope="col">Na zalogi</th><th scope="col">Manjka</th><th scope="col">Stanje</th></tr></thead>
          <tbody>{requirements.map(item => <tr key={item.material_id}>
            <td>{item.material_name}</td><td>{formatDecimal(item.required_qty)} {item.unit}</td><td>{formatDecimal(item.available_qty)} {item.unit}</td>
            <td>{formatDecimal(item.missing_qty)} {item.unit}</td><td>{item.status}</td>
          </tr>)}</tbody>
        </table></div>
      </section>}
      <button type="submit" disabled={disabled || checking || !preview?.can_start}>{starting ? "Zaganjanje …" : "Zaženi šaržo"}</button>
    </form>
  </section>;
}
