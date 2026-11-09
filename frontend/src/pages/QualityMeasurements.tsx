// — meritve, zgodovina, sprostitev in zavrnitev.
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Batch } from "../api/batches";
import { getQuality, QualityApiError, rejectBatch, releaseBatch, saveQualityCheck } from "../api/quality";
import type { QualityFields, QualityOverview, ReleaseProblems } from "../api/quality";
import { formatDecimal, milli } from "../quantities";

// Podpisane vrednosti pretvorimo v tisočinke brez izgube decimalne natančnosti.
function measurement(raw: string) {
  const normalized = raw.trim().replace(",", ".");
  if (!/^[+-]?\d{1,9}(?:\.\d{1,3})?$/.test(normalized)) return null;
  const unsigned = normalized.replace(/^[+-]/, "");
  return { normalized, scaled: milli(unsigned) * (normalized.startsWith("-") ? -1n : 1n) };
}

export function QualityMeasurements({ batch, onSaving, onConflict, onReleased, onRejected }: {
  batch: Pick<Batch, "id" | "status">;
  onSaving: (saving: boolean) => void;
  onConflict: (message: string) => void;
  onReleased: (batch: Batch) => void;
  onRejected: (batch: Batch) => void;
}) {
  const [overview, setOverview] = useState<QualityOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [parameterId, setParameterId] = useState("");
  const [value, setValue] = useState("");
  const [fields, setFields] = useState<QualityFields>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [releasing, setReleasing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");
  const [releaseProblems, setReleaseProblems] = useState<ReleaseProblems | null>(null);
  const pending = useRef(false);
  const active = useRef(true);
  const parameter = overview?.parameters.find(item => item.id === Number(parameterId));
  const parsed = measurement(value);
  const lower = parameter && measurement(parameter.min_value);
  const upper = parameter && measurement(parameter.max_value);
  const preview = parsed && lower && upper ? parsed.scaled >= lower.scaled && parsed.scaled <= upper.scaled : null;
  const missing = overview?.parameters.filter(item => !item.latest_check) ?? [];
  const invalid = overview?.parameters.filter(item => item.latest_check && !item.latest_check.passed) ?? [];
  const canRelease = batch.status === "awaiting_qc" && !!overview?.parameters.length && !missing.length && !invalid.length;

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError(""); setOverview(null);
    getQuality(batch.id, controller.signal)
      .then(result => { if (!controller.signal.aborted) setOverview(result); })
      .catch(error => { if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "Meritev ni mogoče naložiti."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [batch.id, refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || loading || !overview || batch.status !== "awaiting_qc") return;
    const errors: QualityFields = {};
    if (!parameter) errors.parameter_id = "Izberi parameter izdelka.";
    if (!parsed) errors.value = "Vnesi število z največ 9 mesti pred vejico in 3 decimalnimi mesti.";
    setFields(errors); setError(""); setSuccess(""); setReleaseProblems(null);
    if (Object.keys(errors).length || !parsed || !parameter) return;
    pending.current = true; setSaving(true); onSaving(true);
    try {
      const result = await saveQualityCheck(batch.id, { parameter_id: parameter.id, value: parsed.normalized });
      if (!active.current) return;
      setSuccess(`Meritev ${parameter.name} je shranjena: ${result.passed ? "ustreza" : "ne ustreza"}.`);
      setValue(""); setFields({}); setRefresh(version => version + 1);
    } catch (error) {
      if (!active.current) return;
      setError(error instanceof Error ? error.message : "Meritve ni mogoče shraniti.");
      if (error instanceof QualityApiError) {
        setFields(error.fields);
        if (error.status === 409 || error.status === 403 || error.status === 404) onConflict(error.message);
      }
    } finally {
      pending.current = false;
      if (active.current) { setSaving(false); onSaving(false); }
    }
  }

  async function release() {
    if (pending.current || loading || !canRelease) return;
    pending.current = true; setSaving(true); setReleasing(true); onSaving(true);
    setError(""); setSuccess(""); setReleaseProblems(null);
    try {
      const result = await releaseBatch(batch.id);
      if (!active.current) return;
      setSuccess("Šarža je uspešno sproščena.");
      onReleased(result);
    } catch (error) {
      if (!active.current) return;
      setError(error instanceof Error ? error.message : "Sprostitev šarže ni uspela.");
      if (error instanceof QualityApiError) {
        setReleaseProblems(error.problems);
        if (error.status === 422) setRefresh(version => version + 1);
        if (error.status === 409 || error.status === 403 || error.status === 404) onConflict(error.message);
      }
    } finally {
      pending.current = false;
      if (active.current) { setSaving(false); setReleasing(false); onSaving(false); }
    }
  }

  async function reject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current || batch.status !== "awaiting_qc") return;
    const normalized = reason.trim();
    const length = Array.from(normalized).length;
    setReasonError(""); setError(""); setSuccess(""); setReleaseProblems(null);
    if (length < 10 || length > 500) {
      setReasonError("Razlog mora vsebovati od 10 do 500 znakov.");
      return;
    }
    pending.current = true; setSaving(true); setRejecting(true); onSaving(true);
    try {
      const result = await rejectBatch(batch.id, normalized);
      if (!active.current) return;
      setReason(""); setSuccess("Šarža je uspešno zavrnjena."); onRejected(result);
    } catch (error) {
      if (!active.current) return;
      setError(error instanceof Error ? error.message : "Zavrnitev šarže ni uspela.");
      if (error instanceof QualityApiError) {
        setReasonError(error.fields.decision_note ?? "");
        if (error.status === 409 || error.status === 403 || error.status === 404) onConflict(error.message);
      }
    } finally {
      pending.current = false;
      if (active.current) { setSaving(false); setRejecting(false); onSaving(false); }
    }
  }

  return <section aria-labelledby="quality-title">
    <div className="workspace-header">
      <h4 id="quality-title">Meritve kakovosti</h4>
      <button className="secondary" disabled={loading || saving} onClick={() => { setError(""); setReleaseProblems(null); setRefresh(version => version + 1); }}>Osveži meritve</button>
    </div>
    {loading && <p role="status">Nalaganje meritev …</p>}
    {loadError && <p className="error" role="alert">{loadError}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {releaseProblems && <div role="alert">
      {!!releaseProblems.missing.length && <><p>Manjkajoči parametri ob sprostitvi:</p><ul>{releaseProblems.missing.map(item => <li key={item.parameter_id}>{item.name}</li>)}</ul></>}
      {!!releaseProblems.invalid.length && <><p>Neustrezni parametri ob sprostitvi:</p><ul>{releaseProblems.invalid.map(item => <li key={item.parameter_id}>{item.name}</li>)}</ul></>}
    </div>}
    {success && <p className="success" role="status">{success}</p>}
    {overview && <>
      {!overview.parameters.length ? <p>Za izdelek ni določenih parametrov kakovosti.</p> : <>
        <div className="table-scroll"><table aria-label="Zahtevani parametri kakovosti">
          <thead><tr><th scope="col">Parameter</th><th scope="col">Enota</th><th scope="col">Dovoljene meje</th><th scope="col">Zadnja vrednost</th><th scope="col">Ustreznost</th></tr></thead>
          <tbody>{overview.parameters.map(item => <tr key={item.id}>
            <td>{item.name}</td><td>{item.unit}</td><td>{formatDecimal(item.min_value)}–{formatDecimal(item.max_value)}</td>
            <td>{item.latest_check ? formatDecimal(item.latest_check.value) : "Manjka meritev"}</td>
            <td>{item.latest_check ? (item.latest_check.passed ? "Ustreza" : "Ne ustreza") : "Ni izmerjeno"}</td>
          </tr>)}</tbody>
        </table></div>
        {batch.status === "awaiting_qc" ? <form id="quality-measurement-form" onSubmit={submit}>
          <fieldset disabled={saving || loading}>
            <label htmlFor="quality-parameter">Parameter</label>
            <select id="quality-parameter" required value={parameterId} aria-invalid={Boolean(fields.parameter_id)}
              aria-describedby={fields.parameter_id ? "quality-parameter-error" : undefined}
              onChange={event => { setParameterId(event.target.value); setValue(""); setFields({}); setError(""); setSuccess(""); }}>
              <option value="">Izberi …</option>{overview.parameters.map(item => <option key={item.id} value={item.id}>{item.name} ({item.unit})</option>)}
            </select>
            {fields.parameter_id && <small id="quality-parameter-error" className="field-error" role="alert">{fields.parameter_id}</small>}
            {parameter && <p>Enota: {parameter.unit} · Dovoljeno: {formatDecimal(parameter.min_value)}–{formatDecimal(parameter.max_value)} (vključno z mejama)</p>}
            <label htmlFor="quality-value">Izmerjena vrednost</label>
            <input id="quality-value" required inputMode="decimal" maxLength={32} value={value} aria-invalid={Boolean(fields.value)}
              aria-describedby={fields.value ? "quality-value-error" : undefined}
              onChange={event => { setValue(event.target.value); setFields(current => ({ ...current, value: undefined })); setError(""); setSuccess(""); }} />
            {fields.value && <small id="quality-value-error" className="field-error" role="alert">{fields.value}</small>}
            {preview !== null && <p role="status">Predogled: {preview ? "ustreza" : "ne ustreza"}. Meritev še ni shranjena.</p>}
            <button type="submit">{saving && !releasing && !rejecting ? "Shranjevanje …" : "Shrani meritev"}</button>
          </fieldset>
        </form> : <p>Meritve je mogoče vnašati samo za šaržo, ki čaka na kontrolo.</p>}
      </>}
      {batch.status === "awaiting_qc" && <section aria-labelledby="release-title">
        <h4 id="release-title">Sprostitev šarže</h4>
        <p>Sprostitev upošteva zadnje shranjene meritve vseh zahtevanih parametrov.</p>
        {!!missing.length && <p>Manjkajoče meritve: {missing.map(item => item.name).join(", ")}.</p>}
        {!!invalid.length && <p>Neustrezne meritve: {invalid.map(item => item.name).join(", ")}.</p>}
        {canRelease && <p>Vse zahtevane meritve so vnesene in ustrezajo mejam.</p>}
        <button type="button" disabled={loading || saving || !canRelease} onClick={() => void release()}>{releasing ? "Sproščanje …" : "Sprosti šaržo"}</button>
      </section>}
      {!!overview.checks.length && <details>
        <summary>Zgodovina meritev</summary>
        <div className="table-scroll"><table aria-label="Zgodovina meritev kakovosti">
          <thead><tr><th scope="col">Parameter</th><th scope="col">Vrednost</th><th scope="col">Ustreznost</th><th scope="col">Kontrolor</th><th scope="col">Čas</th></tr></thead>
          <tbody>{overview.checks.map(check => {
            const item = overview.parameters.find(parameter => parameter.id === check.parameter_id);
            return <tr key={check.id}><td>{item?.name ?? `#${check.parameter_id}`}</td><td>{formatDecimal(check.value)} {item?.unit}</td>
              <td>{check.passed ? "Ustreza" : "Ne ustreza"}</td><td>#{check.checked_by}</td><td>{new Date(check.checked_at).toLocaleString("sl-SI")}</td></tr>;
          })}</tbody>
        </table></div>
      </details>}
    </>}
    {batch.status === "awaiting_qc" && <section aria-labelledby="reject-title">
      <h4 id="reject-title">Zavrnitev šarže</h4>
      <p>Šaržo lahko zavrneš tudi brez vseh meritev. Vnesi razlog z 10–500 znaki.</p>
      <form id="quality-reject-form" onSubmit={reject}>
        <fieldset disabled={saving}>
          <label htmlFor="quality-reason">Razlog zavrnitve</label>
          <textarea id="quality-reason" rows={4} required value={reason} aria-invalid={Boolean(reasonError)}
            aria-describedby={reasonError ? "quality-reason-error" : undefined}
            onChange={event => { setReason(event.target.value); setReasonError(""); setError(""); setSuccess(""); }} />
          {reasonError && <small id="quality-reason-error" className="field-error" role="alert">{reasonError}</small>}
          <button className="danger" type="submit">{rejecting ? "Zavračanje …" : "Zavrni šaržo"}</button>
        </fieldset>
      </form>
    </section>}
  </section>;
}
