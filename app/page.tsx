import { getEvents, getEventSessions, initDb, type Event, type Session } from "@/lib/db";
import RefreshButton from "./components/RefreshButton";
import DeleteButton from "./components/DeleteButton";
import ToggleButton from "./components/ToggleButton";
import ScrapeButton from "./components/ScrapeButton";
import SyncButton from "./components/SyncButton";

export const dynamic = "force-dynamic";

function formatDate(raw: string): string {
  if (!raw) return "";
  // Only attempt JS Date parsing on ISO-format strings (YYYY-MM-DD...)
  // Non-ISO labels (e.g. "Sábado 16 mayo 19:00") are returned as-is
  if (!/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw;
  try {
    const date = new Date(raw.length <= 10 ? raw + "T00:00" : raw);
    const d = date.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    const t = raw.includes("T") ? " · " + raw.slice(11, 16) + "h" : "";
    return d.charAt(0).toUpperCase() + d.slice(1) + t;
  } catch { return raw; }
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
          <div style={{ fontSize: 36, color: "var(--gold)", marginBottom: 16 }}>⚠</div>
          <div style={{ fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
            Base de datos no configurada
          </div>
          <p style={{ color: "var(--muted)", fontSize: 13, margin: "8px 0 24px" }}>
            Añade <code>DATABASE_URL</code> en Vercel → Settings → Environment Variables
          </p>
          <a href="https://neon.tech" target="_blank" className="btn btn-primary">Crear DB gratis en Neon →</a>
        </div>
      </div>
    );
  }

  const withoutTickets = events.filter(e => !e.has_tickets);

  // All events with ticket URLs — load their sessions regardless of platform
  const allWithTickets: (Event & { sessions: Session[] })[] = await Promise.all(
    events
      .filter(e => e.has_tickets)
      .map(async ev => ({ ...ev, sessions: await getEventSessions(ev.id) }))
  );

  // If they have actual session data → show with full stats
  // If no data yet → show as "pending" with link to buy manually
  const eventData    = allWithTickets.filter(e => e.sessions.some(s => s.last_check));
  const pendingData  = allWithTickets.filter(e => !e.sessions.some(s => s.last_check));

  const isEmpty = events.length === 0;

  return (
    <div className="container">

      {/* Header */}
      <div className="row" style={{ marginBottom: 32, justifyContent: "space-between" }}>
        <div>
          <div className="gold-line" />
          <h1 style={{ margin: 0 }}>Monitor de Entradas</h1>
        </div>
        <div className="actions">
          <SyncButton />
          {allWithTickets.length > 0 && <RefreshButton />}
        </div>
      </div>

      {isEmpty && (
        <div className="card" style={{ textAlign: "center", padding: "64px 32px" }}>
          <div style={{ color: "var(--gold)", fontSize: 36, marginBottom: 20 }}>🎭</div>
          <div style={{ fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
            Sin shows cargados
          </div>
          <p style={{ color: "var(--muted)", fontSize: 13, margin: "8px 0 28px" }}>
            Pulsa "↻ Sync showsaryel.com" para descubrir todos tus shows automáticamente.
          </p>
          <SyncButton />
        </div>
      )}

      {/* Shows WITH tickets */}
      {eventData.length > 0 && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)" }}>
              Con entradas online
            </div>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>

          {eventData.map(event => {
            const totalSold = event.sessions.reduce((s, sess) => {
              const real = Math.max(0, (sess.sold ?? 0) - (sess.sold_baseline ?? 0));
              return s + real;
            }, 0);
            const totalCap  = event.sessions.reduce((s, sess) => s + (sess.total_capacity ?? 0), 0);

            return (
              <div className="card" key={event.id} style={{ opacity: event.active ? 1 : 0.5 }}>
                <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                  <div>
                    <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                      {event.name}
                    </div>
                    <div style={{ color: "var(--gold)", fontSize: 12, fontWeight: 600, marginTop: 4 }}>
                      📍 {event.venue}
                    </div>
                    <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <span className={`badge ${event.active ? "badge-green" : "badge-gray"}`}>
                        {event.active ? "Activo" : "Pausado"}
                      </span>
                      {totalCap > 0 && (
                        <span className="badge badge-gold">{totalSold} vendidas · {totalCap} aforo</span>
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
                  <a href={event.url} target="_blank" style={{ color: "var(--muted)", fontSize: 11 }}>
                    ↗ Ver entradas
                  </a>
                  {event.page_url && (
                    <> &nbsp;·&nbsp;
                      <a href={event.page_url} target="_blank" style={{ color: "var(--muted)", fontSize: 11 }}>
                        showsaryel.com
                      </a>
                    </>
                  )}
                </div>

                <div className="divider" />

                {event.sessions.length === 0 ? (
                  <div style={{ color: "#555", fontSize: 12, padding: "8px 0" }}>
                    Sin datos — pulsa 🔄 para cargar
                  </div>
                ) : (
                  event.sessions.map((sess, idx) => {
                    const baseline = sess.sold_baseline ?? 0;
                    const sold  = Math.max(0, (sess.sold ?? 0) - baseline);
                    const cap   = sess.total_capacity ?? 0;
                    const reserved = sess.reserved ?? 0;
                    const avail = Math.max(0, cap - sold - reserved);
                    const pct   = cap > 0 ? Math.round((sold / cap) * 100) : 0;

                    return (
                      <div key={sess.id} style={{
                        padding: "14px 0",
                        borderBottom: idx < event.sessions.length - 1 ? "1px solid #2a2a2a" : "none",
                      }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--gold)", marginBottom: 8 }}>
                          {formatDate(sess.session_label || sess.session_date)}
                        </div>

                        {sess.last_check ? (
                          <>
                            <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                              <div style={{ display: "flex", gap: 24 }}>
                                {[
                                  { label: "Vendidas", value: sold, color: "var(--yellow)" },
                                  { label: "Disponibles", value: avail, color: "var(--green)" },
                                  { label: "Aforo", value: cap, color: "#555" },
                                ].map(s => (
                                  <div key={s.label}>
                                    <div style={{ fontSize: 24, fontWeight: 800, color: s.color }}>{s.value}</div>
                                    <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>{s.label}</div>
                                  </div>
                                ))}
                              </div>
                              <div>
                                {avail === 0 ? (
                                  <span className="badge badge-red">Agotado</span>
                                ) : pct >= 80 ? (
                                  <span className="badge badge-yellow">{pct}% vendido</span>
                                ) : (
                                  <span style={{ fontSize: 26, fontWeight: 800, color: "#444" }}>{pct}%</span>
                                )}
                              </div>
                            </div>
                            <div className="progress" style={{ marginTop: 12 }}>
                              <div className="progress-fill" style={{
                                width: `${pct}%`,
                                background: pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--yellow)" : "var(--gold)",
                              }} />
                            </div>
                            <div style={{ fontSize: 11, color: "#444" }}>
                              Actualizado {new Date(sess.last_check).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" })}
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
        </>
      )}

      {/* Shows with tickets but no data yet — waiting for GitHub Actions scrape */}
      {pendingData.length > 0 && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "28px 0 16px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)" }}>
              Entradas online — actualizando cada 10 min
            </div>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {pendingData.map(event => (
              <div key={event.id} className="card" style={{ padding: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                  {event.name}
                </div>
                {event.venue && (
                  <div style={{ fontSize: 12, color: "var(--gold)", marginBottom: 10 }}>📍 {event.venue}</div>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                  <span className="badge badge-yellow">{event.platform}</span>
                  <div style={{ display: "flex", gap: 4 }}>
                    <a href={event.url} target="_blank" className="btn btn-ghost btn-sm">Ver →</a>
                    {event.page_url && <a href={event.page_url} target="_blank" className="btn btn-ghost btn-sm">showsaryel.com</a>}
                    <DeleteButton eventId={event.id} />
                  </div>
                </div>
                <div style={{ fontSize: 11, color: "#444", marginTop: 8 }}>
                  Sin datos aún — el scraper automático actualizará en breve
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Shows WITHOUT tickets */}
      {withoutTickets.length > 0 && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "28px 0 16px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)" }}>
              Sin entradas online aún
            </div>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {withoutTickets.map(event => (
              <div key={event.id} className="card" style={{ opacity: 0.6, padding: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                  {event.name}
                </div>
                {event.venue && (
                  <div style={{ fontSize: 12, color: "var(--gold)", marginBottom: 8 }}>📍 {event.venue}</div>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="badge badge-gray">Sin entradas online</span>
                  <div style={{ display: "flex", gap: 4 }}>
                    {event.page_url && (
                      <a href={event.page_url} target="_blank" className="btn btn-ghost btn-sm">Ver</a>
                    )}
                    <DeleteButton eventId={event.id} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

    </div>
  );
}
