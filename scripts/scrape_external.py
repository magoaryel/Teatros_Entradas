"""
GitHub Actions scraper — Playwright scraper for JS-heavy ticket platforms.
Sends results to /api/ingest.
"""
import os, json, re, sys, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INGEST_URL    = os.environ.get("INGEST_URL", "")
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

if not INGEST_URL or not INGEST_SECRET:
    print("ERROR: INGEST_URL or INGEST_SECRET not set"); sys.exit(1)

HEADERS = {"x-ingest-secret": INGEST_SECRET, "Content-Type": "application/json"}


def get_active_events():
    print(f"Fetching events from {INGEST_URL}")
    r = requests.get(INGEST_URL, headers=HEADERS, timeout=15)
    if r.status_code == 401:
        print("ERROR 401: check INGEST_SECRET in Vercel env vars"); sys.exit(1)
    r.raise_for_status()
    events = r.json()
    targets = [e for e in events if e.get("platform") in SCRAPERS]
    print(f"Found {len(events)} events, {len(targets)} to scrape")
    for e in targets:
        print(f"  [{e.get('platform')}] {e.get('name')} — {e.get('url', '')[:80]}")
    return events


# ── todaslasentradas.com ─────────────────────────────────────────────────────
# Seat classes confirmed from HTML: .mapaLibre and .mapaOcupada

def scrape_todaslasentradas(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)

    # Try Palco4 arraySesiones first
    raw = page.evaluate("typeof arraySesiones !== 'undefined' ? JSON.stringify(arraySesiones) : null")
    if raw:
        sessions = json.loads(raw)
        return [{"session_id": str(s.get("idSesion", "main")),
                 "label": s.get("litSesion") or s.get("fechaCelebracionStr", ""),
                 "date": (s.get("fecha") or s.get("fechaCelebracionStr", ""))[:10],
                 "capacity": s.get("aforo", 0), "sold": s.get("entradasVendidas", 0),
                 "reserved": s.get("entradasReservadas", 0)}
                for s in sessions if not s.get("streamingOnly")]

    # Use confirmed CSS classes from HTML analysis
    libre   = len(page.query_selector_all("[class*='mapaLibre']"))
    ocupada = len(page.query_selector_all("[class*='mapaOcupada']"))
    total   = libre + ocupada
    print(f"  mapaLibre={libre}, mapaOcupada={ocupada}, total={total}")

    if total == 0:
        print("  No seat data found")
        return []

    title = page.title()
    # Extract date from page body
    body  = page.inner_text("body")
    date_m = re.search(r'\d{1,2}\s+\w+\s+\d{4}', body)
    label = date_m.group(0) if date_m else title

    return [{"session_id": "main", "label": label, "date": "",
             "capacity": total, "sold": ocupada, "reserved": 0}]


# ── bacantix.com ─────────────────────────────────────────────────────────────
# NOTE: URL must include &codigo= parameter (fixed in syncShows.ts)

def scrape_bacantix(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(5000)

    title = page.title()
    print(f"  Title: {title}")

    # Check if page loaded correctly
    body = page.inner_text("body")
    if "no está disponible" in body or "Oops" in body:
        print(f"  Page not available — URL might be wrong")
        print(f"  Body: {body[:200]}")
        return []

    # Try multiple seat selectors (bacantix uses various class conventions)
    selectors_libre  = ["[class*='Libre']", "[class*='libre']", "[title='Libre']",
                        ".asiento-libre", ".localidad-libre"]
    selectors_ocup   = ["[class*='Ocupado']", "[class*='Vendido']", "[class*='ocupado']",
                        "[title='Ocupado']", ".asiento-ocupado", ".localidad-ocupado"]

    libre  = sum(len(page.query_selector_all(s)) for s in selectors_libre)
    ocupado = sum(len(page.query_selector_all(s)) for s in selectors_ocup)
    print(f"  libre={libre}, ocupado={ocupado}")

    # Try SVG approach — count by computed fill color
    if libre + ocupado == 0:
        result = page.evaluate("""() => {
            const seats = document.querySelectorAll('svg rect, svg circle, svg polygon');
            const colors = {};
            seats.forEach(el => {
                const fill = window.getComputedStyle(el).fill;
                colors[fill] = (colors[fill] || 0) + 1;
            });
            return colors;
        }""")
        print(f"  SVG computed colors: {result}")
        if result:
            # Most common colors: try to identify libre vs ocupado
            sorted_colors = sorted(result.items(), key=lambda x: -x[1])
            print(f"  Top colors: {sorted_colors[:5]}")

    if libre + ocupado > 5:
        return [{"session_id": "main", "label": title, "date": "",
                 "capacity": libre + ocupado, "sold": ocupado, "reserved": 0}]

    print("  No seat data found")
    return []


# ── reservaentradas.com ──────────────────────────────────────────────────────
# 617 butaca1 elements — state set via Angular (computed styles)

def scrape_reservaentradas(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(5000)  # Extra wait for Angular

    title = page.title()

    # Use page.evaluate to check computed fill colors of seat paths
    # Each seat (butaca1) contains SVG paths — their color indicates state
    result = page.evaluate("""() => {
        const seats = document.querySelectorAll('.butaca1, .cursorPointer.butaca1');
        let libre = 0, ocupado = 0, unknown = 0;
        seats.forEach(seat => {
            const paths = seat.querySelectorAll('path, rect, circle');
            if (paths.length === 0) { unknown++; return; }
            // Get computed fill of first significant path
            const fill = window.getComputedStyle(paths[0]).fill;
            // Typically: grey/dark = occupied, light/green/blue = available
            // We'll collect the fills and analyze
            if (fill) {
                const rgb = fill.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                if (rgb) {
                    const [r, g, b] = [parseInt(rgb[1]), parseInt(rgb[2]), parseInt(rgb[3])];
                    const brightness = (r + g + b) / 3;
                    // Dark grey (158,158,158) likely = occupied or default
                    // White or light = available
                    if (brightness > 200) libre++;
                    else if (brightness < 100) ocupado++;
                    else unknown++;
                }
            }
        });
        return { total: seats.length, libre, ocupado, unknown };
    }""")

    print(f"  Angular seat analysis: {result}")

    # Also try getting all unique fill colors to understand the mapping
    colors = page.evaluate("""() => {
        const seats = document.querySelectorAll('.butaca1 path');
        const colorMap = {};
        seats.forEach(el => {
            const fill = window.getComputedStyle(el).fill;
            colorMap[fill] = (colorMap[fill] || 0) + 1;
        });
        return colorMap;
    }""")
    print(f"  Fill colors of butaca1 paths: {colors}")

    total = result.get("total", 0) if result else 0
    if total == 0:
        # Fallback: text-based
        body = page.inner_text("body")
        for pattern in [r"(\d+)\s+disponibles?", r"(\d+)\s+libres?"]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                avail = int(m.group(1))
                print(f"  Text fallback: {avail} disponibles")
                return [{"session_id": "main", "label": title, "date": "",
                         "capacity": 0, "sold": 0, "reserved": 0}]
        print("  No seat data found")
        return []

    # If we got color data, use it
    if colors:
        sorted_c = sorted(colors.items(), key=lambda x: -x[1])
        print(f"  Top fill colors: {sorted_c[:4]}")
        # If two dominant colors, one is libre and one is ocupado
        # We need to determine which is which — for now report total
        # and mark unknown as available (conservative)
        ocupado = result.get("ocupado", 0)
        libre   = result.get("libre", 0) + result.get("unknown", 0)
        if libre + ocupado == 0:
            libre = total  # All seats, we don't know state yet

    return [{"session_id": "main", "label": title, "date": "",
             "capacity": total,
             "sold": result.get("ocupado", 0),
             "reserved": 0}]


SCRAPERS = {
    "todaslasentradas": scrape_todaslasentradas,
    "bacantix":         scrape_bacantix,
    "reservaentradas":  scrape_reservaentradas,
}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    events  = get_active_events()
    targets = [e for e in events if e.get("platform") in SCRAPERS]

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            locale="es-ES",
        )
        page = ctx.new_page()

        for event in targets:
            platform = event["platform"]
            url      = event["url"]
            print(f"\n[{platform}] {event['name']}")
            print(f"  URL: {url}")
            try:
                sessions = SCRAPERS[platform](page, url)
                if sessions:
                    results.append({"eventId": event["id"], "eventName": event["name"],
                                    "eventVenue": event["venue"], "sessions": sessions})
                    for s in sessions:
                        print(f"  -> {s['label']}: {s['sold']} vendidas / {s['capacity']} aforo")
            except PWTimeout:
                print("  TIMEOUT")
            except Exception as ex:
                print(f"  ERROR: {ex}")

        browser.close()

    print(f"\nSending {len(results)} results to ingest...")
    if results:
        r = requests.post(INGEST_URL, json={"results": results}, headers=HEADERS, timeout=15)
        print(f"Ingest: {r.status_code} — {r.text}")
    else:
        print("Nothing scraped.")


if __name__ == "__main__":
    main()
