import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

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
