"""
GitHub Actions scraper for JS-heavy ticket platforms.
Findings:
 - todaslasentradas.com: classes mapaLibre / mapaOcupada in HTML
 - bacantix.com:  MCIAjax.aspx response XML — O attr absent=libre, O=201=vendida
 - reservaentradas.com: Angular, need to navigate base→click Butacas step, then count butaca1
"""
import os, json, re, sys, requests, datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

MESES = {"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
         "julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

def _parse_es_date(day_s: str, month_s: str, year_s: str | None) -> str:
    """Return ISO date YYYY-MM-DD from Spanish day/month/year strings."""
    month = MESES.get(month_s.lower(), "")
    if not month:
        return ""
    day = day_s.zfill(2)
    if year_s:
        return f"{year_s}-{month}-{day}"
    # Infer year: if date already passed this year, use next year
    today = datetime.date.today()
    try:
        candidate = datetime.date(today.year, int(month), int(day))
        year = today.year if candidate >= today else today.year + 1
    except ValueError:
        year = today.year
    return f"{year}-{month}-{day}"

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
    # Try with year: "Sábado 16 mayo 2026 19:00"
    date_m = re.search(
        r'(?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)\s+(\d+)\s+(\w+)\s+(\d{4})\s+(\d{2}:\d{2})',
        body, re.IGNORECASE)
    if date_m:
        date_iso = _parse_es_date(date_m.group(1), date_m.group(2), date_m.group(3))
        label    = f"{date_iso}T{date_m.group(4)}" if date_iso else date_m.group(0).strip()
    else:
        # No year: "Sábado 16 mayo 19:00"
        date_m2 = re.search(
            r'(?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)\s+(\d+)\s+(\w+)\s+(\d{2}:\d{2})',
            body, re.IGNORECASE)
        if date_m2:
            date_iso = _parse_es_date(date_m2.group(1), date_m2.group(2), None)
            label    = f"{date_iso}T{date_m2.group(3)}" if date_iso else date_m2.group(0).strip()
        else:
            date_iso = ""
            label    = page.title()

    return [{"session_id": "main", "label": label, "date": date_iso,
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

    # Extract date from body text: "viernes, 27 noviembre 2026"
    body_text = page.inner_text("body")
    date_m = re.search(
        r'(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)[,\s]+(\d+)\s+(\w+)\s+(\d{4})',
        body_text, re.IGNORECASE)
    if date_m:
        date_iso = _parse_es_date(date_m.group(1), date_m.group(2), date_m.group(3))
        label    = f"{date_iso}" if date_iso else date_m.group(0).strip()
    else:
        date_iso = ""
        label    = page.title()

    return [{"session_id": "main", "label": date_iso or label, "date": date_iso,
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

    # Collect ALL Janto codes in the page (page may list multiple events)
    api_codes = re.findall(r'apiw5\.janto\.es/[^/]+/sessions/([A-Z0-9]+)', html)
    standalone = re.findall(r'["\'/]([A-Z]\d{6}[A-Z]{2,})["\'/]', html)
    all_codes = list(dict.fromkeys(api_codes + standalone))  # deduplicate, keep order

    # Prefer code associated with the URL fragment (e.g. #web5) — look in that HTML section
    fragment = url.split("#")[-1] if "#" in url else ""
    if fragment:
        frag_m = re.search(
            rf'id=["\']?{re.escape(fragment)}["\']?[^>]*>[\s\S]{{0,2000}}?([A-Z]\d{{6}}[A-Z]{{2,}})',
            html
        )
        if frag_m and frag_m.group(1) in all_codes:
            frag_code = frag_m.group(1)
            all_codes = [frag_code] + [c for c in all_codes if c != frag_code]
            print(f"  Fragment #{fragment} → code {frag_code} (prioritised)")

    print(f"  Janto codes to try: {all_codes[:4]}...")

    # Referer required by Janto API — must match the venue domain
    from urllib.parse import urlparse
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    janto_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
        "Referer":    url,
        "Origin":     origin,
    }

    # Try each code with multiple endpoint variants
    data = None
    used_code = None
    for event_code in all_codes:
        for endpoint in [
            f"https://apiw5.janto.es/v5/sessions/{event_code}/full/01",
            f"https://apiw5.janto.es/v5/sessions/{event_code}/full",
            f"https://apiw5.janto.es/v5/sessions/{event_code}",
        ]:
            try:
                jr = requests.get(endpoint, headers=janto_headers, timeout=15)
                jr.raise_for_status()
                candidate = jr.json()
                print(f"  {event_code} {endpoint.split('sessions/')[1]} → 200, keys={list(candidate.keys()) if isinstance(candidate, dict) else f'list[{len(candidate)}]'}")
                # Accept any non-error JSON dict or non-empty list
                is_error = isinstance(candidate, dict) and candidate.get("error") and not candidate.get("sessionDate")
                if not is_error:
                    data = candidate
                    used_code = event_code
                    print(f"  Using code {event_code} → {endpoint.split('sessions/')[1]}")
                    break
            except Exception as e:
                print(f"  {event_code} {endpoint.split('sessions/')[1]} → {e}")
        if data is not None:
            break

    if data is None:
        print("  No valid Janto code found")
        return []

    # API returns {"sessions": {sessionId: {percentAvailable, maxTickets, desc3, ...}}, ...}
    # sessions is a dict — values are the full session objects, no extra API call needed
    if isinstance(data, dict) and "sessions" in data:
        sessions_val = data["sessions"]
        raw_sessions = list(sessions_val.values()) if isinstance(sessions_val, dict) else sessions_val
        print(f"  Event status: {data.get('status')} | sessions: {len(raw_sessions)}")
    else:
        raw_sessions = data if isinstance(data, list) else [data]

    results = []
    for s in raw_sessions:
        if not isinstance(s, dict):
            continue
        mt        = s.get("maxTickets") or {}
        available = mt.get("availableTickets", 0)
        pct_avail = float(s.get("percentAvailable", 1.0))

        # total = available / percentAvailable  (e.g. 499 / 0.998 ≈ 500)
        if 0 < pct_avail < 1:
            total = round(available / pct_avail)
        else:
            total = available

        sold = max(0, total - available)

        # Date is in desc3 field as "20261029214500" (YYYYMMDDHHMMSS)
        raw = str(s.get("desc3") or s.get("sessionDate") or "")
        if len(raw) >= 12:
            date_iso = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            label    = f"{date_iso}T{raw[8:10]}:{raw[10:12]}"  # ISO for frontend formatDate()
        else:
            label    = s.get("InfoEvSes1", "") or raw
            date_iso = ""

        session_id = str(s.get("idSession") or s.get("sessionDate") or "main")
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
# Angular app. Navigate to the event URL + ?step=2 with Playwright so Angular
# fires the real selbutacav2 call (the static HTML has sesion=12345 placeholder).
# Intercept the API response to parse sold vs available seats.

def scrape_reservaentradas(page, url):
    # Build step=2 URL from whatever is stored in the DB
    base = url.rstrip("/")
    target = base + ("&step=2" if "?" in base else "?step=2")
    if "step=2" in base:
        target = base  # already has it

    api_body = []

    def on_response(resp):
        # Capture selbutacav2 AND any other reservaentradas API that might give real session
        if "reservaentradas.com" in resp.url and resp.request.resource_type in ("xhr", "fetch"):
            try:
                api_body.append((resp.url, resp.body().decode("utf-8", errors="replace")))
            except: pass

    page.on("response", on_response)
    page.goto(target, timeout=35000)
    page.wait_for_load_state("networkidle", timeout=25000)
    page.wait_for_timeout(5000)

    # Accept cookies if present
    try:
        btn = page.query_selector("button:has-text('Aceptar')")
        if btn and btn.is_visible():
            btn.click(); page.wait_for_timeout(1000)
    except: pass

    # ── Log all captured API calls (useful for debugging) ─────────────────────
    print(f"  Captured {len(api_body)} API responses")
    for api_url, body in api_body:
        print(f"  API: {api_url[-80:]}")
        print(f"  Body: {body[:200]}")

    # ── Try parsing the selbutacav2 API response ──────────────────────────────
    for api_url, body in api_body:
        if "selbutacav2" not in api_url and "selbutaca" not in api_url:
            continue

        # Format A: XML  <I id="N" [O="201"] .../>
        seats = re.findall(r'<I\s[^/]*/>', body)
        if seats:
            libre = sold = 0
            for tag in seats:
                o = re.search(r'O="(\d+)"', tag)
                if not o:
                    libre += 1
                elif o.group(1) == "201":
                    sold += 1
            total = libre + sold
            print(f"  XML parse: libre={libre}, sold={sold}, total={total}")
            if total > 0:
                label = _reserva_label(page)
                return [{"session_id": "main", "label": label, "date": "2026-05-30",
                         "capacity": total, "sold": sold, "reserved": 0}]

        # Format B: JSON array
        try:
            seats_json = json.loads(body)
            if isinstance(seats_json, list) and seats_json:
                sold  = sum(1 for s in seats_json if str(s.get("estado","")).lower() in ("ocupada","vendida","sold","1"))
                total = len(seats_json)
                print(f"  JSON parse: total={total}, sold={sold}")
                if total > 0:
                    label = _reserva_label(page)
                    return [{"session_id": "main", "label": label, "date": "2026-05-30",
                             "capacity": total, "sold": sold, "reserved": 0}]
        except: pass

    # ── Fallback: count seats by rendered fill colour via DOM ─────────────────
    print("  Inspecting rendered DOM for seat colours")
    counts = page.evaluate("""() => {
        // cursorPointer + butaca1 is the exact class combo for standard seats
        const byClass = [...document.querySelectorAll('.cursorPointer.butaca1')];
        // If Angular changed the markup, also try butacadetect
        const byDetect = byClass.length > 0 ? byClass
                         : [...document.querySelectorAll('.butacadetect')];
        let total = byDetect.length, sold = 0;
        byDetect.forEach(el => {
            // Check SVG child fill OR computed background
            const child = el.querySelector('rect,circle,path') || el;
            const fill  = (child.getAttribute('fill') || '').toLowerCase();
            const style = window.getComputedStyle(child);
            const bg    = style.fill || style.backgroundColor || '';
            // SVG className is SVGAnimatedString — must use getAttribute
            const cls   = (el.getAttribute('class') || '').toLowerCase();
            // Red-ish: high R, low G  e.g. rgb(200,30,30)
            const rgbM  = bg.match(/rgb[(](\\d+),\\s*(\\d+),\\s*(\\d+)[)]/u);
            const isRed = rgbM ? (parseInt(rgbM[1]) > 150 && parseInt(rgbM[2]) < 80) : false;
            if (isRed || fill === 'red' || fill === '#e53935' || fill === '#c62828' ||
                cls.includes('ocupad') || cls.includes('vendid')) {
                sold++;
            }
        });
        return {total, sold, selector: byClass.length > 0 ? 'cursorPointer.butaca1' : 'butacadetect'};
    }""")
    total = counts["total"]
    sold  = counts["sold"]
    print(f"  DOM ({counts['selector']}): total={total}, sold={sold}")
    if total == 0:
        print("  No seat data found")
        return []

    label = _reserva_label(page)
    return [{"session_id": "main", "label": label, "date": "2026-05-30",
             "capacity": total, "sold": sold, "reserved": 0}]


def _reserva_label(page):
    try:
        body = page.inner_text("body")
        m = re.search(r'\d{1,2}/\d{2}/\d{4}\s+\d{2}:\d{2}', body)
        return m.group(0) if m else page.title()
    except:
        return "30/05/2026 20:00"


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
