# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Monitor de Entradas — Aryel Altamar**  
A Next.js web app that tracks ticket sales across multiple Spanish theatres for the performer Aryel Altamar. Deployed on Vercel. GitHub Actions runs a Playwright scraper every 10 minutes for JS-heavy platforms.

Live: `https://teatrosaryel.vercel.app`  
Repo: `https://github.com/magoaryel/Teatros_Entradas`

## Commands

```bash
npm run dev      # local dev server (needs DATABASE_URL in .env.local)
npm run build    # production build (run before pushing)
npm start        # production server
```

## Architecture

**Frontend + API**: Next.js 15 App Router on Vercel (free tier)  
**Database**: Neon PostgreSQL serverless (`@neondatabase/serverless`)  
**Scraping (Vercel)**: Plain `fetch()` — works for gruposmedia.com which embeds `arraySesiones` in raw HTML  
**Scraping (GitHub Actions)**: Playwright on Ubuntu, runs every 10 min, calls `/api/ingest` to save data

### Data flow

```
showsaryel.com ──sync──► events table (auto-discovered)
gruposmedia.com ──fetch──► /api/cron/scrape (Vercel) ──► snapshots
bacantix/todaslasentradas/ctickets ──playwright──► GitHub Actions ──► /api/ingest ──► snapshots
reservaentradas/auditoriocartuja ──HTTP──► GitHub Actions ──► /api/ingest ──► snapshots
```

### Key files

- `lib/scraper.ts` — gruposmedia scraper (reads `arraySesiones` from HTML)
- `lib/syncShows.ts` — discovers shows from showsaryel.com/gira/
- `lib/runScrape.ts` — shared scrape+notify logic for Vercel
- `lib/db.ts` — all DB queries (Neon)
- `lib/telegram.ts` — Telegram notifications via env vars
- `scripts/scrape_external.py` — GitHub Actions scraper (Playwright + requests)
- `.github/workflows/scrape.yml` — GH Actions cron (every 10 min)
- `app/api/ingest/route.ts` — receives data from GitHub Actions
- `app/api/sync/route.ts` — syncs events from showsaryel.com
- `app/api/debug/route.ts` — shows DB state at `/api/debug`

### Ticket platforms

| Platform | Method | Notes |
|---|---|---|
| `gruposmedia` | Vercel fetch | `arraySesiones` in HTML, includes sold counts |
| `todaslasentradas` | GitHub Actions Playwright | CSS classes `mapaLibre` / `mapaOcupada` |
| `bacantix` | GitHub Actions Playwright | MCIAjax.aspx XML — `<E Estados="..."/>` string, pos N = state of seat id N; `'1'`=libre, `'3'`=vendida (NOT O attr, which is orientation) |
| `reservaentradas` | GitHub Actions HTTP | `sesionv2` API on venue subdomain: `https://{slug}.reservaentradas.com/{slug}/sesionv2?recinto=X&sesion=EVENT_ID&key=apirswebphp` — returns `Sesion.Aforo` and `Sesion.Disponibles` |
| `auditoriocartuja` | GitHub Actions HTTP | Janto API: `apiw5.janto.es/v5/sessions/{code}/full/01` — requires Referer header; `sessions` is a dict not a list |
| `ctickets` | GitHub Actions Playwright | Server-rendered HTML; click each available zone → count `.libre` / `.ocupada` CSS classes. Sold-out zones have `class="zonacompleta"` |

### TICKET_DOMAINS (syncShows.ts)
Events are auto-discovered from showsaryel.com/gira/ only when ticket URLs belong to these domains:
`gruposmedia.com`, `entradas.plus`, `todaslasentradas.com`, `bacantix.com`, `reservaentradas.com`, `auditoriocartuja.com`, `ctickets.es`, `atrapalo.com`, `ticketmaster.es`, `eventbrite.es`, `wegow.com`, `fever.com`

### formatDate() rule (app/page.tsx)
Only parses strings starting with `\d{4}-\d{2}-\d{2}` (ISO format). All scrapers must store labels as ISO datetime `"YYYY-MM-DDTHH:MM"` — non-ISO strings are returned as-is to avoid wrong year bugs (e.g. year 2001).

### upsertSession ON CONFLICT
Updates `session_label`, `session_date`, AND `total_capacity`. Missing `session_date` breaks sort order (NULLS LAST).

### deleteStaleSessionsForEvent
Called before each ingest batch — removes sessions whose `session_id` is not in the new data. Prevents ghost "main" sessions accumulating alongside real IDs.

### Sort order (getEvents)
Events sorted by nearest upcoming `session_date` via `MIN(s.session_date) WHERE >= today`. Falls back to `show_date` then `created_at`. NULLS LAST. All scrapers must output `date` as `"YYYY-MM-DD"` ISO string.

### Environment variables

Required in Vercel:
- `DATABASE_URL` — Neon connection string
- `INGEST_SECRET` — shared secret with GitHub Actions
- `TELEGRAM_TOKEN` — Telegram bot token
- `TELEGRAM_CHAT_ID` — Telegram chat ID (940741683)

Required in GitHub Actions secrets:
- `INGEST_URL` — `https://teatrosaryel.vercel.app/api/ingest`
- `INGEST_SECRET` — same as Vercel

### DB schema (auto-migrated in `initDb`)

```sql
events    (id, name, venue, url, platform, active, page_url, has_tickets, show_date)
sessions  (id, event_id, session_id, session_label, session_date, total_capacity)
snapshots (id, session_id, sold, reserved, available, captured_at)
```

### Active shows (as of May 2026)

| Ciudad | Venue | Fecha | Plataforma |
|---|---|---|---|
| Madrid | Teatro Fígaro | May + Jun 2026 | gruposmedia |
| Almería | Teatro Cervantes | 16 May 2026 | todaslasentradas |
| Palencia | Teatro Cines Ortega | 30 May 2026 | reservaentradas |
| Salamanca | Palacio de Congresos | 18 Oct 2026 | ctickets |
| Sevilla | Auditorio Cartuja | 29 Oct 2026 | auditoriocartuja |
| Santander | Auditorium Salesianos | 22 Nov 2026 | ctickets |
| Burgos | Cultural Caja de Burgos | 27 Nov 2026 | bacantix |
| León | Auditorio Ciudad de León | 12 Dec 2026 | ctickets |
