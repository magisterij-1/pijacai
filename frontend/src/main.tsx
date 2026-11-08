import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8001/api";

function App() {
  const [status, setStatus] = useState("Preverjanje povezave …");

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
      <p role="status">{status}</p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
