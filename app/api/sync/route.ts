import { NextResponse } from "next/server";
import { discoverShows } from "@/lib/syncShows";
import { addEvent, getEvents, initDb } from "@/lib/db";
import { detectPlatform } from "@/lib/scraper";
import { neon } from "@neondatabase/serverless";

async function upsertShow(name: string, venue: string, pageUrl: string, ticketUrl: string | null) {
  const db = neon(process.env.DATABASE_URL!);
  // Check if already exists by page_url
  const existing = await db`SELECT id FROM events WHERE page_url = ${pageUrl} LIMIT 1`;
  if (existing.length > 0) {
    // Update ticket URL if it changed
    if (ticketUrl) {
      await db`UPDATE events SET url = ${ticketUrl}, venue = ${venue}, has_tickets = true WHERE page_url = ${pageUrl}`;
    }
    return existing[0].id as number;
  }
  // Insert new
  const rows = await db`
    INSERT INTO events (name, venue, url, platform, page_url, has_tickets)
    VALUES (${name}, ${venue || "Spain"}, ${ticketUrl ?? pageUrl}, ${ticketUrl ? detectPlatform(ticketUrl) : "none"}, ${pageUrl}, ${!!ticketUrl})
    RETURNING id
  `;
  return rows[0].id as number;
}

export async function POST() {
  await initDb();

  // Ensure new columns exist
  const db = neon(process.env.DATABASE_URL!);
  await db`ALTER TABLE events ADD COLUMN IF NOT EXISTS page_url TEXT`;
  await db`ALTER TABLE events ADD COLUMN IF NOT EXISTS has_tickets BOOLEAN DEFAULT false`;

  const shows = await discoverShows();
  const results = [];

  for (const show of shows) {
    try {
      const id = await upsertShow(show.name, show.venue || show.city, show.pageUrl, show.ticketUrl);
      results.push({ id, name: show.name, hasTickets: !!show.ticketUrl });
    } catch (e) {
      results.push({ name: show.name, error: String(e) });
    }
  }

  return NextResponse.json({ synced: results.length, shows: results });
}
