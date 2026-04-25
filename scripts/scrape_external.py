"""
GitHub Actions scraper — runs Playwright to scrape JS-heavy ticket platforms.
Sends results to the Vercel /api/ingest endpoint.
"""
import os, json, re, sys, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INGEST_URL    = os.environ.get("INGEST_URL", "")
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

if not INGEST_URL or not INGEST_SECRET:
    print("ERROR: INGEST_URL or INGEST_SECRET not set")
    sys.exit(1)

HEADERS = {"x-ingest-secret": INGEST_SECRET, "Content-Type": "application/json"}


def get_active_events():
    print(f"Fetching active events from {INGEST_URL}")
    r = requests.get(INGEST_URL, headers=HEADERS, timeout=15)
    print(f"  Response: {r.status_code}")
    if r.status_code == 401:
        print("  ERROR: Invalid INGEST_SECRET — check Vercel env vars")
        sys.exit(1)
    r.raise_for_status()
    events = r.json()
    print(f"  Found {len(events)} active events")
    for e in events:
        print(f"    [{e.get('platform')}] {e.get('name')} — {e.get('url', '')[:60]}")
    return events


# ── Platform scrapers ────────────────────────────────────────────────────────

def scrape_todaslasentradas(page, url):
    print(f"  Loading {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    # Try arraySesiones (Palco4 platform)
    raw = page.evaluate("typeof arraySesiones !== 'undefined' ? JSON.stringify(arraySesiones) : null")
    if raw:
        print(f"  Found arraySesiones!")
        sessions = json.loads(raw)
        return [
            {
                "session_id": str(s.get("idSesion", "main")),
                "label": s.get("litSesion") or s.get("fechaCelebracionStr", ""),
                "date": (s.get("fecha") or s.get("fechaCelebracionStr", ""))[:10],
                "capacity": s.get("aforo", 0),
                "sold": s.get("entradasVendidas", 0),
                "reserved": s.get("entradasReservadas", 0),
            }
            for s in sessions if not s.get("streamingOnly")
        ]

    # Count seat DOM elements
    selectors = [
        (".ButacaLibre", ".ButacaOcupada,.ButacaNoDisponible,.ButacaVendida"),
        ("[class*='libre']", "[class*='ocupad'],[class*='vendid']"),
        (".seat-available", ".seat-taken,.seat-sold"),
    ]
    for (sel_libre, sel_ocup) in selectors:
        libre   = len(page.query_selector_all(sel_libre))
        ocupada = len(page.query_selector_all(sel_ocup))
        if libre + ocupada > 5:
            print(f"  Seats via DOM: {libre} libre, {ocupada} ocupada")
            return [{"session_id": "main", "label": page.title(), "date": "",
                     "capacity": libre + ocupada, "sold": ocupada, "reserved": 0}]

    print(f"  No seat data found. Page title: {page.title()}")
    return []


def scrape_bacantix(page, url):
    print(f"  Loading {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(4000)

    selectors = [
        ("[class*='Libre']", "[class*='Ocupado'],[class*='Vendido']"),
        ("[title='Libre']", "[title='Ocupado'],[title='Vendido']"),
        (".libre", ".ocupado,.vendido"),
    ]
    for (sel_libre, sel_ocup) in selectors:
        libre   = len(page.query_selector_all(sel_libre))
        ocupada = len(page.query_selector_all(sel_ocup))
        if libre + ocupada > 5:
            print(f"  Seats via DOM: {libre} libre, {ocupada} ocupada")
            return [{"session_id": "main", "label": page.title(), "date": "",
                     "capacity": libre + ocupada, "sold": ocupada, "reserved": 0}]

    print(f"  No seat data found. Page title: {page.title()}")
    return []


def scrape_reservaentradas(page, url):
    print(f"  Loading {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    text = page.inner_text("body")
    m = re.search(r"(\d+)\s+disponibles?", text, re.IGNORECASE)
    if m:
        avail = int(m.group(1))
        t = re.search(r"(\d+)\s+(?:total|aforo)", text, re.IGNORECASE)
        total = int(t.group(1)) if t else 0
        print(f"  disponibles={avail}, total={total}")
        return [{"session_id": "main", "label": page.title(), "date": "",
                 "capacity": total, "sold": max(0, total - avail), "reserved": 0}]

    print(f"  No availability text found. Page title: {page.title()}")
    return []


SCRAPERS = {
    "todaslasentradas": scrape_todaslasentradas,
    "bacantix":         scrape_bacantix,
    "reservaentradas":  scrape_reservaentradas,
}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    events  = get_active_events()
    targets = [e for e in events if e.get("platform") in SCRAPERS]

    print(f"\nTargets to scrape: {len(targets)}")
    if not targets:
        print("No browser-scraping targets. Done.")
        return

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            locale="es-ES",
        )
        page = context.new_page()

        for event in targets:
            platform = event["platform"]
            url      = event["url"]
            print(f"\n[{platform}] {event['name']}")
            try:
                sessions = SCRAPERS[platform](page, url)
                if sessions:
                    results.append({
                        "eventId":    event["id"],
                        "eventName":  event["name"],
                        "eventVenue": event["venue"],
                        "sessions":   sessions,
                    })
                    for s in sessions:
                        print(f"  -> {s['label']}: {s['sold']} vendidas / {s['capacity']} aforo")
            except PWTimeout:
                print(f"  TIMEOUT loading page")
            except Exception as ex:
                print(f"  ERROR: {ex}")

        browser.close()

    print(f"\nSending {len(results)} results to ingest...")
    if results:
        r = requests.post(INGEST_URL, json={"results": results}, headers=HEADERS, timeout=15)
        print(f"Ingest: {r.status_code} — {r.text}")
    else:
        print("Nothing scraped, nothing sent.")


if __name__ == "__main__":
    main()
