import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { LoginResult } from "./api/auth";
import { clearToken, readToken, restoreSession, saveToken, unauthorizedEvent } from "./api/auth";
import { Login } from "./pages/Login";
import { RoleHome } from "./pages/RoleHome";
import "./style.css";

const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8001/api";

function App() {
  const [session, setSession] = useState<LoginResult | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState("");
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [notice, setNotice] = useState("");
  const [status, setStatus] = useState("Preverjanje povezave …");

  function logout(message = "Odjava je uspela.") {
    clearToken();
    setSession(null);
    setRestoreError("");
    setRestoring(false);
    setNotice(message);
  }

  function completeLogin(result: LoginResult) {
    saveToken(result.access_token);
    setNotice("");
    setSession(result);
  }

  useEffect(() => {
    const onUnauthorized = () => logout("Prijava je potekla ali ni veljavna. Prijavi se znova.");
    window.addEventListener(unauthorizedEvent, onUnauthorized);
    return () => window.removeEventListener(unauthorizedEvent, onUnauthorized);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = readToken();
    setRestoring(true);
    setRestoreError("");
    restoreSession()
      .then(result => {
        if (!cancelled && readToken() === token) setSession(result);
      })
      .catch(() => {
        if (!cancelled && readToken()) {
          setRestoreError("Povezava s strežnikom ni uspela. Prijave ni mogoče preveriti.");
        }
      })
      .finally(() => { if (!cancelled) setRestoring(false); });
    return () => { cancelled = true; };
  }, [restoreAttempt]);

  useEffect(() => {
    if (!session) return;
    const expire = () => logout("Prijava je potekla. Prijavi se znova.");
    const checkExpiry = () => {
      if (Date.now() >= session.expires_at * 1000) expire();
    };
    const timer = window.setTimeout(expire, Math.max(0, session.expires_at * 1000 - Date.now()));
    window.addEventListener("focus", checkExpiry);
    document.addEventListener("visibilitychange", checkExpiry);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("focus", checkExpiry);
      document.removeEventListener("visibilitychange", checkExpiry);
    };
  }, [session]);

  useEffect(() => {
    const controller = new AbortController();
    async function checkConnection() {
      try {
        const response = await fetch(`${apiUrl}/health`, { signal: controller.signal });
        if (!response.ok) throw new Error("Povezava ni uspela.");
        const result = await response.json();
        if (result.status !== "ok" || result.database !== "ok") {
          throw new Error("Storitve niso pripravljene.");
        }
        setStatus("Povezava z API in podatkovno bazo deluje.");
      } catch {
        if (!controller.signal.aborted) {
          setStatus("Povezava ni uspela. Preveri, ali sta API in podatkovna baza zagnana.");
        }
      }
    }
    void checkConnection();
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>Pijacai</h1>
      <p>Sistem za vodenje proizvodnih šarž.</p>
      {notice && <p role="status">{notice}</p>}
      {restoring ? <p role="status">Preverjanje prijave …</p> : restoreError ? (
        <section>
          <p className="error" role="alert">{restoreError}</p>
          <button onClick={() => setRestoreAttempt(attempt => attempt + 1)}>Poskusi znova</button>
          <button className="secondary" onClick={() => logout()}>Nazaj na prijavo</button>
        </section>
      ) : session ? (
        <>
          <RoleHome user={session.user} />
          <button className="secondary" onClick={() => logout()}>Odjava</button>
        </>
      ) : <Login onLogin={completeLogin} />}
      <footer><p role="status">{status}</p></footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
