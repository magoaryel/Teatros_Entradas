export interface ScrapedSession {
  session_id: string;
  label: string;
  date: string;
  capacity: number;
  sold: number;
  reserved: number;
}

async function scrapeGruposmedia(url: string): Promise<ScrapedSession[]> {
  const res = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
      "Accept-Language": "es-ES,es;q=0.9",
    },
    next: { revalidate: 0 },
  });

  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);

  const html = await res.text();
  const match = html.match(/arraySesiones\s*=\s*(\[[\s\S]*?\]);/);
  if (!match) throw new Error("arraySesiones not found in page");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sessions: any[] = JSON.parse(match[1]);

  return sessions
    .filter((s) => !s.streamingOnly)
    .map((s) => ({
      session_id: String(s.idSesion),
      label: s.litSesion || s.fechaCelebracionStr || String(s.idSesion),
      date: s.fecha || s.fechaCelebracionStr?.slice(0, 10) || "",
      capacity: s.aforo ?? 0,
      sold: s.entradasVendidas ?? 0,
      reserved: s.entradasReservadas ?? 0,
    }));
}

export function detectPlatform(url: string): string {
  if (url.includes("gruposmedia.com") || url.includes("entradas.plus")) return "gruposmedia";
  if (url.includes("todaslasentradas.com")) return "todaslasentradas";
  if (url.includes("bacantix.com")) return "bacantix";
  if (url.includes("reservaentradas.com")) return "reservaentradas";
  if (url.includes("auditoriocartuja.com")) return "auditoriocartuja";
  return "manual";
}

// Platforms that require a real browser (JS execution) — not supported on Vercel serverless
const BROWSER_REQUIRED = ["todaslasentradas", "bacantix", "reservaentradas", "auditoriocartuja", "manual"];

export function requiresBrowser(platform: string): boolean {
  return BROWSER_REQUIRED.includes(platform);
}

export async function scrapeEvent(
  url: string,
  platform: string
): Promise<ScrapedSession[]> {
  if (platform === "gruposmedia") return scrapeGruposmedia(url);
  if (BROWSER_REQUIRED.includes(platform)) {
    throw new Error(`BROWSER_REQUIRED:${platform}`);
  }
  throw new Error(`Platform not supported: ${platform}`);
}
