"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function AddEvent() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(e.currentTarget);
    const body = { name: form.get("name"), venue: form.get("venue"), url: form.get("url") };
    const res = await fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json();
      setError(data.error ?? "Error al añadir el evento.");
      setLoading(false);
      return;
    }
    const { id } = await res.json();
    await fetch(`/api/scrape/${id}`, { method: "POST" });
    router.push("/");
  }

  return (
    <div className="container">
      <div style={{ maxWidth: 560 }}>
        <div className="gold-line" />
        <h1>Añadir evento</h1>

        {error && (
          <div style={{
            background: "rgba(229,62,62,0.1)", color: "#fc8181",
            border: "1px solid rgba(229,62,62,0.25)",
            borderRadius: 4, padding: "12px 16px", marginBottom: 20, fontSize: 13,
          }}>
            {error}
          </div>
        )}

        <div className="card">
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Nombre del show</label>
              <input type="text" name="name" placeholder="El Mentalista — Aryel Altamar" required />
            </div>
            <div className="form-group">
              <label>Teatro / Venue</label>
              <input type="text" name="venue" placeholder="Teatro Fígaro, Madrid" required />
            </div>
            <div className="form-group">
              <label>URL de compra</label>
              <input
                type="url" name="url"
                placeholder="https://entradas.gruposmedia.com/entradas/comprarEvento?idEvento=..."
                required
              />
              <div className="hint">Pega la URL completa de la página del evento</div>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 28 }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "Añadiendo..." : "Añadir evento"}
              </button>
              <a href="/" className="btn btn-ghost">Cancelar</a>
            </div>
          </form>
        </div>

        <div className="card" style={{ marginTop: 14 }}>
          <h2>Plataformas compatibles</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { name: "entradas.gruposmedia.com", ok: true },
              { name: "entradas.plus", ok: true },
              { name: "Otras plataformas", ok: false, note: "se pueden añadir" },
            ].map((p) => (
              <div key={p.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ color: p.ok ? "var(--green)" : "var(--yellow)", fontSize: 12, fontWeight: 700 }}>
                  {p.ok ? "✓" : "→"}
                </span>
                <span style={{ fontSize: 13, color: p.ok ? "var(--text)" : "var(--muted)" }}>{p.name}</span>
                {p.note && <span style={{ fontSize: 11, color: "#555" }}>({p.note})</span>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
