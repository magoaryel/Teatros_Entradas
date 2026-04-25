"""
GitHub Actions scraper — Playwright scraper for JS-heavy ticket platforms.
Sends results to /api/ingest. Saves HTML snapshots as artifacts for debugging.
"""
import os, json, re, sys, requests, pathlib
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INGEST_URL    = os.environ.get("INGEST_URL", "")
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

if not INGEST_URL or not INGEST_SECRET:
    print("ERROR: INGEST_URL or INGEST_SECRET not set"); sys.exit(1)

HEADERS = {"x-ingest-secret": INGEST_SECRET, "Content-Type": "application/json"}
DEBUG_DIR = pathlib.Path("debug_html")
DEBUG_DIR.mkdir(exist_ok=True)


def get_active_events():
    print(f"Fetching events from {INGEST_URL}")
    r = requests.get(INGEST_URL, headers=HEADERS, timeout=15)
    if r.status_code == 401:
        print("ERROR 401: check INGEST_SECRET in Vercel env vars"); sys.exit(1)
    r.raise_for_status()
    events = r.json()
    print(f"Found {len(events)} active events")
    for e in events:
        print(f"  [{e.get('platform')}] {e.get('name')}")
    return events


def save_debug(name: str, html: str):
    path = DEBUG_DIR / f"{name}.html"
    path.write_text(html, encoding="utf-8", errors="replace")
    print(f"  Saved debug HTML: {path} ({len(html)} chars)")


def count_elements(page, *selectors) -> int:
    return sum(len(page.query_selector_all(s)) for s in selectors)


# ── todaslasentradas.com ─────────────────────────────────────────────────────

def scrape_todaslasentradas(page, url, name):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(4000)
    html = page.content()
    save_debug(name, html)
    print(f"  Title: {page.title()}")

    # Try Palco4 arraySesiones (same platform family)
    raw = page.evaluate("typeof arraySesiones !== 'undefined' ? JSON.stringify(arraySesiones) : null")
    if raw:
        sessions = json.loads(raw)
        print(f"  Found arraySesiones with {len(sessions)} sessions")
        return [{"session_id": str(s.get("idSesion","main")),
                 "label": s.get("litSesion") or s.get("fechaCelebracionStr",""),
                 "date": (s.get("fecha") or s.get("fechaCelebracionStr",""))[:10],
                 "capacity": s.get("aforo",0), "sold": s.get("entradasVendidas",0),
                 "reserved": s.get("entradasReservadas",0)}
                for s in sessions if not s.get("streamingOnly")]

    # Count every element whose class contains seat-related words
    seats = {
        "ButacaLibre":     count_elements(page, ".ButacaLibre"),
        "ButacaOcupada":   count_elements(page, ".ButacaOcupada", ".ButacaNoDisponible", ".ButacaVendida"),
        "[libre]":         count_elements(page, "[class*='libre']"),
        "[ocupad]":        count_elements(page, "[class*='ocupad']", "[class*='vendid']"),
        "svg rect":        count_elements(page, "svg rect"),
        "svg circle":      count_elements(page, "svg circle"),
    }
    print(f"  Seat element counts: {seats}")

    # Look for available count in text
    text = page.inner_text("body")
    print(f"  Body text (first 300): {text[:300].replace(chr(10),' ')}")
    nums = re.findall(r"(\d+)\s*(?:disponibles?|libres?|available)", text, re.IGNORECASE)
    print(f"  'disponibles' numbers: {nums}")

    libre = seats["ButacaLibre"] or seats["[libre]"]
    ocup  = seats["ButacaOcupada"] or seats["[ocupad]"]
    if libre + ocup > 5:
        return [{"session_id":"main","label":page.title(),"date":"",
                 "capacity": libre+ocup, "sold": ocup, "reserved": 0}]
    print("  No seat data found")
    return []


# ── bacantix.com ─────────────────────────────────────────────────────────────

def scrape_bacantix(page, url, name):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(5000)
    html = page.content()
    save_debug(name, html)
    print(f"  Title: {page.title()}")

    seats = {
        "Libre(class)":  count_elements(page, "[class*='Libre']", "[class*='libre']"),
        "Ocupado(class)":count_elements(page, "[class*='Ocupado']","[class*='Vendido']","[class*='ocupado']"),
        "Libre(title)":  count_elements(page, "[title='Libre']", "[title*='libre']"),
        "Ocupado(title)":count_elements(page, "[title='Ocupado']","[title*='Vendido']"),
        "svg rect":      count_elements(page, "svg rect"),
        "svg circle":    count_elements(page, "svg circle"),
        "svg path":      count_elements(page, "svg path"),
        "div[onclick]":  count_elements(page, "div[onclick]"),
        "td[onclick]":   count_elements(page, "td[onclick]"),
    }
    print(f"  Seat element counts: {seats}")
    text = page.inner_text("body")
    print(f"  Body text (first 300): {text[:300].replace(chr(10),' ')}")

    libre = seats["Libre(class)"] or seats["Libre(title)"]
    ocup  = seats["Ocupado(class)"] or seats["Ocupado(title)"]
    if libre + ocup > 5:
        return [{"session_id":"main","label":page.title(),"date":"",
                 "capacity": libre+ocup, "sold": ocup, "reserved": 0}]

    # Try SVG elements
    if seats["svg rect"] > 10:
        total = seats["svg rect"]
        print(f"  Using SVG rects as proxy: {total} total")
        return [{"session_id":"main","label":page.title(),"date":"",
                 "capacity": total, "sold": 0, "reserved": 0}]

    print("  No seat data found")
    return []


# ── reservaentradas.com ──────────────────────────────────────────────────────

def scrape_reservaentradas(page, url, name):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(3000)
    html = page.content()
    save_debug(name, html)
    print(f"  Title: {page.title()}")
    text = page.inner_text("body")
    print(f"  Body text (first 500): {text[:500].replace(chr(10),' ')}")

    # Patterns for available/sold
    for pattern, label in [
        (r"(\d+)\s+disponibles?", "disponibles"),
        (r"(\d+)\s+libres?",      "libres"),
        (r"(\d+)\s+entradas?\s+disponibles?", "entradas disponibles"),
        (r"quedan\s+(\d+)",       "quedan"),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            avail = int(m.group(1))
            tm = re.search(r"(\d+)\s+(?:total|aforo|plazas)", text, re.IGNORECASE)
            total = int(tm.group(1)) if tm else 0
            print(f"  Found '{label}': avail={avail}, total={total}")
            return [{"session_id":"main","label":page.title(),"date":"",
                     "capacity":total,"sold":max(0,total-avail),"reserved":0}]

    seats = {
        "libre":  count_elements(page, ".libre,.available,[class*='libre'],[class*='available']"),
        "ocupado":count_elements(page, ".ocupado,.sold,[class*='ocupado'],[class*='sold']"),
        "svg":    count_elements(page, "svg rect", "svg circle"),
    }
    print(f"  Seat counts: {seats}")
    if seats["libre"] + seats["ocupado"] > 5:
        return [{"session_id":"main","label":page.title(),"date":"",
                 "capacity":seats["libre"]+seats["ocupado"],
                 "sold":seats["ocupado"],"reserved":0}]
    print("  No seat data found")
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
    print(f"\nTargets: {len(targets)}")

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
            slug     = re.sub(r"[^a-z0-9]", "_", event["name"].lower())[:30]
            print(f"\n[{platform}] {event['name']}")
            print(f"  URL: {url}")
            try:
                sessions = SCRAPERS[platform](page, url, slug)
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
