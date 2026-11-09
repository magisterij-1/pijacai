// — seznam/podrobnosti šarž in zaključek polnjenja.
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { User } from "../api/auth";
import { BatchApiError, finishBatch, getBatch, listBatches } from "../api/batches";
import type { Batch, BatchFields, BatchSummary } from "../api/batches";
import { formatDecimal } from "../quantities";
import { QualityMeasurements } from "./QualityMeasurements";

const statusNames: Record<Batch["status"], string> = {
  in_production: "V proizvodnji", awaiting_qc: "Čaka na kontrolo", released: "Sproščena", rejected: "Zavrnjena",
};

function FinishBatch({ batch, onFinished, onConflict, onSaving }: {
  batch: Batch; onFinished: (batch: Batch) => void; onConflict: (message: string) => void; onSaving: (saving: boolean) => void;
}) {
  const [produced, setProduced] = useState("");
  const [rejected, setRejected] = useState("");
  const [fields, setFields] = useState<BatchFields>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const errors: BatchFields = {};
    const valid = (value: string) => /^\d+$/.test(value.trim()) && value.trim().length <= 10 && Number(value) <= 2147483647;
    if (!valid(produced)) errors.produced_qty = "Vnesi celo število od 0 do 2147483647.";
    if (!valid(rejected)) errors.rejected_qty = "Vnesi celo število od 0 do 2147483647.";
    if (!errors.produced_qty && !errors.rejected_qty && Number(rejected) > Number(produced)) {
      errors.rejected_qty = "Izmet ne sme presegati proizvedene količine.";
    }
    setFields(errors); setError("");
    if (Object.keys(errors).length) return;
    pending.current = true; setSaving(true); onSaving(true);
    try {
      const result = await finishBatch(batch.id, { produced_qty: Number(produced), rejected_qty: Number(rejected) });
      onFinished(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Zaključek polnjenja ni uspel.");
      if (error instanceof BatchApiError) {
        setFields(error.fields);
        if (error.status === 409 || error.status === 403 || error.status === 404) onConflict(error.message);
      }
    } finally {
      pending.current = false; setSaving(false); onSaving(false);
    }
  }

  return <section aria-labelledby="finish-title">
    <h4 id="finish-title">Zaključek polnjenja</h4>
    <p>Po predaji v kontrolo količin ni več mogoče spreminjati.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <form onSubmit={submit}>
      <fieldset disabled={saving}>
        <label htmlFor="finish-produced">Proizvedena količina</label>
        <input id="finish-produced" required inputMode="numeric" maxLength={10} value={produced}
          aria-invalid={Boolean(fields.produced_qty)} aria-describedby={fields.produced_qty ? "finish-produced-error" : undefined}
          onChange={event => setProduced(event.target.value)} />
        {fields.produced_qty && <small id="finish-produced-error" className="field-error" role="alert">{fields.produced_qty}</small>}
        <label htmlFor="finish-rejected">Izmet</label>
        <input id="finish-rejected" required inputMode="numeric" maxLength={10} value={rejected}
          aria-invalid={Boolean(fields.rejected_qty)} aria-describedby={fields.rejected_qty ? "finish-rejected-error" : undefined}
          onChange={event => setRejected(event.target.value)} />
        {fields.rejected_qty && <small id="finish-rejected-error" className="field-error" role="alert">{fields.rejected_qty}</small>}
        <button type="submit">{saving ? "Predajanje …" : "Predaj v kontrolo"}</button>
      </fieldset>
    </form>
  </section>;
}

export function Batches({ user }: { user: User }) {
  const queue = user.role === "quality";
  const [items, setItems] = useState<BatchSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [success, setSuccess] = useState("");
  const [actionError, setActionError] = useState("");
  const [saving, setSaving] = useState(false);
  const [listVersion, setListVersion] = useState(0);
  const [detailVersion, setDetailVersion] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setListError(""); setItems([]);
    listBatches(queue ? "awaiting_qc" : "in_production", controller.signal)
      .then(result => { if (!controller.signal.aborted) setItems(result); })
      .catch(error => { if (!controller.signal.aborted) setListError(error instanceof Error ? error.message : "Šarž ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [queue, listVersion]);

  useEffect(() => {
    if (selected === null) return;
    const controller = new AbortController();
    setLoadingDetail(true); setDetailError(""); setBatch(null);
    getBatch(selected, controller.signal)
      .then(result => { if (!controller.signal.aborted) setBatch(result); })
      .catch(error => { if (!controller.signal.aborted) setDetailError(error instanceof Error ? error.message : "Podrobnosti ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoadingDetail(false); });
    return () => controller.abort();
  }, [selected, detailVersion]);

  useEffect(() => { if (batch) heading.current?.focus(); }, [batch]);

  function refresh() { setListVersion(value => value + 1); setDetailVersion(value => value + 1); }

  return <div className="users-content">
    <button className="secondary" disabled={loading || loadingDetail || saving} onClick={refresh}>Osveži šarže</button>
    {success && <p className="success" role="status">{success}</p>}
    {actionError && <p className="error" role="alert">{actionError}</p>}
    {listError && <p className="error" role="alert">{listError}</p>}
    {loading && <p role="status">Nalaganje šarž …</p>}
    {!loading && !listError && !items.length && <p>{queue ? "Ni šarž za kontrolo." : "Ni aktivnih šarž."}</p>}
    {!!items.length && <div className="table-scroll"><table aria-label={queue ? "Čakalna vrsta kontrole" : "Aktivne proizvodne šarže"}>
      <thead><tr><th scope="col">Šarža</th><th scope="col">Izdelek</th><th scope="col">Linija</th><th scope="col">Stanje</th><th scope="col">Podrobnosti</th></tr></thead>
      <tbody>{items.map(item => <tr key={item.id}>
        <td>{item.batch_code}</td><td>{item.product_name}</td><td>{item.line_name}</td><td>{statusNames[item.status]}</td>
        <td><button className="secondary" disabled={saving || selected === item.id} aria-label={`Odpri šaržo ${item.batch_code}`}
          onClick={() => { setBatch(null); setSuccess(""); setActionError(""); setSelected(item.id); }}>Odpri</button></td>
      </tr>)}</tbody>
    </table></div>}
    {loadingDetail && <p role="status">Nalaganje podrobnosti …</p>}
    {detailError && <p className="error" role="alert">{detailError}</p>}
    {batch && <section aria-labelledby="batch-detail-title">
      <h3 id="batch-detail-title" tabIndex={-1} ref={heading}>Šarža {batch.batch_code}</h3>
      <p>{batch.product_name} · {batch.line_name} · Nalog #{batch.order_id} · Receptura v{batch.recipe_version}</p>
      <p>Stanje: {statusNames[batch.status]}</p>
      <p>Planirano: {formatDecimal(batch.planned_qty)} {batch.product_unit}</p>
      <p>Proizvedeno: {batch.produced_qty} {batch.product_unit} · Izmet: {batch.rejected_qty} {batch.product_unit}</p>
      {batch.finished_at && <p>Zaključeno: {new Date(batch.finished_at).toLocaleString("sl-SI")}</p>}
      {batch.decided_at && <p>Odločil kontrolor #{batch.decided_by} · {new Date(batch.decided_at).toLocaleString("sl-SI")}</p>}
      {batch.decision_note && <p className="decision-note"><strong>Razlog zavrnitve:</strong> {batch.decision_note}</p>}
      <h4>Porabljene serije</h4>
      <div className="table-scroll"><table aria-label="Porabljene serije šarže">
        <thead><tr><th scope="col">Sestavina</th><th scope="col">Dobavitelj</th><th scope="col">Serija</th><th scope="col">Porabljeno</th></tr></thead>
        <tbody>{batch.consumptions.map(item => <tr key={item.material_lot_id}>
          <td>{item.material_name}</td><td>{item.supplier_name}</td><td>{item.supplier_lot_no}</td><td>{formatDecimal(item.qty)} {item.unit}</td>
        </tr>)}</tbody>
      </table></div>
      {user.role === "quality" && <QualityMeasurements key={batch.id} batch={batch} onSaving={setSaving}
        onConflict={message => { setActionError(message); refresh(); }} onReleased={result => {
          setBatch(result); setActionError(""); setSuccess(`Šarža ${result.batch_code} je sproščena.`); setListVersion(version => version + 1);
        }} onRejected={result => {
          setBatch(result); setActionError(""); setSuccess(`Šarža ${result.batch_code} je zavrnjena.`); setListVersion(version => version + 1);
        }} />}
      {user.role === "operator" && batch.status === "in_production" && (batch.operator_id === user.id
        ? <FinishBatch key={batch.id} batch={batch} onSaving={setSaving} onConflict={message => { setActionError(message); refresh(); }} onFinished={result => {
          setBatch(result); setActionError(""); setSuccess(`Šarža ${result.batch_code} je predana v kontrolo.`); setListVersion(value => value + 1);
        }} />
        : <p>Šaržo lahko zaključi samo operater, ki jo je zagnal.</p>)}
    </section>}
  </div>;
}
