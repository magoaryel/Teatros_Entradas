import { NextRequest, NextResponse } from "next/server";
import { getEvents, addEvent, initDb } from "@/lib/db";
import { detectPlatform } from "@/lib/scraper";

export async function GET() {
  await initDb();
  const events = await getEvents();
  return NextResponse.json(events);
}

export async function POST(req: NextRequest) {
  await initDb();
  const { name, venue, url } = await req.json();
  if (!name || !venue || !url) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }
  const platform = detectPlatform(url);
  const id = await addEvent(name, venue, url, platform);
  return NextResponse.json({ id });
}
