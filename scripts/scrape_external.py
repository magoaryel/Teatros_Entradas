"""
GitHub Actions scraper — runs Playwright to scrape JS-heavy ticket platforms.
Sends results to the Vercel /api/ingest endpoint.
"""
import os, json, re, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INGEST_URL    = os.environ["INGEST_URL"]    # e.g. https://tu-app.vercel.app/api/ingest
INGEST_SECRET = os.environ["INGEST_SECRET"] # same as Vercel env var

HEADERS = {"x-ingest-secret": INGEST_SECRET}


def get_active_events():
    r = requests.get(INGEST_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


# ── Platform scrapers ────────────────────────────────────────────────────────

def scrape_gruposmedia(page, url):
    """Already handled by Vercel — skip."""
    return []


def scrape_todaslasentradas(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    # Try arraySesiones first (same platform family)
    raw = page.evaluate("typeof arraySesiones !== 'undefined' ? JSON.stringify(arraySesiones) : null")
    if raw:
        sessions = json.loads(raw)
        return [
            {
                "session_id": str(s.get("idSesion", "")),
                "label": s.get("litSesion") or s.get("fechaCelebracionStr", ""),
                "date": (s.get("fecha") or s.get("fechaCelebracionStr", ""))[:10],
                "capacity": s.get("aforo", 0),
                "sold": s.get("entradasVendidas", 0),
                "reserved": s.get("entradasReservadas", 0),
            }
            for s in sessions if not s.get("streamingOnly")
        ]

    # Fallback: count seat elements
    libre   = len(page.query_selector_all(".ButacaLibre, .butaca-libre, [class*='libre']"))
    ocupada = len(page.query_selector_all(".ButacaOcupada, .butaca-ocupada, [class*='ocupad'], [class*='vendid']"))
    total   = libre + ocupada
    if total == 0:
        return []

    title = page.title()
    return [{
        "session_id": "main",
        "label": title,
        "date": "",
        "capacity": total,
        "sold": ocupada,
        "reserved": 0,
    }]


def scrape_bacantix(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(4000)

    # Count seat labels
    libre   = len(page.query_selector_all("[class*='Libre'], [class*='libre'], [title*='Libre']"))
    ocupado = len(page.query_selector_all("[class*='Ocupado'], [class*='ocupado'], [class*='Vendido'], [title*='Ocupado']"))
    total   = libre + ocupado
    if total == 0:
        return []

    title = page.title()
    return [{
        "session_id": "main",
        "label": title,
        "date": "",
        "capacity": total,
        "sold": ocupado,
        "reserved": 0,
    }]


def scrape_reservaentradas(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    # Look for availability numbers in the page
    text = page.inner_text("body")
    # Try to find patterns like "X disponibles" or "X entradas"
    m = re.search(r"(\d+)\s+disponibles?", text, re.IGNORECASE)
    if m:
        avail = int(m.group(1))
        # Try to get total
        t = re.search(r"(\d+)\s+(?:total|aforo|entradas totales)", text, re.IGNORECASE)
        total = int(t.group(1)) if t else 0
        sold = total - avail if total > 0 else 0
        title = page.title()
        return [{
            "session_id": "main",
            "label": title,
            "date": "",
            "capacity": total,
            "sold": sold,
            "reserved": 0,
        }]
    return []


SCRAPERS = {
    "gruposmedia":       scrape_gruposmedia,
    "todaslasentradas":  scrape_todaslasentradas,
    "bacantix":          scrape_bacantix,
    "reservaentradas":   scrape_reservaentradas,
}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    events = get_active_events()
    # Only scrape platforms that need a browser (skip gruposmedia — Vercel handles it)
    targets = [e for e in events if e.get("platform") in SCRAPERS and e["platform"] != "gruposmedia"]

    if not targets:
        print("No browser-scraping targets found.")
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
            print(f"Scraping [{platform}] {event['name']} — {url}")
            try:
                scraper  = SCRAPERS[platform]
                sessions = scraper(page, url)
                if sessions:
                    results.append({
                        "eventId":    event["id"],
                        "eventName":  event["name"],
                        "eventVenue": event["venue"],
                        "sessions":   sessions,
                    })
                    for s in sessions:
                        print(f"  {s['label']}: {s['sold']} vendidas / {s['capacity']} aforo")
                else:
                    print(f"  No data found")
            except PWTimeout:
                print(f"  TIMEOUT")
            except Exception as ex:
                print(f"  ERROR: {ex}")

        browser.close()

    if results:
        r = requests.post(INGEST_URL, json={"results": results}, headers=HEADERS, timeout=15)
        print(f"\nIngest response: {r.status_code} {r.text}")
    else:
        print("\nNothing to ingest.")


if __name__ == "__main__":
    main()
