// — prijavni obrazec in napake prijave.
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { login } from "../api/auth";
import type { LoginResult } from "../api/auth";

export function Login({ onLogin }: { onLogin: (result: LoginResult) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const passwordInput = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError("");
    try {
      const result = await login(email, password);
      setPassword("");
      onLogin(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Prijava ni uspela.");
      setPassword("");
      passwordInput.current?.focus();
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="login-title">
      <h2 id="login-title">Prijava</h2>
      <p className="muted">Za nadaljevanje vnesi službeno e-pošto in geslo.</p>
      <form onSubmit={submit} aria-busy={pending}>
        <label htmlFor="email">E-pošta</label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          maxLength={255}
          value={email}
          onChange={event => setEmail(event.target.value)}
          required
          readOnly={pending}
        />
        <label htmlFor="password">Geslo</label>
        <input
          ref={passwordInput}
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={event => setPassword(event.target.value)}
          required
          readOnly={pending}
          aria-describedby={error ? "login-error" : undefined}
        />
        {error && <p id="login-error" className="error" role="alert">{error}</p>}
        <button type="submit" disabled={pending}>
          {pending ? "Prijavljanje …" : "Prijava"}
        </button>
      </form>
    </section>
  );
}
