import { NextRequest, NextResponse } from "next/server";
import { getEvents } from "@/lib/db";
import { runScrapeForEvent } from "@/lib/runScrape";

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const events = await getEvents();
  const event = events.find((e) => e.id === Number(id));
  if (!event) return NextResponse.json({ error: "Not found" }, { status: 404 });

  await runScrapeForEvent({
    id: event.id as number,
    name: event.name as string,
    venue: event.venue as string,
    url: event.url as string,
    platform: event.platform as string,
  });

  return NextResponse.json({ ok: true });
}
