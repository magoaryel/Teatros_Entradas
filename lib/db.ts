import { neon } from "@neondatabase/serverless";

export interface Event {
  id: number;
  name: string;
  venue: string;
  url: string;
  platform: string;
  active: boolean;
  page_url: string | null;
  has_tickets: boolean;
  show_date: string | null;
  created_at: string;
}

export interface Session {
  id: number;
  event_id: number;
  session_id: string;
  session_label: string;
  session_date: string;
  total_capacity: number;
  sold: number | null;
  reserved: number | null;
  available: number | null;
  last_check: string | null;
  sold_baseline: number | null;  // sold count from first snapshot — subtract to get real sales
}

export interface Snapshot {
  id: number;
  session_id: number;
  sold: number;
  reserved: number;
  available: number;
  captured_at: string;
}

function sql() {
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL not set");
  return neon(process.env.DATABASE_URL);
}

export async function initDb() {
  const db = sql();
  await db`
    CREATE TABLE IF NOT EXISTS events (
      id SERIAL PRIMARY KEY,
      name TEXT NOT NULL,
      venue TEXT NOT NULL,
      url TEXT NOT NULL,
      platform TEXT DEFAULT 'gruposmedia',
      active BOOLEAN DEFAULT true,
      page_url TEXT,
      has_tickets BOOLEAN DEFAULT false,
      created_at TIMESTAMPTZ DEFAULT NOW()
    )
  `;
  await db`ALTER TABLE events ADD COLUMN IF NOT EXISTS page_url TEXT`;
  await db`ALTER TABLE events ADD COLUMN IF NOT EXISTS has_tickets BOOLEAN DEFAULT false`;
  await db`ALTER TABLE events ADD COLUMN IF NOT EXISTS show_date TEXT`;
  await db`
    CREATE TABLE IF NOT EXISTS sessions (
      id SERIAL PRIMARY KEY,
      event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
      session_id TEXT NOT NULL,
      session_label TEXT,
      session_date TEXT,
      total_capacity INTEGER DEFAULT 0,
      UNIQUE(event_id, session_id)
    )
  `;
  await db`
    CREATE TABLE IF NOT EXISTS snapshots (
      id SERIAL PRIMARY KEY,
      session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
      sold INTEGER DEFAULT 0,
      reserved INTEGER DEFAULT 0,
      available INTEGER DEFAULT 0,
      captured_at TIMESTAMPTZ DEFAULT NOW()
    )
  `;
}

export async function getEvents(): Promise<Event[]> {
  const db = sql();
  // Sort by nearest upcoming session date, then by show_date, then by created_at
  return db`
    SELECT e.*,
      COALESCE(
        (SELECT MIN(s.session_date) FROM sessions s WHERE s.event_id = e.id AND s.session_date >= to_char(NOW(), 'YYYY-MM-DD')),
        e.show_date
      ) AS next_date
    FROM events e
    ORDER BY next_date ASC NULLS LAST, e.created_at ASC
  ` as unknown as Promise<Event[]>;
}

export async function getActiveEvents(): Promise<Event[]> {
  const db = sql();
  return db`SELECT * FROM events WHERE active = true` as unknown as Promise<Event[]>;
}

export async function addEvent(
  name: string, venue: string, url: string, platform: string
) {
  const db = sql();
  const rows = await db`
    INSERT INTO events (name, venue, url, platform)
    VALUES (${name}, ${venue}, ${url}, ${platform})
    RETURNING id
  `;
  return rows[0].id as number;
}

export async function toggleEvent(id: number) {
  const db = sql();
  await db`UPDATE events SET active = NOT active WHERE id = ${id}`;
}

export async function deleteEvent(id: number) {
  const db = sql();
  await db`DELETE FROM events WHERE id = ${id}`;
}

export async function deleteStaleSessionsForEvent(eventId: number, keepSessionIds: string[]) {
  const db = sql();
  if (keepSessionIds.length === 0) return;
  const existing = await db`SELECT id, session_id FROM sessions WHERE event_id = ${eventId}` as { id: number; session_id: string }[];
  for (const row of existing) {
    if (!keepSessionIds.includes(row.session_id)) {
      await db`DELETE FROM sessions WHERE id = ${row.id}`;
    }
  }
}

export async function upsertSession(
  eventId: number, sessionId: string, label: string,
  date: string, capacity: number
) {
  const db = sql();
  const rows = await db`
    INSERT INTO sessions (event_id, session_id, session_label, session_date, total_capacity)
    VALUES (${eventId}, ${sessionId}, ${label}, ${date}, ${capacity})
    ON CONFLICT (event_id, session_id)
    DO UPDATE SET session_label    = EXCLUDED.session_label,
                  session_date     = EXCLUDED.session_date,
                  total_capacity   = EXCLUDED.total_capacity
    RETURNING id
  `;
  return rows[0].id as number;
}

export async function saveSnapshot(
  sessionId: number, sold: number, reserved: number, capacity: number
) {
  const db = sql();
  const available = Math.max(0, capacity - sold - reserved);
  await db`
    INSERT INTO snapshots (session_id, sold, reserved, available)
    VALUES (${sessionId}, ${sold}, ${reserved}, ${available})
  `;
}

export async function getLatestSnapshot(sessionId: number) {
  const db = sql();
  const rows = await db`
    SELECT * FROM snapshots WHERE session_id = ${sessionId}
    ORDER BY captured_at DESC LIMIT 1
  `;
  return rows[0] ?? null;
}

export async function getEventSessions(eventId: number): Promise<Session[]> {
  const db = sql();
  return db`
    SELECT s.*,
      snap.sold, snap.reserved, snap.available, snap.captured_at AS last_check,
      COALESCE((
        SELECT sold FROM snapshots WHERE session_id = s.id ORDER BY captured_at ASC LIMIT 1
      ), 0) AS sold_baseline
    FROM sessions s
    LEFT JOIN LATERAL (
      SELECT sold, reserved, available, captured_at
      FROM snapshots WHERE session_id = s.id ORDER BY captured_at DESC LIMIT 1
    ) snap ON true
    WHERE s.event_id = ${eventId}
      AND (s.session_date IS NULL OR s.session_date >= to_char(NOW(), 'YYYY-MM-DD'))
    ORDER BY s.session_date
  ` as unknown as Promise<Session[]>;
}

export async function getSessionHistory(sessionId: number): Promise<Snapshot[]> {
  const db = sql();
  return db`
    SELECT * FROM snapshots WHERE session_id = ${sessionId}
    ORDER BY captured_at DESC LIMIT 100
  ` as unknown as Promise<Snapshot[]>;
}
