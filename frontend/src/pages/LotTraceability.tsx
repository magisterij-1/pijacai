import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Material } from "../api/inventory";
import { findTraceLots, listTraceMaterials, traceLot, TraceabilityApiError } from "../api/traceability";
import type { LotSearchFields, LotTraceability as LotResult, TraceLot } from "../api/traceability";
import { formatDecimal } from "../quantities";

const statusNames: Record<LotResult["batches"][number]["status"], string> = {
  in_production: "V proizvodnji", awaiting_qc: "Čaka na kontrolo", released: "Sproščena", rejected: "Zavrnjena",
};

export function LotTraceability() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loadingMaterials, setLoadingMaterials] = useState(true);
  const [materialsError, setMaterialsError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [materialId, setMaterialId] = useState("");
  const [code, setCode] = useState("");
  const [fields, setFields] = useState<LotSearchFields>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<TraceLot[]>([]);
  const [selected, setSelected] = useState("");
  const [data, setData] = useState<LotResult | null>(null);
  const request = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingMaterials(true); setMaterialsError(""); setMaterials([]);
    listTraceMaterials(controller.signal)
      .then(items => { if (!controller.signal.aborted) setMaterials(items); })
      .catch(error => { if (!controller.signal.aborted) setMaterialsError(error instanceof Error ? error.message : "Surovin ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoadingMaterials(false); });
    return () => controller.abort();
  }, [refresh]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (data) heading.current?.focus(); }, [data]);

  function invalidate() {
    request.current?.abort(); setLoading(false); setCandidates([]); setSelected(""); setData(null); setFields({}); setError("");
  }
  function showError(error: unknown) {
    setError(error instanceof Error ? error.message : "Sledljivosti serije ni mogoče naložiti.");
    if (error instanceof TraceabilityApiError) setFields(error.fields);
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || loadingMaterials) return;
    invalidate();
    const errors: LotSearchFields = {};
    if (!materials.some(item => item.id === Number(materialId))) errors.material_id = "Izberi surovino ali embalažo.";
    if (!code.trim() || Array.from(code.trim()).length > 80) errors.supplier_lot_no = "Vnesi dobaviteljevo številko serije z največ 80 znaki.";
    setFields(errors);
    if (Object.keys(errors).length) return;
    const controller = new AbortController(); request.current = controller; setLoading(true);
    try {
      const matches = await findTraceLots({ material_id: Number(materialId), supplier_lot_no: code.trim() }, controller.signal);
      if (controller.signal.aborted) return;
      if (!matches.length) throw new TraceabilityApiError("Serija ni najdena.", 404);
      setCandidates(matches);
      if (matches.length === 1) {
        setSelected(String(matches[0].id));
        const result = await traceLot(matches[0].id, controller.signal);
        if (!controller.signal.aborted) setData(result);
      }
    } catch (error) { if (!controller.signal.aborted) showError(error); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }

  async function chooseLot(id: string) {
    request.current?.abort(); setSelected(id); setData(null); setError(""); setLoading(false);
    if (!candidates.some(item => item.id === Number(id))) return;
    const controller = new AbortController(); request.current = controller; setLoading(true);
    try {
      const result = await traceLot(Number(id), controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (error) { if (!controller.signal.aborted) showError(error); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }

  return <div className="users-content">
    <button className="secondary" disabled={loadingMaterials} onClick={() => { invalidate(); setRefresh(value => value + 1); }}>Osveži surovine</button>
    {loadingMaterials && <p role="status">Nalaganje surovin …</p>}
    {materialsError && <p className="error" role="alert">{materialsError}</p>}
    {!loadingMaterials && !materialsError && !materials.length && <p>Ni surovin ali embalaže za izbor.</p>}
    <form onSubmit={search}>
      <label htmlFor="trace-material">Surovina ali embalaža</label>
      <select id="trace-material" value={materialId} disabled={loadingMaterials} required aria-invalid={Boolean(fields.material_id)}
        aria-describedby={fields.material_id ? "trace-material-error" : undefined}
        onChange={event => { invalidate(); setMaterialId(event.target.value); }}>
        <option value="">Izberi …</option>{materials.map(item => <option key={item.id} value={item.id}>{item.name} ({item.unit})</option>)}
      </select>
      {fields.material_id && <small id="trace-material-error" className="field-error" role="alert">{fields.material_id}</small>}
      <label htmlFor="trace-lot-code">Dobaviteljeva številka serije</label>
      <input id="trace-lot-code" value={code} required aria-invalid={Boolean(fields.supplier_lot_no)} aria-describedby={fields.supplier_lot_no ? "trace-lot-code-error" : undefined}
        onChange={event => { invalidate(); setCode(event.target.value); }} />
      {fields.supplier_lot_no && <small id="trace-lot-code-error" className="field-error" role="alert">{fields.supplier_lot_no}</small>}
      <button type="submit" disabled={loadingMaterials || loading || !materials.length}>{loading ? "Iskanje …" : "Poišči serijo"}</button>
    </form>
    {loading && <p role="status">Nalaganje sledljivosti serije …</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!!candidates.length && <>
      <label htmlFor="trace-lot-choice">Izbrana serija in dobavitelj</label>
      {candidates.length > 1 && <p>Ista številka pripada več serijam. Izberi dobavitelja.</p>}
      <select id="trace-lot-choice" value={selected} onChange={event => void chooseLot(event.target.value)}>
        <option value="">Izberi …</option>{candidates.map(item => <option key={item.id} value={item.id}>
          {item.supplier_name} · {item.supplier_lot_no} · #{item.id}
        </option>)}
      </select>
    </>}
    {data && <section aria-labelledby="lot-trace-title">
      <h3 id="lot-trace-title" ref={heading} tabIndex={-1}>Serija {data.supplier_lot_no}</h3>
      <p>{data.material_name} · Dobavitelj: {data.supplier_name} · Serija #{data.id}</p>
      <p>Prejeto: {formatDecimal(data.received_qty)} {data.unit} · Preostalo: {formatDecimal(data.remaining_qty)} {data.unit}</p>
      <p>Skupna poraba: {formatDecimal(data.total_consumed_qty)} {data.unit}</p>
      {!data.batches.length ? <p role="status">Ta serija še ni bila uporabljena v nobeni šarži.</p> : <>
        <h4>Povezane šarže od najstarejše</h4>
        <div className="table-scroll"><table aria-label="Sledljivost serije do šarž">
          <thead><tr><th scope="col">Šarža</th><th scope="col">Izdelek</th><th scope="col">Datum zagona</th><th scope="col">Stanje</th><th scope="col">Poraba iz serije</th></tr></thead>
          <tbody>{data.batches.map(item => <tr key={item.batch_id}>
            <td>{item.batch_code}</td><td>{item.product_name}</td><td>{new Date(item.started_at).toLocaleString("sl-SI")}</td>
            <td>{statusNames[item.status]}</td><td>{formatDecimal(item.consumed_qty)} {data.unit}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
    </section>}
  </div>;
}
