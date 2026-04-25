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
    const body = {
      name: form.get("name"),
      venue: form.get("venue"),
      url: form.get("url"),
    };

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

    // Trigger first scrape
    await fetch(`/api/scrape/${id}`, { method: "POST" });

    router.push("/");
  }

  return (
    <div className="container">
      <div style={{ maxWidth: 560 }}>
        <h1>Añadir evento</h1>

        {error && (
          <div
            style={{
              background: "#7f1d1d", color: "#fca5a5", border: "1px solid #991b1b",
              borderRadius: 8, padding: "12px 16px", marginBottom: 20, fontSize: 14,
            }}
          >
            {error}
          </div>
        )}

        <div className="card">
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Nombre del show *</label>
              <input type="text" name="name" placeholder="El Mentalista — Aryel Altamar" required />
            </div>
            <div className="form-group">
              <label>Teatro / Venue *</label>
              <input type="text" name="venue" placeholder="Teatro Fígaro, Madrid" required />
            </div>
            <div className="form-group">
              <label>URL de compra de entradas *</label>
              <input
                type="url" name="url"
                placeholder="https://entradas.gruposmedia.com/entradas/comprarEvento?idEvento=..."
                required
              />
              <div className="hint">Pega la URL completa del evento en la web del teatro</div>
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "Añadiendo..." : "✓ Añadir evento"}
              </button>
              <a href="/" className="btn btn-ghost">Cancelar</a>
            </div>
          </form>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <h2>Plataformas compatibles</h2>
          <ul style={{ paddingLeft: 20, fontSize: 13, color: "var(--muted)", lineHeight: 2.2 }}>
            <li><span style={{ color: "var(--green)" }}>✓</span> <b>entradas.gruposmedia.com</b></li>
            <li><span style={{ color: "var(--green)" }}>✓</span> <b>entradas.plus</b></li>
            <li><span style={{ color: "var(--yellow)" }}>→</span> Otras plataformas: se pueden añadir</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
