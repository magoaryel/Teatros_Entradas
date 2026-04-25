"use client";
import { useState } from "react";

export default function Config() {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "fail" | null>(null);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    const res = await fetch("/api/telegram/test", { method: "POST" });
    const data = await res.json();
    setTestResult(data.ok ? "ok" : "fail");
    setTesting(false);
  }

  return (
    <div className="container">
      <div style={{ maxWidth: 560 }}>
        <h1>⚙ Configuración</h1>

        <div className="card">
          <h2>Telegram</h2>
          <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>
            Las notificaciones se configuran como variables de entorno en Vercel.
            No se guardan en código.
          </p>

          <div
            style={{
              background: "#111118", borderRadius: 8,
              padding: "14px 16px", fontSize: 13, marginBottom: 16,
            }}
          >
            <div style={{ color: "var(--muted)", marginBottom: 8, fontSize: 12, fontWeight: 600 }}>
              Variables a configurar en Vercel → Settings → Environment Variables:
            </div>
            {[
              ["TELEGRAM_TOKEN", "Token de tu bot (de @BotFather)"],
              ["TELEGRAM_CHAT_ID", "Tu ID de Telegram (de @userinfobot)"],
              ["CRON_SECRET", "Cualquier string secreto para el cron"],
              ["DATABASE_URL", "Connection string de Neon"],
            ].map(([key, desc]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <code
                  style={{
                    background: "#1a1a24", padding: "2px 8px",
                    borderRadius: 4, color: "#c4b5fd", fontSize: 12,
                  }}
                >
                  {key}
                </code>
                <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: 12 }}>{desc}</span>
              </div>
            ))}
          </div>

          <button
            className="btn btn-ghost"
            onClick={handleTest}
            disabled={testing}
            style={{ marginTop: 8 }}
          >
            {testing ? "Enviando..." : "📨 Enviar mensaje de prueba"}
          </button>

          {testResult === "ok" && (
            <div style={{ marginTop: 10, color: "var(--green)", fontSize: 13 }}>
              ✅ Telegram configurado correctamente
            </div>
          )}
          {testResult === "fail" && (
            <div style={{ marginTop: 10, color: "#fca5a5", fontSize: 13 }}>
              ❌ Error — revisa TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en Vercel
            </div>
          )}
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <h2>Cómo configurar Telegram</h2>
          <ol style={{ fontSize: 13, color: "var(--muted)", paddingLeft: 20, lineHeight: 2.3 }}>
            <li>
              Abre Telegram, busca{" "}
              <a href="https://t.me/BotFather" target="_blank" style={{ color: "var(--accent)" }}>
                @BotFather
              </a>{" "}
              y escribe <code style={{ background: "#111118", padding: "1px 6px", borderRadius: 4 }}>/newbot</code>
            </li>
            <li>Copia el token que te da y ponlo en <b>TELEGRAM_TOKEN</b></li>
            <li>
              Busca{" "}
              <a href="https://t.me/userinfobot" target="_blank" style={{ color: "var(--accent)" }}>
                @userinfobot
              </a>{" "}
              — te dirá tu ID numérico
            </li>
            <li>Ponlo en <b>TELEGRAM_CHAT_ID</b></li>
            <li>Empieza una conversación con tu bot (envíale /start)</li>
          </ol>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <h2>Cron automático</h2>
          <p style={{ fontSize: 13, color: "var(--muted)" }}>
            Vercel ejecuta automáticamente{" "}
            <code style={{ background: "#111118", padding: "1px 6px", borderRadius: 4 }}>
              /api/cron/scrape
            </code>{" "}
            cada 30 minutos y envía notificaciones si hay nuevas ventas.
            Esto está configurado en <code style={{ background: "#111118", padding: "1px 6px", borderRadius: 4 }}>vercel.json</code>.
          </p>
        </div>
      </div>
    </div>
  );
}
