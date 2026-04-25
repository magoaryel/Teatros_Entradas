import { NextResponse } from "next/server";
import { sendTest } from "@/lib/telegram";

export async function POST() {
  const ok = await sendTest();
  return NextResponse.json({ ok });
}
