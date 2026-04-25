import { NextRequest, NextResponse } from "next/server";
import { getActiveEvents } from "@/lib/db";
import { runScrapeForEvent } from "@/lib/runScrape";

export async function GET(req: NextRequest) {
  const secret = req.headers.get("authorization")?.replace("Bearer ", "");
  if (process.env.CRON_SECRET && secret !== process.env.CRON_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const events = await getActiveEvents();
  const results = [];

  for (const event of events) {
    try {
      await runScrapeForEvent({
        id: event.id as number,
        name: event.name as string,
        venue: event.venue as string,
        url: event.url as string,
        platform: event.platform as string,
      });
      results.push({ id: event.id, status: "ok" });
    } catch (err) {
      results.push({ id: event.id, status: "error", error: String(err) });
    }
  }

  return NextResponse.json({ results });
}
