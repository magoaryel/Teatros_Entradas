const TICKET_DOMAINS = [
  "gruposmedia.com", "entradas.plus",
  "todaslasentradas.com", "bacantix.com", "reservaentradas.com",
  "auditoriocartuja.com",
  "atrapalo.com", "ticketmaster.es", "eventbrite.es", "wegow.com", "fever.com",
];

export interface DiscoveredShow {
  slug: string;
  name: string;
  venue: string;
  city: string;
  date: string;        // human readable "15 de junio de 2026"
  isoDate: string;     // "2026-06-15" for sorting
  ticketUrl: string | null;
  pageUrl: string;
}

async function fetchHtml(url: string): Promise<string> {
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
    next: { revalidate: 0 },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

function extractLinks(html: string): string[] {
  return [...html.matchAll(/href="(https?:\/\/[^"]+)"/g)].map(m => m[1]);
}

function cleanTicketUrl(url: string): string {
  // Remove UTM/tracking params after &#038; or &
  return url.replace(/&#038;.*$/, "").replace(/&_gl=.*$/, "").replace(/&utm.*$/i, "");
}

async function parseEventPage(pageUrl: string): Promise<DiscoveredShow | null> {
  try {
    const html = await fetchHtml(pageUrl);
    const slug = pageUrl.split("/events/")[1]?.replace(/\/$/, "") ?? pageUrl;

    // Title
    const titleM = html.match(/<title>([^<]+)<\/title>/);
    const rawTitle = titleM?.[1] ?? slug;
    const name = rawTitle.split(/[-–|]/)[0].trim().replace(/\s+/g, " ");

    // Ticket link
    const links = extractLinks(html);
    const ticketRaw = links.find(l => TICKET_DOMAINS.some(d => l.includes(d)));
    const ticketUrl = ticketRaw ? cleanTicketUrl(ticketRaw) : null;

    // Venue — look for "Teatro X", "Auditorio X", etc.
    const venueM = html.match(/(?:Teatro|Auditorio|Sala|Palacio|Centro Cultural|Teatro-Cine)\s+[\w\sáéíóúñÁÉÍÓÚÑ\-]+/i);
    const venue = venueM?.[0]?.replace(/\s+/g, " ").trim() ?? "";

    // City — from event slug or title
    const cityM = name.match(/(?:en|EN)\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ]+)?)/);
    const city = cityM?.[1] ?? "";

    // Date — human readable
    const dateM = html.match(/\d{1,2}\s+de\s+\w+\s+(?:de\s+)?\d{4}/i);
    const date = dateM?.[0] ?? "";

    // ISO date for sorting
    const MONTHS: Record<string, string> = {
      enero:"01", febrero:"02", marzo:"03", abril:"04", mayo:"05", junio:"06",
      julio:"07", agosto:"08", septiembre:"09", octubre:"10", noviembre:"11", diciembre:"12",
    };
    let isoDate = "";
    if (date) {
      const parts = date.toLowerCase().replace("de ", "").split(/\s+/);
      if (parts.length >= 3) {
        const day = parts[0].padStart(2, "0");
        const month = MONTHS[parts[1]] ?? "01";
        const year = parts[parts.length - 1];
        isoDate = `${year}-${month}-${day}`;
      }
    }

    return { slug, name, venue, city, date, isoDate, ticketUrl, pageUrl };
  } catch {
    return null;
  }
}

export async function discoverShows(): Promise<DiscoveredShow[]> {
  // 1. Get the /gira/ page which lists all events
  const giraHtml = await fetchHtml("https://showsaryel.com/gira/");
  const links = extractLinks(giraHtml);

  // 2. Find all /events/* pages
  const eventUrls = [...new Set(
    links.filter(l => l.includes("showsaryel.com/events/"))
  )];

  // 3. Parse each event page in parallel
  const results = await Promise.all(eventUrls.map(parseEventPage));
  return results.filter((r): r is DiscoveredShow => r !== null);
}
