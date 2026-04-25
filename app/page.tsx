import { getEvents, getEventSessions, initDb, type Event, type Session } from "@/lib/db";
import RefreshButton from "./components/RefreshButton";
import DeleteButton from "./components/DeleteButton";
import ToggleButton from "./components/ToggleButton";
import ScrapeButton from "./components/ScrapeButton";

export const dynamic = "force-dynamic";

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
        <div className="card" style={{ textAlign: "center", padding: "48px" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <h2>Base de datos no configurada</h2>
          <p style={{ color: "var(--muted)", margin: "12px 0 24px", fontSize: 14 }}>
            Configura la variable de entorno <code>DATABASE_URL</code> con tu
            base de datos Neon.
          </p>
          <a
            href="https://neon.tech"
            target="_blank"
            className="btn btn-primary"
          >
            Crear base de datos gratis en Neon →
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
      <div className="row" style={{ marginBottom: 24, justifyContent: "space-between" }}>
        <h1 style={{ margin: 0 }}>Dashboard</h1>
        <div className="actions">
          <RefreshButton />
          <a href="/add" className="btn btn-primary">+ Añadir evento</a>
        </div>
      </div>

      {eventData.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: "48px" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🎭</div>
          <h2>No hay eventos</h2>
          <p style={{ color: "var(--muted)", margin: "12px 0 24px", fontSize: 14 }}>
            Añade tu primer evento para empezar a monitorizar ventas.
          </p>
          <a href="/add" className="btn btn-primary">+ Añadir evento</a>
        </div>
      )}

      {eventData.map((event) => (
          <div className="card" key={event.id} style={{ opacity: event.active ? 1 : 0.55 }}>
            {/* Header */}
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 8, alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700 }}>{event.name}</div>
                <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 2 }}>
                  📍 {event.venue}
                </div>
                <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className={`badge ${event.active ? "badge-green" : "badge-gray"}`}>
                    {event.active ? "● Activo" : "● Pausado"}
                  </span>
                  <span className="badge badge-gray">{event.platform}</span>
                </div>
              </div>
              <div className="actions">
                <ScrapeButton eventId={event.id} />
                <ToggleButton eventId={event.id} active={event.active} />
                <DeleteButton eventId={event.id} />
              </div>
            </div>

            <a href={event.url} target="_blank" style={{ color: "var(--accent)", fontSize: 12 }}>
              🔗 Ver en web del teatro
            </a>

            {/* Sessions */}
            <div style={{ marginTop: 14 }}>
              {event.sessions.length === 0 ? (
                <div style={{ color: "#4b5563", fontSize: 13 }}>
                  Sin datos todavía — haz clic en 🔄 para actualizar.
                </div>
              ) : (
                event.sessions.map((sess) => {
                  const sold = sess.sold ?? 0;
                  const cap = sess.total_capacity ?? 0;
                  const avail = sess.available ?? Math.max(0, cap - sold);
                  const pct = cap > 0 ? Math.round((sold / cap) * 100) : 0;

                  return (
                    <div key={sess.id} style={{ padding: "10px 0", borderBottom: "1px solid #1f2937" }}>
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <div style={{ fontWeight: 600, fontSize: 13, color: "#c4b5fd" }}>
                          {sess.session_label}
                        </div>
                        <div style={{ fontSize: 13, color: "var(--muted)" }}>
                          {sess.last_check ? (
                            <>
                              <span style={{ color: "var(--yellow)", fontWeight: 700 }}>{sold}</span>
                              {" vendidas · "}
                              <span style={{ color: "var(--green)", fontWeight: 700 }}>{avail}</span>
                              {" libres · "}{cap} total{" "}
                              {avail === 0 ? (
                                <span className="badge badge-red">AGOTADO</span>
                              ) : pct >= 80 ? (
                                <span className="badge badge-yellow">{pct}%</span>
                              ) : (
                                <span style={{ color: "var(--muted)", fontSize: 12 }}>{pct}%</span>
                              )}
                            </>
                          ) : (
                            <span style={{ color: "#4b5563" }}>Sin datos</span>
                          )}
                        </div>
                      </div>

                      {sess.last_check && cap > 0 && (
                        <>
                          <div className="progress">
                            <div
                              className="progress-fill"
                              style={{
                                width: `${pct}%`,
                                background: pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--yellow)" : "var(--accent)",
                              }}
                            />
                          </div>
                          <div style={{ fontSize: 11, color: "#4b5563" }}>
                            Última actualización:{" "}
                            {new Date(sess.last_check).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" })}
                          </div>
                        </>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        ))}
    </div>
  );
}
