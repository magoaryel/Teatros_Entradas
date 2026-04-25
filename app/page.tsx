import { getEvents, getEventSessions, initDb, type Event, type Session } from "@/lib/db";
import RefreshButton from "./components/RefreshButton";
import DeleteButton from "./components/DeleteButton";
import ToggleButton from "./components/ToggleButton";
import ScrapeButton from "./components/ScrapeButton";

export const dynamic = "force-dynamic";

function formatDate(raw: string): string {
  if (!raw) return "—";
  // raw may be "2026-05-10T12:30" or "2026-05-10"
  try {
    const date = new Date(raw.length <= 10 ? raw + "T00:00" : raw);
    return date.toLocaleDateString("es-ES", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
    }) + (raw.includes("T") ? " · " + raw.slice(11, 16) + "h" : "");
  } catch {
    return raw;
  }
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default async function Dashboard() {
  let events: Event[] = [];
  let dbError = false;

  try {
    await initDb();
    events = await getEvents();
  } catch {
    dbError = true;
  }

  if (dbError) {
    return (
      <div className="container">
        <div className="card" style={{ textAlign: "center", padding: "56px" }}>
          <div style={{ fontSize: 40, marginBottom: 16, color: "var(--gold)" }}>⚠</div>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
            Base de datos no configurada
          </div>
          <p style={{ color: "var(--muted)", margin: "8px 0 24px", fontSize: 13 }}>
            Añade la variable <code>DATABASE_URL</code> en Vercel → Settings → Environment Variables
          </p>
          <a href="https://neon.tech" target="_blank" className="btn btn-primary">
            Crear base de datos gratis →
          </a>
        </div>
      </div>
    );
  }

  const eventData: (Event & { sessions: Session[] })[] = await Promise.all(
    events.map(async (ev) => ({
      ...ev,
      sessions: await getEventSessions(ev.id),
    }))
  );

  return (
    <div className="container">
      {/* Header */}
      <div className="row" style={{ marginBottom: 32, justifyContent: "space-between" }}>
        <div>
          <div className="gold-line" />
          <h1 style={{ margin: 0 }}>Dashboard</h1>
        </div>
        <div className="actions">
          <RefreshButton />
          <a href="/add" className="btn btn-primary">+ Añadir evento</a>
        </div>
      </div>

      {eventData.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "64px 32px" }}>
          <div style={{ color: "var(--gold)", fontSize: 36, marginBottom: 20 }}>🎭</div>
          <div style={{ fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
            Sin eventos
          </div>
          <p style={{ color: "var(--muted)", fontSize: 13, margin: "8px 0 28px" }}>
            Añade tu primer teatro para empezar a monitorizar ventas.
          </p>
          <a href="/add" className="btn btn-primary">+ Añadir evento</a>
        </div>
      )}

      {eventData.map((event) => {
        const totalSold = event.sessions.reduce((s, sess) => s + (sess.sold ?? 0), 0);
        const totalCap  = event.sessions.reduce((s, sess) => s + (sess.total_capacity ?? 0), 0);

        return (
          <div className="card" key={event.id} style={{ opacity: event.active ? 1 : 0.5 }}>

            {/* Event header */}
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  {event.name}
                </div>
                <div style={{ color: "var(--gold)", fontSize: 12, fontWeight: 600, marginTop: 4, letterSpacing: "0.06em" }}>
                  📍 {event.venue}
                </div>
                <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <span className={`badge ${event.active ? "badge-green" : "badge-gray"}`}>
                    {event.active ? "Activo" : "Pausado"}
                  </span>
                  {totalCap > 0 && (
                    <span className="badge badge-gold">
                      {totalSold} vendidas en total
                    </span>
                  )}
                </div>
              </div>
              <div className="actions">
                <ScrapeButton eventId={event.id} />
                <ToggleButton eventId={event.id} active={event.active} />
                <DeleteButton eventId={event.id} />
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <a href={event.url} target="_blank"
                style={{ color: "var(--muted)", fontSize: 11, letterSpacing: "0.04em" }}>
                ↗ Ver en web del teatro
              </a>
            </div>

            <div className="divider" />

            {/* Sessions */}
            {event.sessions.length === 0 ? (
              <div style={{ color: "#555", fontSize: 12, padding: "8px 0", letterSpacing: "0.04em" }}>
                Sin datos — pulsa 🔄 para cargar
              </div>
            ) : (
              event.sessions.map((sess, idx) => {
                const sold  = sess.sold ?? 0;
                const cap   = sess.total_capacity ?? 0;
                const avail = sess.available ?? Math.max(0, cap - sold);
                const pct   = cap > 0 ? Math.round((sold / cap) * 100) : 0;

                return (
                  <div key={sess.id}
                    style={{
                      padding: "14px 0",
                      borderBottom: idx < event.sessions.length - 1 ? "1px solid #2a2a2a" : "none",
                    }}
                  >
                    {/* Date label */}
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--gold)", marginBottom: 8 }}>
                      {capitalize(formatDate(sess.session_label || sess.session_date))}
                    </div>

                    {sess.last_check ? (
                      <>
                        {/* Stats row */}
                        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                          <div style={{ display: "flex", gap: 24 }}>
                            <div>
                              <div style={{ fontSize: 24, fontWeight: 800, color: "var(--yellow)" }}>{sold}</div>
                              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Vendidas</div>
                            </div>
                            <div>
                              <div style={{ fontSize: 24, fontWeight: 800, color: "var(--green)" }}>{avail}</div>
                              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Disponibles</div>
                            </div>
                            <div>
                              <div style={{ fontSize: 24, fontWeight: 800, color: "#555" }}>{cap}</div>
                              <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Aforo</div>
                            </div>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            {avail === 0 ? (
                              <span className="badge badge-red">Agotado</span>
                            ) : pct >= 80 ? (
                              <span className="badge badge-yellow">{pct}% vendido</span>
                            ) : (
                              <span style={{ fontSize: 28, fontWeight: 800, color: "#444" }}>{pct}%</span>
                            )}
                          </div>
                        </div>

                        {/* Progress */}
                        <div className="progress" style={{ marginTop: 12 }}>
                          <div className="progress-fill" style={{
                            width: `${pct}%`,
                            background: pct >= 90
                              ? "var(--red)"
                              : pct >= 70
                              ? "var(--yellow)"
                              : "var(--gold)",
                          }} />
                        </div>
                        <div style={{ fontSize: 11, color: "#444", letterSpacing: "0.02em" }}>
                          Actualizado{" "}
                          {new Date(sess.last_check).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" })}
                        </div>
                      </>
                    ) : (
                      <div style={{ color: "#444", fontSize: 12 }}>Sin datos aún</div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        );
      })}
    </div>
  );
}
