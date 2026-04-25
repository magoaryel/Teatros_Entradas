import { NextResponse } from "next/server";
import { discoverShows } from "@/lib/syncShows";
import { initDb } from "@/lib/db";
import { detectPlatform } from "@/lib/scraper";
import { neon } from "@neondatabase/serverless";

async function upsertShow(
  name: string, venue: string, pageUrl: string,
  ticketUrl: string | null, isoDate: string
) {
  const db = neon(process.env.DATABASE_URL!);

  // Deduplicate by ticket URL first
  if (ticketUrl) {
    const byTicket = await db`SELECT id FROM events WHERE url = ${ticketUrl} LIMIT 1`;
    if (byTicket.length > 0) {
      await db`
        UPDATE events SET page_url = ${pageUrl}, venue = ${venue}, has_tickets = true,
        show_date = COALESCE(show_date, ${isoDate || null})
        WHERE id = ${byTicket[0].id}
      `;
      return byTicket[0].id as number;
    }
  }

  // Then by page_url
  const byPage = await db`SELECT id FROM events WHERE page_url = ${pageUrl} LIMIT 1`;
  if (byPage.length > 0) {
    await db`
      UPDATE events SET
        url = COALESCE(NULLIF(${ticketUrl ?? ""}, ""), url),
        has_tickets = CASE WHEN ${!!ticketUrl} THEN true ELSE has_tickets END,
        show_date = COALESCE(show_date, ${isoDate || null}),
        venue = ${venue}
      WHERE id = ${byPage[0].id}
    `;
    return byPage[0].id as number;
  }

  const platform = ticketUrl ? detectPlatform(ticketUrl) : "manual";
  const rows = await db`
    INSERT INTO events (name, venue, url, platform, page_url, has_tickets, show_date)
    VALUES (
      ${name}, ${venue || "España"},
      ${ticketUrl ?? pageUrl}, ${platform},
      ${pageUrl}, ${!!ticketUrl}, ${isoDate || null}
    )
    RETURNING id
  `;
  return rows[0].id as number;
}

export async function POST() {
  await initDb();

  const shows = await discoverShows();
  const results = [];

  for (const show of shows) {
    try {
      const id = await upsertShow(
        show.name, show.venue || show.city,
        show.pageUrl, show.ticketUrl, show.isoDate
      );
      results.push({ id, name: show.name, hasTickets: !!show.ticketUrl });
    } catch (e) {
      results.push({ name: show.name, error: String(e) });
    }
  }

  return NextResponse.json({ synced: results.length, shows: results });
}
