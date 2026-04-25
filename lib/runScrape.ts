import * as db from "./db";
import { scrapeEvent } from "./scraper";
import { notifySales, notifySoldOut } from "./telegram";

export async function runScrapeForEvent(event: {
  id: number;
  name: string;
  venue: string;
  url: string;
  platform: string;
}) {
  const sessions = await scrapeEvent(event.url, event.platform);

  for (const s of sessions) {
    const sessionDbId = await db.upsertSession(
      event.id, s.session_id, s.label, s.date, s.capacity
    );

    const prev = await db.getLatestSnapshot(sessionDbId);
    const soldBefore = prev ? (prev.sold as number) : 0;

    await db.saveSnapshot(sessionDbId, s.sold, s.reserved, s.capacity);

    if (s.sold > soldBefore) {
      if (s.capacity - s.sold <= 0) {
        await notifySoldOut(event.name, event.venue, s.label);
      } else {
        await notifySales(
          event.name, event.venue, s.label,
          s.sold, soldBefore, s.capacity
        );
      }
    }
  }
}
