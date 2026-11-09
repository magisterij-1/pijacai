import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { traceBatchByCode, TraceabilityApiError } from "../api/traceability";
import type { BatchTraceability } from "../api/traceability";
import { formatDecimal } from "../quantities";
import { LotTraceability } from "./LotTraceability";

const statusNames: Record<BatchTraceability["status"], string> = {
  in_production: "V proizvodnji", awaiting_qc: "Čaka na kontrolo", released: "Sproščena", rejected: "Zavrnjena",
};

export function Traceability() {
  const [direction, setDirection] = useState<"batch" | "lot">("batch");
  return <>
    <div className="stock-filters" aria-label="Smer sledljivosti">
      <button className="secondary" type="button" aria-pressed={direction === "batch"} onClick={() => setDirection("batch")}>Po šarži</button>
      <button className="secondary" type="button" aria-pressed={direction === "lot"} onClick={() => setDirection("lot")}>Po seriji surovine</button>
    </div>
    {direction === "batch" ? <BatchTraceabilityView /> : <LotTraceability />}
  </>;
}

function BatchTraceabilityView() {
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<BatchTraceability | null>(null);
  const request = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (data) heading.current?.focus(); }, [data]);

  function changeCode(value: string) {
    request.current?.abort();
    setCode(value); setCodeError(""); setError(""); setData(null); setLoading(false);
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    request.current?.abort();
    setData(null); setError(""); setCodeError("");
    const normalized = code.trim();
    if (!normalized || Array.from(normalized).length > 80) {
      setCodeError("Vnesi kodo šarže z največ 80 znaki.");
      return;
    }
    const controller = new AbortController();
    request.current = controller; setLoading(true);
    try {
      const result = await traceBatchByCode(normalized, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof Error ? error.message : "Sledljivosti ni mogoče naložiti.");
        if (error instanceof TraceabilityApiError) setCodeError(error.codeError ?? "");
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return <div className="users-content">
    <form onSubmit={search}>
      <label htmlFor="trace-batch-code">Koda šarže</label>
      <input id="trace-batch-code" required value={code} aria-invalid={Boolean(codeError)} aria-describedby={codeError ? "trace-code-error" : undefined}
        onChange={event => changeCode(event.target.value)} />
      {codeError && <small id="trace-code-error" className="field-error" role="alert">{codeError}</small>}
      <button type="submit" disabled={loading}>{loading ? "Iskanje …" : "Poišči šaržo"}</button>
    </form>
    {loading && <p role="status">Nalaganje sledljivosti …</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {data && <section aria-labelledby="trace-result-title">
      <h3 id="trace-result-title" ref={heading} tabIndex={-1}>Šarža {data.batch_code}</h3>
      <p>Izdelek: {data.product_name} · Stanje: {statusNames[data.status]}</p>
      <p>Nalog #{data.order_id} · {data.line_name} · Receptura v{data.recipe_version}</p>
      {data.decided_at && <p>Odločil kontrolor #{data.decided_by} · {new Date(data.decided_at).toLocaleString("sl-SI")}</p>}
      {data.decision_note && <p className="decision-note"><strong>Razlog zavrnitve:</strong> {data.decision_note}</p>}
      <p role="status">Najdenih uporabljenih serij: {data.consumptions.length}.</p>
      {!data.consumptions.length ? <p>Za to šaržo ni zapisane porabe surovin.</p> : <>
        <h4>Uporabljene serije surovin in embalaže</h4>
        <div className="table-scroll"><table aria-label="Sledljivost šarže do uporabljenih serij">
          <thead><tr><th scope="col">Surovina ali embalaža</th><th scope="col">Dobavitelj</th><th scope="col">Dobaviteljeva serija</th><th scope="col">Porabljena količina</th></tr></thead>
          <tbody>{data.consumptions.map(item => <tr key={item.material_lot_id}>
            <td>{item.material_name}</td><td>{item.supplier_name}</td><td>{item.supplier_lot_no}</td><td>{formatDecimal(item.qty)} {item.unit}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
      {!!data.totals.length && <section aria-labelledby="trace-totals-title">
        <h4 id="trace-totals-title">Skupna poraba po surovinah</h4>
        <ul className="stock-totals">{data.totals.map(item => <li key={item.material_id}>
          <span>{item.material_name}</span><strong>{formatDecimal(item.consumed_qty)} {item.unit}</strong>
        </li>)}</ul>
      </section>}
    </section>}
  </div>;
}
