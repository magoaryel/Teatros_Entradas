"""
GitHub Actions scraper for JS-heavy ticket platforms.
Findings:
 - todaslasentradas.com: classes mapaLibre / mapaOcupada in HTML
 - bacantix.com:  MCIAjax.aspx response XML — O attr absent=libre, O=201=vendida
 - reservaentradas.com: Angular, need to navigate base→click Butacas step, then count butaca1
"""
import os, json, re, sys, requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INGEST_URL    = os.environ.get("INGEST_URL", "")
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

if not INGEST_URL or not INGEST_SECRET:
    print("ERROR: INGEST_URL or INGEST_SECRET not set"); sys.exit(1)

HEADERS = {"x-ingest-secret": INGEST_SECRET, "Content-Type": "application/json"}


def get_active_events():
    print(f"Fetching events from Vercel...")
    r = requests.get(INGEST_URL, headers=HEADERS, timeout=15)
    if r.status_code == 401:
        print("ERROR 401: check INGEST_SECRET in Vercel env vars"); sys.exit(1)
    r.raise_for_status()
    events  = r.json()
    targets = [e for e in events if e.get("platform") in SCRAPERS]
    print(f"Found {len(events)} events, {len(targets)} to scrape")
    for e in targets:
        print(f"  [{e['platform']}] {e['name']} — {e['url'][:80]}")
    return events


# ── todaslasentradas.com ──────────────────────────────────────────────────────
# Classes confirmed in HTML: mapaLibre / mapaOcupada

def scrape_todaslasentradas(page, url):
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)

    # Try Palco4 arraySesiones (same platform family)
    raw = page.evaluate("typeof arraySesiones !== 'undefined' ? JSON.stringify(arraySesiones) : null")
    if raw:
        sessions = json.loads(raw)
        return [{"session_id": str(s.get("idSesion", "main")),
                 "label": s.get("litSesion") or s.get("fechaCelebracionStr", ""),
                 "date": (s.get("fecha") or s.get("fechaCelebracionStr", ""))[:10],
                 "capacity": s.get("aforo", 0), "sold": s.get("entradasVendidas", 0),
                 "reserved": s.get("entradasReservadas", 0)}
                for s in sessions if not s.get("streamingOnly")]

    libre   = len(page.query_selector_all("[class*='mapaLibre']"))
    ocupada = len(page.query_selector_all("[class*='mapaOcupada']"))
    total   = libre + ocupada
    print(f"  mapaLibre={libre}, mapaOcupada={ocupada}")

    if total == 0:
        print("  No seat data found")
        return []

    # Extract date/label from page body
    body  = page.inner_text("body")
    # Pattern: "Sábado 16 mayo 19:00" or "16 mayo 2026 19:00"
    date_m = re.search(r'(?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)\s+\d+\s+\w+\s+\d{2}:\d{2}', body, re.IGNORECASE)
    if not date_m:
        date_m = re.search(r'\d{1,2}\s+(?:de\s+)?\w+\s+(?:de\s+)?\d{4}', body)
    label = date_m.group(0).strip() if date_m else page.title()

    return [{"session_id": "main", "label": label, "date": "",
             "capacity": total, "sold": ocupada, "reserved": 0}]


# ── bacantix.com ──────────────────────────────────────────────────────────────
# MCIAjax.aspx XML: no O attr = libre, O="201" = vendida, O="90" = discapacitados (skip)

def scrape_bacantix(page, url):
    mci_body = []

    def on_response(resp):
        if "MCIAjax" in resp.url:
            try: mci_body.append(resp.body().decode("utf-8", errors="replace"))
            except: pass

    page.on("response", on_response)

    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    # Accept cookies if present
    try:
        btn = page.query_selector("button:has-text('Aceptar')")
        if btn: btn.click(); page.wait_for_timeout(1000)
    except: pass
    page.wait_for_timeout(4000)

    if not mci_body:
        print("  MCIAjax response not captured")
        return []

    body = mci_body[0]
    # Count numeric-id <I> elements by O attribute
    all_seats = re.findall(r'<I id="(\d+)"([^/]*)/>', body)
    libre = sold = 0
    for _, attrs in all_seats:
        o = re.search(r'O="(\d+)"', attrs)
        if not o:
            libre += 1       # no O attribute = available
        elif o.group(1) == "201":
            sold += 1        # O=201 = sold/occupied
        # O=90 = disabled spaces, skip

    total = libre + sold
    print(f"  Libre={libre}, Vendidas(O=201)={sold}, Total={total}")

    if total == 0:
        print("  No seat data found in MCIAjax")
        return []

    # Extract date from body text
    body_text = page.inner_text("body")
    date_m = re.search(r'(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)[,\s]+\d+\s+\w+\s+\d{4}', body_text, re.IGNORECASE)
    label = date_m.group(0).strip() if date_m else page.title()

    return [{"session_id": "main", "label": label, "date": "",
             "capacity": total, "sold": sold, "reserved": 0}]


# ── auditoriocartuja.com ─────────────────────────────────────────────────────
# Uses Janto ticketing: apiw5.janto.es/v5/sessions/{code}/full/01
# Event code (e.g. A291026HIPNOSTIS) is embedded in the page HTML

def scrape_auditoriocartuja(page, url):
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        html = resp.text
    except Exception as e:
        print(f"  HTTP error: {e}")
        return []

    # Try Janto API URL pattern first, then standalone code pattern
    code_m = re.search(r'apiw5\.janto\.es/[^/]+/sessions/([A-Z0-9]+)', html)
    if not code_m:
        code_m = re.search(r'["\'/]([A-Z]\d{6}[A-Z]{2,})["\'/]', html)
    if not code_m:
        print("  Janto event code not found in page")
        return []

    event_code = code_m.group(1)
    print(f"  Janto event code: {event_code}")

    try:
        jr = requests.get(
            f"https://apiw5.janto.es/v5/sessions/{event_code}/full/01",
            timeout=15
        )
        jr.raise_for_status()
        data = jr.json()
    except Exception as e:
        print(f"  Janto API error: {e}")
        return []

    sessions = data if isinstance(data, list) else [data]
    results = []
    for s in sessions:
        mt        = s.get("maxTickets") or {}
        available = mt.get("availableTickets", 0)
        pct_avail = float(s.get("percentAvailable", 1.0))

        # total = available / percentAvailable  (e.g. 499 / 0.998 ≈ 500)
        if 0 < pct_avail < 1:
            total = round(available / pct_avail)
        else:
            total = available

        sold = max(0, total - available)

        raw = str(s.get("sessionDate", ""))
        if len(raw) >= 12:
            label    = f"{raw[6:8]}/{raw[4:6]}/{raw[:4]} {raw[8:10]}:{raw[10:12]}"
            date_iso = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        else:
            label    = raw or page.title() if hasattr(page, "title") else raw
            date_iso = ""

        session_id = str(s.get("sessionId") or s.get("sessionDate") or "main")
        print(f"  Session {label}: available={available}, total={total}, sold={sold}")

        results.append({
            "session_id": session_id,
            "label":      label,
            "date":       date_iso,
            "capacity":   total,
            "sold":       sold,
            "reserved":   0,
        })

    return results


# ── reservaentradas.com ───────────────────────────────────────────────────────
# Angular app — must load base URL then click "Butacas" step to render seat map
# butaca1 elements: count by computed fill color

def _accept_cookies(page):
    for sel in ['button:has-text("Aceptar")', 'button:has-text("Accept")',
                'button:has-text("Acepto")', '#onetrust-accept-btn-handler',
                '.accept-cookies', '[class*="cookie"] button']:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(800)
                return
        except: pass


def scrape_reservaentradas(_, url):
    """
    reservaentradas.com uses sesion=12345 (hardcoded placeholder) in the page HTML.
    The selbutacav2 API always fails → seat colors are identical → can't detect sold count.
    We use a plain HTTP request to get total capacity from the server-rendered HTML.
    Sold count is always 0 (tracking unavailable until venue fixes their config).
    """
    import urllib.request as ureq
    try:
        req = ureq.Request(
            "https://www.reservaentradas.com/entrada/sessionone/buy/teatrocinesortega/tickets/18636"
            "?destatic=false&sala=0&port=&step=2",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with ureq.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  HTTP error: {e}")
        return []

    import re as re2
    butaca1 = len(re2.findall(r'cursorPointer butaca1', html))
    print(f"  butaca1 (standard seats): {butaca1}")
    if butaca1 == 0:
        print("  No seat data found")
        return []

    date_m = re2.search(r'\d{1,2}/\d{2}/\d{4}\s+\d{2}:\d{2}', html)
    label = date_m.group(0) if date_m else "30/05/2026 20:00"
    print(f"  NOTE: sesion=12345 hardcoded, sold count unavailable")
    return [{"session_id": "main", "label": label, "date": "2026-05-30",
             "capacity": butaca1, "sold": 0, "reserved": 0}]


SCRAPERS = {
    "todaslasentradas":  scrape_todaslasentradas,
    "bacantix":          scrape_bacantix,
    "reservaentradas":   scrape_reservaentradas,
    "auditoriocartuja":  scrape_auditoriocartuja,
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
                else:
                    print("  No data")
            except PWTimeout:
                print("  TIMEOUT")
            except Exception as ex:
                print(f"  ERROR: {ex}")

        browser.close()

    print(f"\nSending {len(results)} results...")
    if results:
        r = requests.post(INGEST_URL, json={"results": results}, headers=HEADERS, timeout=15)
        print(f"Ingest: {r.status_code} — {r.text}")
    else:
        print("Nothing scraped.")


if __name__ == "__main__":
    main()
