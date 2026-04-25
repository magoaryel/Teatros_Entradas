import { NextRequest, NextResponse } from "next/server";
import { getActiveEvents, upsertSession, saveSnapshot, getLatestSnapshot } from "@/lib/db";
import { notifySales, notifySoldOut } from "@/lib/telegram";

// GitHub Actions posts scraped data here
// Body: { secret, results: [{ eventId, sessions: [{ session_id, label, date, capacity, sold, reserved }] }] }

export async function POST(req: NextRequest) {
  const secret = req.headers.get("x-ingest-secret");
  if (!process.env.INGEST_SECRET || secret !== process.env.INGEST_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const results = body.results as Array<{
    eventId: number;
    eventName: string;
    eventVenue: string;
    sessions: Array<{
      session_id: string;
      label: string;
      date: string;
      capacity: number;
      sold: number;
      reserved: number;
    }>;
  }>;

  const saved = [];
  for (const r of results) {
    for (const s of r.sessions) {
      const sessionDbId = await upsertSession(r.eventId, s.session_id, s.label, s.date, s.capacity);
      const prev = await getLatestSnapshot(sessionDbId);
      const soldBefore = prev ? (prev.sold as number) : 0;
      await saveSnapshot(sessionDbId, s.sold, s.reserved, s.capacity);

      if (s.sold > soldBefore) {
        if (s.capacity - s.sold <= 0) {
          await notifySoldOut(r.eventName, r.eventVenue, s.label);
        } else {
          await notifySales(r.eventName, r.eventVenue, s.label, s.sold, soldBefore, s.capacity);
        }
      }
      saved.push({ event: r.eventName, session: s.label, sold: s.sold });
    }
  }

  return NextResponse.json({ ok: true, saved: saved.length });
}

// Also expose active events so the GitHub Action knows what to scrape
export async function GET(req: NextRequest) {
  const secret = req.headers.get("x-ingest-secret");
  if (!process.env.INGEST_SECRET || secret !== process.env.INGEST_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const events = await getActiveEvents();
  return NextResponse.json(events);
}
