import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { Role, User } from "../api/auth";
import { createUser, deactivateUser, listUsers, UserApiError } from "../api/users";
import type { UserCreate, UserFields } from "../api/users";

const roleLabels: Record<Role, string> = {
  operator: "Operater", quality: "Kontrolor kakovosti", planner: "Planer",
  warehouse: "Skladiščnik", admin: "Administrator",
};
const emptyForm: UserCreate = { name: "", email: "", password: "", role: "operator" };

export function Users({ currentUserId, onSelfDeactivated }: {
  currentUserId: number; onSelfDeactivated: () => void;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState<UserCreate>(emptyForm);
  const [fields, setFields] = useState<UserFields>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const busy = saving || pendingId !== null;

  async function load(signal?: AbortSignal) {
    setLoading(true);
    setLoadError("");
    try {
      const result = await listUsers(signal);
      if (!signal?.aborted) setUsers(result);
    } catch (error) {
      if (!signal?.aborted) setLoadError(error instanceof Error ? error.message : "Seznama ni mogoče naložiti.");
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
    if (busy || loading) return;
    setError("");
    setMessage("");
    const errors: UserFields = {};
    if (!form.name.trim()) errors.name = "Vnesi ime.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) errors.email = "Vnesi veljavno e-pošto.";
    if (form.password.length < 8) errors.password = "Geslo mora imeti najmanj 8 znakov.";
    else if (new TextEncoder().encode(form.password).length > 72) errors.password = "Geslo ne sme presegati 72 UTF-8 bajtov.";
    setFields(errors);
    if (Object.keys(errors).length) return;
    setSaving(true);
    try {
      const created = await createUser({ ...form, name: form.name.trim(), email: form.email.trim() });
      setUsers(current => [...current, created].sort((a, b) => a.id - b.id));
      setForm(emptyForm);
      setMessage("Uporabnik je ustvarjen.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Uporabnika ni mogoče ustvariti.");
      if (error instanceof UserApiError) setFields(error.fields);
      setForm(current => ({ ...current, password: "" }));
    } finally {
      setSaving(false);
    }
  }

  async function deactivate(user: User) {
    if (busy) return;
    const question = user.id === currentUserId
      ? "Deaktiviraš svoj račun? S tem boš odjavljen iz aplikacije."
      : `Deaktiviraš uporabnika ${user.name} (${user.email})?`;
    if (!window.confirm(question)) return;
    setError("");
    setMessage("");
    setPendingId(user.id);
    try {
      const updated = await deactivateUser(user.id);
      setUsers(current => current.map(item => item.id === updated.id ? updated : item));
      if (updated.id === currentUserId) onSelfDeactivated();
      else setMessage("Uporabnik je deaktiviran.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Deaktivacija ni uspela.");
    } finally {
      setPendingId(null);
    }
  }

  function fieldError(field: keyof UserCreate) {
    return fields[field] ? <small id={`user-${field}-error`} className="field-error" role="alert">{fields[field]}</small> : null;
  }

  return (
    <div className="users-content">
      {message && <p className="success" role="status">{message}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <section aria-labelledby="new-user-title">
        <h3 id="new-user-title">Nov uporabnik</h3>
        <form onSubmit={submit}>
          <fieldset disabled={busy || loading}>
            <label htmlFor="user-name">Ime</label>
            <input id="user-name" name="name" autoComplete="off" required maxLength={120}
              value={form.name} onChange={event => setForm({ ...form, name: event.target.value })}
              aria-invalid={Boolean(fields.name)} aria-describedby={fields.name ? "user-name-error" : undefined} />
            {fieldError("name")}
            <label htmlFor="user-email">E-pošta</label>
            <input id="user-email" name="email" type="email" autoComplete="off" required maxLength={255}
              value={form.email} onChange={event => setForm({ ...form, email: event.target.value })}
              aria-invalid={Boolean(fields.email)} aria-describedby={fields.email ? "user-email-error" : undefined} />
            {fieldError("email")}
            <label htmlFor="user-password">Začetno geslo</label>
            <input id="user-password" name="password" type="password" autoComplete="new-password" required minLength={8}
              value={form.password} onChange={event => setForm({ ...form, password: event.target.value })}
              aria-invalid={Boolean(fields.password)} aria-describedby={fields.password ? "user-password-help user-password-error" : "user-password-help"} />
            <small id="user-password-help" className="muted">Najmanj 8 znakov in največ 72 UTF-8 bajtov.</small>
            {fieldError("password")}
            <label htmlFor="user-role">Vloga</label>
            <select id="user-role" name="role" value={form.role}
              onChange={event => setForm({ ...form, role: event.target.value as Role })}
              aria-invalid={Boolean(fields.role)} aria-describedby={fields.role ? "user-role-error" : undefined}>
              {Object.entries(roleLabels).map(([role, label]) => <option key={role} value={role}>{label}</option>)}
            </select>
            {fieldError("role")}
            <button type="submit">{saving ? "Ustvarjanje …" : "Ustvari uporabnika"}</button>
          </fieldset>
        </form>
      </section>
      <section aria-labelledby="users-list-title">
        <div className="workspace-header">
          <h3 id="users-list-title">Seznam uporabnikov</h3>
          <button className="secondary" disabled={loading || busy} onClick={() => void load()}>Osveži seznam</button>
        </div>
        {loadError && <p className="error" role="alert">{loadError}</p>}
        {loading ? <p role="status">Nalaganje uporabnikov …</p> : !loadError && users.length === 0 ? <p>Ni uporabnikov za prikaz.</p> : null}
        {!loading && users.length > 0 && (
          <div className="table-scroll">
            <table>
              <caption className="sr-only">Uporabniki, njihove vloge in stanje računa</caption>
              <thead><tr><th scope="col">Ime</th><th scope="col">E-pošta</th><th scope="col">Vloga</th><th scope="col">Stanje</th><th scope="col">Akcija</th></tr></thead>
              <tbody>{users.map(user => (
                <tr key={user.id}>
                  <td>{user.name}{user.id === currentUserId ? " (vi)" : ""}</td>
                  <td>{user.email}</td><td>{roleLabels[user.role]}</td>
                  <td>{user.active ? "Aktiven" : "Neaktiven"}</td>
                  <td>{user.active ? <button className="danger" disabled={busy} onClick={() => void deactivate(user)}>
                    {pendingId === user.id ? "Deaktiviranje …" : "Deaktiviraj"}
                  </button> : "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
