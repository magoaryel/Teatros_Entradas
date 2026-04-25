import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

// DELETE /api/debug?ids=6,7,10  — remove specific event IDs
export async function DELETE(req: NextRequest) {
  const ids = req.nextUrl.searchParams.get("ids")?.split(",").map(Number).filter(Boolean);
  if (!ids?.length) return NextResponse.json({ error: "No ids" }, { status: 400 });
  const db = neon(process.env.DATABASE_URL!);
  await db`DELETE FROM snapshots WHERE session_id IN (SELECT id FROM sessions WHERE event_id = ANY(${ids}))`;
  await db`DELETE FROM sessions WHERE event_id = ANY(${ids})`;
  await db`DELETE FROM events WHERE id = ANY(${ids})`;
  return NextResponse.json({ deleted: ids });
}

// Visit /api/debug in browser to see DB state and config
export async function GET() {
  const db = neon(process.env.DATABASE_URL!);

  const events = await db`
    SELECT id, name, venue, platform, has_tickets, active, show_date,
           LEFT(url, 80) as url_preview
    FROM events ORDER BY created_at DESC
  `;

  return NextResponse.json({
    ingest_secret_set: !!process.env.INGEST_SECRET,
    telegram_set: !!process.env.TELEGRAM_TOKEN,
    total_events: events.length,
    events,
  }, { status: 200 });
}
