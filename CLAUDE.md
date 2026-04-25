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
bacantix/todaslasentradas ──playwright──► GitHub Actions ──► /api/ingest ──► snapshots
```

### Key files

- `lib/scraper.ts` — gruposmedia scraper (reads `arraySesiones` from HTML)
- `lib/syncShows.ts` — discovers shows from showsaryel.com/gira/
- `lib/runScrape.ts` — shared scrape+notify logic for Vercel
- `lib/db.ts` — all DB queries (Neon)
- `lib/telegram.ts` — Telegram notifications via env vars
- `scripts/scrape_external.py` — GitHub Actions Playwright scraper
- `.github/workflows/scrape.yml` — GH Actions cron (every 10 min)
- `app/api/ingest/route.ts` — receives data from GitHub Actions
- `app/api/sync/route.ts` — syncs events from showsaryel.com
- `app/api/debug/route.ts` — shows DB state at `/api/debug`

### Ticket platforms

| Platform | Method | Notes |
|---|---|---|
| `gruposmedia` | Vercel fetch | `arraySesiones` in HTML, includes sold counts |
| `todaslasentradas` | GitHub Actions Playwright | CSS classes `mapaLibre` / `mapaOcupada` |
| `bacantix` | GitHub Actions Playwright | MCIAjax.aspx XML, `O=201` = sold |
| `reservaentradas` | GitHub Actions HTTP | `sesion=12345` hardcoded (placeholder), sold=0 always |
| `auditoriocartuja` | Manual only | Venue website, no structured data |

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
