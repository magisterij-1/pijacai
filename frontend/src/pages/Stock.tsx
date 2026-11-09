// — pregled zalog po materialih in serijah.
import { useEffect, useState } from "react";
import { getStock, listMaterials } from "../api/inventory";
import type { Material, Stock as StockData } from "../api/inventory";
import { formatQuantity, milli } from "../quantities";

export function Stock() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [materialId, setMaterialId] = useState("");
  const [includeConsumed, setIncludeConsumed] = useState(false);
  const [data, setData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMaterials, setLoadingMaterials] = useState(true);
  const [error, setError] = useState("");
  const [materialsError, setMaterialsError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingMaterials(true);
    setMaterialsError("");
    listMaterials(controller.signal)
      .then(result => { if (!controller.signal.aborted) setMaterials(result); })
      .catch(error => {
        if (!controller.signal.aborted) setMaterialsError(error instanceof Error ? error.message : "Šifranta ni mogoče naložiti.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoadingMaterials(false); });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);
    getStock({ material_id: materialId ? Number(materialId) : undefined, include_consumed: includeConsumed }, controller.signal)
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(error => {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Zalog ni mogoče naložiti.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [materialId, includeConsumed, refresh]);

  return (
    <div className="users-content">
      <div className="stock-filters">
        <div className="stock-filter">
          <label htmlFor="stock-material">Surovina ali embalaža</label>
          <select id="stock-material" value={materialId} disabled={loadingMaterials}
            onChange={event => setMaterialId(event.target.value)}>
            <option value="">Vse surovine</option>
            {materials.map(item => <option key={item.id} value={item.id}>{item.name} ({item.unit})</option>)}
          </select>
        </div>
        <label className="checkbox-label">
          <input type="checkbox" checked={includeConsumed} onChange={event => setIncludeConsumed(event.target.checked)} />
          Pokaži porabljene
        </label>
        <button className="secondary" disabled={loading || loadingMaterials} onClick={() => setRefresh(value => value + 1)}>Osveži zaloge</button>
      </div>
      {materialsError && <p className="error" role="alert">{materialsError}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {loading && <p role="status">Nalaganje zalog …</p>}
      {!loading && !error && data && (
        <>
          {data.totals.length > 0 && <section aria-labelledby="stock-totals-title">
            <h3 id="stock-totals-title">{materialId ? "Skupna zaloga izbrane surovine" : "Zaloga po surovinah"}</h3>
            <ul className="stock-totals">{data.totals.map(total => <li key={total.material_id}>
              <span>{total.material_name}</span>
              <strong>{formatQuantity(milli(total.remaining_qty))} {total.unit}</strong>
            </li>)}</ul>
          </section>}
          <section aria-labelledby="stock-lots-title">
            <h3 id="stock-lots-title">Serije po vrstnem redu FIFO</h3>
            {data.lots.length === 0 ? <p>Ni serij za izbrane pogoje.</p> : <div className="table-scroll"><table>
              <caption className="sr-only">Zaloge po serijah, od najstarejšega do najnovejšega prejema</caption>
              <thead><tr><th scope="col">Surovina</th><th scope="col">Dobavitelj</th><th scope="col">Serija dobavitelja</th><th scope="col">Prejeto</th><th scope="col">Preostalo</th><th scope="col">Datum prejema</th></tr></thead>
              <tbody>{data.lots.map(lot => <tr key={lot.id}>
                <td>{lot.material_name}</td><td>{lot.supplier_name}</td><td>{lot.supplier_lot_no}</td>
                <td>{formatQuantity(milli(lot.received_qty))} {lot.unit}</td>
                <td>{formatQuantity(milli(lot.remaining_qty))} {lot.unit}</td>
                <td>{new Date(lot.received_at).toLocaleString("sl-SI")}</td>
              </tr>)}</tbody>
            </table></div>}
          </section>
        </>
      )}
    </div>
  );
}
