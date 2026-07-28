"""
GitHub Actions scraper for JS-heavy ticket platforms.
Findings:
 - todaslasentradas.com: classes mapaLibre / mapaOcupada in HTML
 - bacantix.com:  MCIAjax.aspx response XML — O attr absent=libre, O=201=vendida
 - reservaentradas.com: Angular, need to navigate base→click Butacas step, then count butaca1
"""
import os, json, re, sys, requests, datetime, concurrent.futures
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
try:
    from playwright_stealth import stealth_sync as _stealth
except ImportError:
    _stealth = None
try:
    from camoufox.sync_api import Camoufox as _Camoufox
except ImportError:
    _Camoufox = None

MESES = {"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
         "julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

# Full browser UA — some APIs (api.baila.pro gateway) reject the short "Mozilla/5.0" string
FULL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

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
    page.wait_for_timeout(5000)  # extra wait — page has JS queue + dynamic rendering

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

    # Debug: if still 0, log what's on the page to diagnose
    if total == 0:
        page_url   = page.url
        page_title = page.title()
        print(f"  Page URL after load: {page_url}")
        print(f"  Page title: {page_title}")
        rel_classes = page.evaluate("""() => {
            const s = new Set();
            document.querySelectorAll('[class]').forEach(e => {
                (e.getAttribute('class') || '').split(' ').forEach(c => {
                    if (c && (c.includes('mapa') || c.includes('asiento') ||
                              c.includes('butaca') || c.includes('sesion') ||
                              c.includes('queue') || c.includes('waiting')))
                        s.add(c);
                });
            });
            return [...s].slice(0, 30);
        }""")
        print(f"  Relevant classes on page: {rel_classes}")

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
# MCIAjax.aspx XML contains:
#   <I id="N" O="orientation" .../> — one per seat; O = rotation, NOT state
#   <E Estados="111311..."/>        — compact string; position N = state of seat id N
#                                     '1'=libre, anything else = vendida/bloqueada
# Source: reverse-engineered from Control.js MapeaEstados() function.

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

    # Get seat IDs from <I id="N" .../> elements
    seat_ids = [int(i) for i in re.findall(r'<I id="(\d+)"', body)]

    # Get the Estados string from <E Estados="..."/>
    estados_m = re.search(r'<E\s[^>]*Estados="([^"]*)"', body)
    if not estados_m:
        print("  <E Estados=...> not found in MCIAjax")
        # Fallback: log sample XML for debugging
        print(f"  XML sample: {body[:300]}")
        return []

    estados = estados_m.group(1)
    print(f"  Estados string length={len(estados)}, seats={len(seat_ids)}")

    libre = sold = 0
    for sid in seat_ids:
        if sid < len(estados):
            state = estados[sid]
            if state == "1":
                libre += 1
            elif state == "3":   # E=3 = Venta (sold) — shown RED on seat map
                sold += 1
            # E=2 bloqueado, E=4 protocolo, E=14 exclusión → skip (admin holds, not sold)

    total = libre + sold
    print(f"  Libre={libre}, Vendidas(E=3)={sold}, Total={total}")

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

# auditoriocartuja.com serves GitHub Actions runners a ~12 KB block page instead of
# the real 400 KB one (datacenter IPs are WAF-filtered — Playwright gets blocked too),
# so no Janto code can be discovered from there. The Janto API itself answers fine.
# Codes follow the pattern A + DDMMYY + SHOWNAME, so a new show needs a new entry here.
# Discovery from the page still runs first and wins whenever it works.
_JANTO_FALLBACK_CODES = {
    "auditoriocartuja.com": ["A291026HIPNOSTIS"],   # Sevilla, 29 Oct 2026
}


def _janto_codes(html):
    """Collect ALL Janto codes in the page (page may list multiple events)."""
    api_codes = re.findall(r'apiw5\.janto\.es/[^/]+/sessions/([A-Z0-9]+)', html)
    standalone = re.findall(r'["\'/]([A-Z]\d{6}[A-Z]{2,})["\'/]', html)
    return list(dict.fromkeys(api_codes + standalone))  # deduplicate, keep order


def scrape_auditoriocartuja(page, url):
    html = ""
    try:
        resp = requests.get(url, headers={"User-Agent": FULL_UA}, timeout=15)
        print(f"  Page fetch (requests): HTTP {resp.status_code}, {len(resp.text)} bytes, final={resp.url[:80]}")
        html = resp.text
    except Exception as e:
        print(f"  HTTP error: {e}")

    all_codes = _janto_codes(html)

    # GH Actions datacenter IPs sometimes get a WAF page via requests — retry with real browser
    if not all_codes:
        print("  No Janto codes via requests — retrying with Playwright browser")
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            html = page.content()
            all_codes = _janto_codes(html)
            print(f"  Browser fetch: {len(html)} bytes, codes found: {len(all_codes)}")
        except Exception as e:
            print(f"  Browser fallback error: {e}")

    if not all_codes:
        for domain, codes in _JANTO_FALLBACK_CODES.items():
            if domain in url:
                all_codes = list(codes)
                print(f"  Page blocked — using known codes for {domain}: {all_codes}")
                break

    if not all_codes:
        print("  No Janto codes found at all")
        return []

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
# Reverse-engineered: page calls sesionv2 on a venue subdomain.
# URL: https://{slug}.reservaentradas.com/{slug}/sesionv2?recinto={id}&sesion={eventId}&key=apirswebphp
# Returns Aforo (total) and Disponibles (available) → sold = Aforo - Disponibles
# No Playwright needed — pure HTTP.

def scrape_reservaentradas(_, url):
    # Extract venue slug and event ID from URL
    # Pattern: /entrada/{city}/{venue_slug}/{event_slug}/{event_id}/
    m = re.search(r'/entrada/[^/]+/([^/]+)/[^/]+/(\d+)', url)
    if not m:
        print("  Could not parse venue slug / event ID from URL")
        return []
    venue_slug = m.group(1)   # e.g. "teatrocinesortega"
    event_id   = m.group(2)   # e.g. "18636"
    print(f"  venue={venue_slug}, event_id={event_id}")

    # Get recinto ID from the page HTML (appears in selbutacav2 URL in the source)
    try:
        page_resp = requests.get(
            f"https://www.reservaentradas.com/entrada/sessionone/buy/{venue_slug}/tickets/{event_id}",
            headers={"User-Agent": "Mozilla/5.0", "Referer": url}, timeout=15
        )
        recinto_m = re.search(r'recinto=(\d+)', page_resp.text)
        recinto = recinto_m.group(1) if recinto_m else "0"
    except Exception as e:
        print(f"  Could not fetch page for recinto: {e}")
        return []

    print(f"  recinto={recinto}")
    if recinto == "0":
        print("  recinto not found in page")
        return []

    # Call the real sesionv2 API
    api_url = (f"https://{venue_slug}.reservaentradas.com/{venue_slug}/sesionv2"
               f"?recinto={recinto}&UUID=scraper&sesion={event_id}&referer=&key=apirswebphp")
    try:
        jr = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0", "Referer": url}, timeout=15)
        data = jr.json()
    except Exception as e:
        print(f"  sesionv2 error: {e}")
        return []

    # Aforo and Disponibles live inside the Sesion sub-object
    sesion     = data.get("Sesion") or {}
    aforo      = sesion.get("Aforo", 0)
    disponible = sesion.get("Disponibles", 0)
    sold       = max(0, aforo - disponible)
    print(f"  sesionv2: aforo={aforo}, disponibles={disponible}, sold={sold}")

    if aforo == 0:
        # Log top-level keys for debugging unexpected structure
        print(f"  sesionv2 top keys: {list(data.keys())[:10]}")
        print(f"  Sesion keys: {list(sesion.keys())[:10]}")
        print("  No seat data in sesionv2")
        return []

    # Date from Sesion.FechaSesion ("30/05/2026") + Sesion.Horatxt ("20:00")
    fecha    = sesion.get("FechaSesion") or sesion.get("Fecha") or ""
    hora     = (sesion.get("Horatxt") or sesion.get("Hora") or "").strip()
    dm = re.match(r'(\d{1,2})/(\d{2})/(\d{4})', fecha)
    if dm:
        date_iso = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1).zfill(2)}"
        label    = f"{date_iso}T{hora}" if hora else date_iso
    else:
        date_iso = ""
        label    = fecha or event_id

    return [{"session_id": event_id, "label": label, "date": date_iso,
             "capacity": aforo, "sold": sold, "reserved": 0}]


# ── ctickets.es ──────────────────────────────────────────────────────────────
# Fully server-rendered — NO Playwright needed (verified jul 2026).
# Each zone's seat map has its own GET URL: /comprar_entradas/{event}/{zone}
# That URL works for sold-out zones too, so the old "inject a hidden input and
# submit the form" Playwright hack is obsolete. Seat classes: libre / ocupada.
# Counts verified identical to the Playwright version (León 772 aforo / 129 vendidas).

def scrape_ctickets(_, url):
    base = url.rstrip("/")
    sess = requests.Session()
    sess.headers.update({"User-Agent": FULL_UA, "Accept-Language": "es-ES,es;q=0.9"})

    try:
        html = sess.get(base, timeout=20).text
    except Exception as e:
        print(f"  HTTP error fetching event page: {e}")
        return []

    # ── Collect zone IDs ──────────────────────────────────────────────────────
    avail_ids = re.findall(r'<input[^>]+radioZona[^>]+value="(\d+)"', html)

    # Sold-out zones have no radio button but <label for="id_XXXXX"> reveals the ID
    sold_ids = []
    for m in re.finditer(r'class=["\']?zonacompleta["\']?', html):
        snippet  = html[m.start():m.start() + 600]
        label_m  = re.search(r'<label\s+for="id_(\d+)"', snippet)
        if label_m:
            sold_ids.append(label_m.group(1))

    print(f"  zonas disponibles={len(avail_ids)}, agotadas={len(sold_ids)}, "
          f"total={len(avail_ids) + len(sold_ids)}")

    def _zone_seats(zone_id):
        """GET a zone's seat map and count free/occupied seats."""
        zr = sess.get(f"{base}/{zone_id}", headers={"Referer": base}, timeout=20)
        libre   = len(re.findall(r'class="[^"]*\blibre\b[^"]*"', zr.text))
        ocupada = len(re.findall(r'class="[^"]*\b(?:ocupada|reservada)\b[^"]*"', zr.text))
        return libre, ocupada

    seat_total = seat_avail = 0
    for zone_id in avail_ids + sold_ids:
        tag = " (agotada)" if zone_id in sold_ids else ""
        try:
            libre, ocupada = _zone_seats(zone_id)
            print(f"  Zona {zone_id}{tag}: libre={libre}, ocupada={ocupada}")
            seat_avail += libre
            seat_total += libre + ocupada
        except Exception as e:
            print(f"  Zona {zone_id}{tag} error: {e}")

    # ── Compute totals ────────────────────────────────────────────────────────
    capacity = seat_total
    sold     = seat_total - seat_avail
    print(f"  Seat data ({len(avail_ids)} disponibles + {len(sold_ids)} agotadas): "
          f"total={capacity}, sold={sold}")

    if capacity == 0:
        print("  No data found")
        return []

    # Date from JSON-LD
    date_iso = label = ""
    jld_m = re.search(r'"startDate"\s*:\s*"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})', html)
    if jld_m:
        date_iso = jld_m.group(1)
        label    = f"{date_iso}T{jld_m.group(2)}"

    sid_m = re.search(r'/(\d+)(?:/|$)', url)
    session_id = sid_m.group(1) if sid_m else "main"

    return [{"session_id": session_id, "label": label, "date": date_iso,
             "capacity": capacity, "sold": sold, "reserved": 0}]



# ── patronbase.com ────────────────────────────────────────────────────────────
# Server-rendered HTML — no Playwright needed.
# Seat classes: pb_pyos_free (available), pb_pyos_held (blocked/sold).
# pb_pyos_held includes admin invitation blocks → needs sold_baseline like ctickets.
# URL format: https://es.patronbase.com/_VENUE/Sections/Choose?prod_id=X&perf_id=Y&submit=Continuar

def scrape_patronbase(_, url):
    from urllib.parse import urlparse, parse_qs

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9",
    }

    parsed     = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    venue_path = path_parts[0]   # e.g. "_AuditorioBaranain"
    params     = parse_qs(parsed.query)
    base_url   = f"{parsed.scheme}://{parsed.netloc}"

    # Support both URL formats:
    #   .../Sections/Choose?prod_id=2635&perf_id=1  (from manual entry)
    #   .../Productions/2635/Performances           (from showsaryel.com auto-discovery)
    prod_id = params.get("prod_id", [""])[0]
    perf_id = params.get("perf_id", [""])[0]

    if not prod_id:
        # Try extracting prod_id from path: /.../_VENUE/Productions/2635/Performances
        prod_m = re.search(r"/Productions/(\d+)", parsed.path)
        if not prod_m:
            print("  Could not extract prod_id from URL")
            return []
        prod_id = prod_m.group(1)

    if not perf_id:
        # Fetch Performances page to get the first available perf_id
        perf_url = f"{base_url}/{venue_path}/Productions/{prod_id}/Performances"
        try:
            perf_html = requests.get(perf_url, headers=headers, timeout=15).text
            perf_m    = re.search(r"name=['\"]perf_id['\"][^>]+value=['\"](\d+)['\"]", perf_html)
            perf_id   = perf_m.group(1) if perf_m else "1"
        except Exception as e:
            print(f"  Could not fetch Performances page: {e}")
            perf_id = "1"
        print(f"  prod_id={prod_id}, perf_id={perf_id}")

    # Fetch the sections page to discover section_id and seat types
    sections_url = f"{base_url}/{venue_path}/Sections/Choose?prod_id={prod_id}&perf_id={perf_id}&submit=Continuar"
    try:
        html = requests.get(sections_url, headers=headers, timeout=15).text
    except Exception as e:
        print(f"  HTTP error fetching sections: {e}")
        return []

    section_id_m = re.search(r"section_id=['\"](\w+)['\"]", html)
    section_id   = section_id_m.group(1) if section_id_m else "PLAT"

    # Extract (code, display_name) for each seat type — skip SR (wheelchair)
    seat_types = []
    for div_m in re.finditer(r"<div class='seattype[^>]*>([\s\S]*?)</div>", html):
        div_html = div_m.group(1)
        val_m    = re.search(r"value=['\"](\w+)['\"]", div_html)
        if not val_m:
            continue
        code   = val_m.group(1)
        name_m = re.search(r"/>\s*([\w\s\-áéíóúÁÉÍÓÚñÑ]+?)\s*</label>", div_html, re.DOTALL)
        name   = name_m.group(1).strip() if name_m else code
        if code != "SR":
            seat_types.append((code, name))

    print(f"  section_id={section_id}, seat_types={seat_types}")
    if not seat_types:
        print("  No seat types found")
        return []

    # Abbreviated month mapping ("nov" → "11")
    MESES_ABREV = {k[:3]: v for k, v in MESES.items()}

    results = []
    for seat_code, seat_name in seat_types:
        map_url = (f"{base_url}/{venue_path}/Seats/ChooseMyOwn"
                   f"?prod_id={prod_id}&perf_id={perf_id}"
                   f"&section_id={section_id}&seat_type_id={seat_code}")
        try:
            map_html = requests.get(map_url, headers=headers, timeout=15).text
        except Exception as e:
            print(f"  HTTP error for {seat_code}: {e}")
            continue

        free_count = len(re.findall(
            rf'class="pb_pyos_seat pb_pyos_free pb_pyos_seat_type_{seat_code}"', map_html
        ))
        held_count = len(re.findall(
            rf'class="pb_pyos_seat pb_pyos_held pb_pyos_seat_type_{seat_code}"', map_html
        ))
        total = free_count + held_count
        print(f"  {seat_code} ({seat_name}): free={free_count}, held={held_count}, total={total}")

        if total == 0:
            print(f"  No seat data for {seat_code}")
            continue

        # Date in pb_value span inside pb_event_attribute_date: "21 de nov de 2026, 18:00"
        date_m = re.search(
            r'pb_event_attribute_date[\s\S]*?pb_value[^>]*>\s*'
            r'(\d+)\s+de\s+(\w+)\s+de\s+(\d{4})[,\s]+(\d{2}:\d{2})',
            map_html, re.DOTALL | re.IGNORECASE
        )
        if date_m:
            day, mon, year, t = date_m.group(1), date_m.group(2).lower(), date_m.group(3), date_m.group(4)
            month_code = MESES.get(mon) or MESES_ABREV.get(mon[:3], "")
            date_iso   = f"{year}-{month_code}-{day.zfill(2)}" if month_code else ""
        else:
            date_iso = ""

        results.append({
            "session_id": seat_code,           # "BUT" / "PALC"
            "label":      seat_name,           # "Butaca" / "Palco" — shown on dashboard
            "date":       date_iso,            # "2026-11-21" for sorting
            "capacity":   total,
            "sold":       held_count,          # includes invitation blocks → baseline needed
            "reserved":   0,
        })

    return results



# ── ukalarimenorcaevents.com (baila.pro API) ─────────────────────────────────
# React SPA. Primary: Playwright intercepts GET /organizations/{org}/events/{ev}/stores/{store}
# and capacityses endpoints. Fallback: POST /events/list via requests.
# Constants hardcoded in JS bundle (index-3b2cb63f.js):
#   store=4ef7b2c1-0f36-42c0-b33c-2c8a512a2f91, org=95f94967-30aa-454f-a070-78c790c6625c
#   apiKey=026e7da582c94921a8be3a963cbe33d0 (Ocp-Apim-Subscription-Key)
# Azure App Gateway blocks GET endpoints by IP — needs real browser TLS fingerprint.

_UKALARI_STORE = "4ef7b2c1-0f36-42c0-b33c-2c8a512a2f91"
_UKALARI_ORG   = "95f94967-30aa-454f-a070-78c790c6625c"
_UKALARI_KEY   = "026e7da582c94921a8be3a963cbe33d0"
_UKALARI_BASE  = "https://api.baila.pro/api/fan"

def scrape_ukalarimenorca(page, url):
    api_data = {}   # path_suffix → parsed JSON body

    def on_response(resp):
        if "api.baila.pro" not in resp.url:
            return
        try:
            body    = resp.json()
            suffix  = resp.url.split("api.baila.pro")[-1]
            api_data[suffix] = body
        except Exception:
            pass

    page.on("response", on_response)
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    print(f"  Intercepted {len(api_data)} api.baila.pro calls:")
    for path in api_data:
        print(f"    {path[:90]}")

    capacity = 0
    sold     = 0

    def _find_capacity(obj, depth=0):
        """Recursively look for capacity/available fields in nested API responses."""
        if depth > 5:
            return None
        if isinstance(obj, dict):
            cap   = (obj.get("TotalSeats") or obj.get("Capacity")
                     or obj.get("totalSeats") or obj.get("capacity") or 0)
            avail = (obj.get("AvailableSeats") or obj.get("Available")
                     or obj.get("availableSeats") or obj.get("available") or 0)
            if cap:
                return int(cap), int(avail)
            for v in obj.values():
                found = _find_capacity(v, depth + 1)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _find_capacity(item, depth + 1)
                if found:
                    return found
        return None

    # Look for capacity data in any intercepted response (also nested, e.g. Data[].Sessions[])
    for path, body in api_data.items():
        found = _find_capacity(body)
        if found:
            capacity, avail = found
            sold = max(0, capacity - avail)
            print(f"  Capacity from {path[:60]}: total={capacity}, avail={avail}, sold={sold}")
            break

    if not capacity:
        print("  No capacity in intercepted calls — logging raw body samples for debugging:")
        for path, body in list(api_data.items())[:3]:
            sample = str(body)[:200]
            print(f"    [{path[:50]}] {sample}")

    # Extract date from URL slug: ...-YYYY-MM-DD
    slug      = url.rstrip("/").split("/")[-1]
    slug_date = re.search(r"(\d{4})-(\d{2})-(\d{2})$", slug)
    if slug_date:
        date_iso = f"{slug_date.group(1)}-{slug_date.group(2)}-{slug_date.group(3)}"
    else:
        date_iso = ""

    # Also try POST events/list (works without browser, use for date/time)
    # NOTE: the baila.pro API gateway rejects the short "Mozilla/5.0" UA — needs FULL_UA
    time_str = "20:30"
    try:
        hdrs = {
            "User-Agent": FULL_UA,
            "Ocp-Apim-Subscription-Key": _UKALARI_KEY,
            "x-api-version": "8",
            "Content-Type": "application/json",
            "Origin": "https://entradas.ukalarimenorcaevents.com",
            "Referer": "https://entradas.ukalarimenorcaevents.com/",
        }
        r = requests.post(f"{_UKALARI_BASE}/events/list",
                          json={"StoreIds": [_UKALARI_STORE], "OrganizationIds": [_UKALARI_ORG]},
                          headers=hdrs, timeout=15)
        if r.text.strip():
            ev = next((e for e in r.json().get("Data", []) if e.get("ShortLink") == slug), None)
            if ev:
                for sess in ev.get("Sessions", []):
                    start = sess.get("StartDate", "")
                    if start:
                        date_iso = start[:10]
                        time_str = start[11:16]
                        break
        else:
            print("  events/list fallback: empty response (tickets may not be on sale yet)")
    except Exception as e:
        print(f"  events/list fallback error: {e}")

    if not capacity:
        # baila.pro no longer exposes numeric availability publicly (only HasAvailability).
        # Don't save a fake 0/0 session — leave the event as "pending" on the dashboard.
        print("  No numeric capacity available — skipping (not saving 0/0)")
        return []

    label = f"{date_iso}T{time_str}" if date_iso else slug
    return [{
        "session_id": slug,
        "label":      label,
        "date":       date_iso,
        "capacity":   capacity,
        "sold":       sold,
        "reserved":   0,
    }]


# ── tickets.oneboxtds.com ────────────────────────────────────────────────────
# Angular SPA behind Cloudflare Turnstile. Playwright passes the challenge automatically.
# API endpoint: /api/events/{id} — returns event detail with seat availability.
# URL format: https://tickets.oneboxtds.com/{venue}/events/{eventId}

_OBX_CAP_KEYS   = ("totalcapacity", "capacity", "totalseats", "aforo", "totaltickets",
                   "maxcapacity", "totalstock", "seatstotal")
_OBX_AVAIL_KEYS = ("availableseats", "availabletickets", "remainingseats", "seatsavailable",
                   "freeseats", "remainingtickets", "stock", "available", "remaining")
_OBX_SOLD_KEYS  = ("soldseats", "soldtickets", "occupiedseats", "sold", "occupied")


def _obx_deep_find(obj, names, depth=0):
    """Find the first NUMERIC value whose key matches any of `names` (case-insensitive)."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in names and isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
        for v in obj.values():
            found = _obx_deep_find(v, names, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _obx_deep_find(item, names, depth + 1)
            if found is not None:
                return found
    return None


def _obx_session_items(body):
    """Normalise a sessions payload into a list of session dicts."""
    if isinstance(body, list):
        return [s for s in body if isinstance(s, dict)]
    if isinstance(body, dict):
        for key in ("items", "data", "content", "sessions", "results", "elements"):
            val = body.get(key)
            if isinstance(val, list):
                return [s for s in val if isinstance(s, dict)]
        return [body]
    return []


def _parse_oneboxtds_responses(api_data, url):
    """Parse intercepted oneboxtds API responses and return sessions list."""
    event_id_m = re.search(r"/events/(\d+)", url)
    event_id   = event_id_m.group(1) if event_id_m else "main"

    for path in api_data:
        print(f"  [{path[:70]}]")

    # The sessions endpoint carries per-session availability:
    #   /channels-api/v1/catalog/events/{id}/sessions?limit=..&offset=..&type=SESSION
    sessions_body = next(
        (b for p, b in api_data.items() if "/sessions" in p and "catalog" in p), None
    )
    if sessions_body is None:
        sessions_body = next((b for p, b in api_data.items() if "/sessions" in p), None)

    def _num(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    results = []
    for s in _obx_session_items(sessions_body):
        # Onebox keeps the real numbers in the session's availability object:
        #   "availability": {"type": "BOUNDED", "total": 888, "available": 732}
        # Read it directly — a blind deep search would also match the payload's
        # pagination "metadata": {"total": 1}.
        availability = s.get("availability") if isinstance(s.get("availability"), dict) else {}
        cap   = _num(availability.get("total"))     or _obx_deep_find(s, _OBX_CAP_KEYS)
        avail = _num(availability.get("available"))
        if avail is None:
            avail = _obx_deep_find(s, _OBX_AVAIL_KEYS)
        sold  = _obx_deep_find(s, _OBX_SOLD_KEYS)

        if cap is None and avail is not None and sold is not None:
            cap = avail + sold
        if cap is None:
            continue
        if sold is None:
            sold = max(0, cap - (avail or 0))

        # Date is a nested object too: {"start": "2026-08-02T22:00:00+02:00", ...}
        raw_date = ""
        date_val = s.get("date")
        if isinstance(date_val, dict):
            raw_date = str(date_val.get("start") or "")
        elif isinstance(date_val, str):
            raw_date = date_val
        if not re.match(r"\d{4}-\d{2}-\d{2}", raw_date):
            raw_date = ""
            for key in ("startDate", "startDateTime", "sessionDate", "eventDate", "start"):
                val = s.get(key)
                if isinstance(val, str) and re.match(r"\d{4}-\d{2}-\d{2}", val):
                    raw_date = val
                    break
        date_iso = raw_date[:10]
        time_m   = re.search(r"T(\d{2}:\d{2})", raw_date)
        label    = f"{date_iso}T{time_m.group(1)}" if (date_iso and time_m) else (date_iso or event_id)

        sid = s.get("id") or s.get("sessionId") or event_id
        print(f"  Session {label}: total={cap}, avail={avail}, sold={sold}")
        results.append({
            "session_id": str(sid),
            "label":      label,
            "date":       date_iso,
            "capacity":   int(cap),
            "sold":       int(sold),
            "reserved":   0,
        })

    if results:
        return results

    # Nothing parsed — dump the interesting bodies IN FULL so the schema can be mapped.
    print("  No capacity fields found — dumping catalog/session responses:")
    for path, body in api_data.items():
        if "catalog" in path or "/sessions" in path:
            print(f"    [{path[:70]}] {json.dumps(body, ensure_ascii=False)[:4000]}")
    print("  No capacity — skipping (not saving 0/0)")
    return []


def _camoufox_worker(url):
    """Runs camoufox in an isolated thread — avoids asyncio conflict with sync_playwright."""
    from camoufox.sync_api import Camoufox
    api_data  = {}
    all_calls = []

    def on_response(resp):
        all_calls.append((resp.url, resp.status))
        if "oneboxtds.com" not in resp.url:
            return
        try:
            body   = resp.json()
            suffix = resp.url.split("oneboxtds.com")[-1]
            api_data[suffix] = body
        except Exception:
            pass

    # headless="virtual" runs under Xvfb (installed in the workflow) — Cloudflare
    # detects pure headless mode; a virtual display passes the challenge far more often
    with Camoufox(headless="virtual", geoip=True) as browser:
        page = browser.new_page()
        page.on("response", on_response)
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)

        # If CF challenge is showing, wait actively for it to resolve (up to 40s)
        title = page.title()
        if "Just a moment" in title or "Attention Required" in title:
            print(f"  CF challenge detected ('{title}') — waiting for resolution...")
            try:
                page.wait_for_function(
                    "!document.title.includes('Just a moment') && "
                    "!document.title.includes('Attention Required')",
                    timeout=40000,
                )
                page.wait_for_load_state("networkidle", timeout=15000)
                print(f"  CF challenge resolved → '{page.title()}'")
            except Exception as e:
                print(f"  CF challenge did not resolve: {e}")

        page.wait_for_timeout(5000)   # let Angular hydrate and fire API calls

        print(f"  Page after load: URL={page.url[:80]}  title={page.title()[:60]}")
        print(f"  Total network calls: {len(all_calls)}")
        print(f"  Intercepted {len(api_data)} oneboxtds.com calls:")
        for path in api_data:
            print(f"    {path[:80]}")

        if not api_data:
            domains = sorted({u.split("/")[2] for u, _ in all_calls if "/" in u})
            print(f"  Domains seen: {domains[:15]}")
            print(f"  HTML sample: {page.content()[:300]}")

    return api_data


def scrape_oneboxtds(_page, url):
    # camoufox must run in a separate thread — its sync_api uses asyncio internally,
    # which conflicts with sync_playwright's event loop if called from the same thread.
    if _Camoufox is None:
        print("  camoufox not installed — cannot bypass Cloudflare")
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        try:
            api_data = ex.submit(_camoufox_worker, url).result(timeout=120)
        except Exception as e:
            print(f"  camoufox error: {e}")
            return []

    return _parse_oneboxtds_responses(api_data, url)


SCRAPERS = {
    "todaslasentradas":  scrape_todaslasentradas,
    "bacantix":          scrape_bacantix,
    "reservaentradas":   scrape_reservaentradas,
    "auditoriocartuja":  scrape_auditoriocartuja,
    "ctickets":          scrape_ctickets,
    "patronbase":        scrape_patronbase,
    "ukalarimenorca":    scrape_ukalarimenorca,
    "oneboxtds":         scrape_oneboxtds,
}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    events  = get_active_events()
    targets = [e for e in events if e.get("platform") in SCRAPERS]

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        if _stealth:
            _stealth(page)

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
