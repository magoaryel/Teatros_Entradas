import { NextRequest, NextResponse } from "next/server";
import { toggleEvent, deleteEvent, getEventSessions } from "@/lib/db";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const sessions = await getEventSessions(Number(id));
  return NextResponse.json(sessions);
}

export async function PATCH(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  await toggleEvent(Number(id));
  return NextResponse.json({ ok: true });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  await deleteEvent(Number(id));
  return NextResponse.json({ ok: true });
}
