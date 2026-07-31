# Unstop Calendar Sync

Auto-syncs your registered [Unstop](https://unstop.com) events to Google Calendar every 30 minutes.

```
 Unstop (Playwright) ──► FastAPI backend ──► SQLite ──► Google Calendar API
                              │
                         Next.js dashboard
```

---

## Features

- Scrapes your registered Unstop events every 30 minutes (headless browser)
- Creates Google Calendar events with **three reminders** (1 day · 2 hours · 30 min)
- Detects changes and updates existing calendar events
- Marks removed registrations as inactive
- Simple dashboard: live event list, sync status, manual "Sync now" button

---

## Project layout

```
unstop-calendar-sync/
├── backend/
│   ├── app.py              ← FastAPI app + all API routes
│   ├── scheduler.py        ← APScheduler background job (30-min sync)
│   ├── unstop.py           ← Playwright scraper for Unstop events
│   ├── google_calendar.py  ← Google Calendar API helpers
│   ├── database.py         ← SQLAlchemy engine + session
│   ├── models.py           ← ORM models (Event, SyncLog)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/app/
    │   ├── page.tsx         ← Dashboard
    │   ├── layout.tsx
    │   └── globals.css
    ├── next.config.js       ← Proxies /api/* to FastAPI
    ├── package.json
    └── .env.local.example
```

---

## Quick start (local)

### 1 — Clone and install

```bash
git clone <your-repo> unstop-calendar-sync
cd unstop-calendar-sync
```

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # download headless browser
cp .env.example .env                 # fill in credentials (see below)
```

**Frontend**
```bash
cd ../frontend
npm install
cp .env.local.example .env.local
```

### 2 — Fill in credentials

Edit `backend/.env`:

| Variable | Where to get it |
|---|---|
| `UNSTOP_EMAIL` | Your Unstop login email |
| `UNSTOP_PASSWORD` | Your Unstop login password |
| `GOOGLE_CLIENT_ID` | Google Cloud Console → OAuth 2.0 client |
| `GOOGLE_CLIENT_SECRET` | Same OAuth client |
| `GOOGLE_REFRESH_TOKEN` | Run the helper script below |

### 3 — Get a Google refresh token

1. Go to [Google Cloud Console](https://console.cloud.google.com).
2. Create a project → enable **Google Calendar API**.
3. Create OAuth credentials (Desktop application).
4. Download the JSON → save as `backend/client_secret.json`.
5. Run:
   ```bash
   cd backend
   python - <<'EOF'
   from google_auth_oauthlib.flow import InstalledAppFlow
   flow = InstalledAppFlow.from_client_secrets_file(
       "client_secret.json",
       scopes=["https://www.googleapis.com/auth/calendar"]
   )
   creds = flow.run_local_server(port=0)
   print("REFRESH_TOKEN:", creds.refresh_token)
   EOF
   ```
6. Copy the printed token into `GOOGLE_REFRESH_TOKEN` in `.env`.

### 4 — Run

**Two terminals:**

```bash
# Terminal 1 — backend
cd backend && uvicorn app:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open **http://localhost:3000** — hit **Sync now** to test your first sync.

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Dashboard summary (event count, last sync) |
| `GET` | `/api/events` | All active synced events |
| `GET` | `/api/events/{id}` | Single event |
| `POST` | `/api/sync` | Trigger a manual sync immediately |
| `GET` | `/api/logs?limit=20` | Recent sync log entries |
| `GET` | `/health` | Liveness check |

---

## Database schema

**events**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| unstop_id | TEXT UNIQUE | ID extracted from Unstop URL |
| title | TEXT | |
| date | TEXT | ISO date `2025-09-14` |
| time | TEXT | `10:00 AM` or null |
| deadline | TEXT | Registration deadline string |
| event_url | TEXT | Full Unstop URL |
| calendar_event_id | TEXT | Google Calendar event ID |
| is_active | BOOLEAN | False when removed from Unstop |
| created_at | DATETIME | |
| updated_at | DATETIME | |

**sync_logs**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| synced_at | DATETIME | |
| events_added | INTEGER | |
| events_updated | INTEGER | |
| events_removed | INTEGER | |
| status | TEXT | `success` or `error` |
| error_message | TEXT | Null on success |

---

## Deployment (Railway / Render)

### Backend (Railway)

1. Create a new Railway project → add a Python service pointing at `/backend`.
2. Set the start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
3. Add all environment variables from `.env.example` in the Railway dashboard.
4. Add `playwright install chromium` as a build command (or use a Dockerfile).

**Dockerfile for backend (Railway)**
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend (Vercel / Railway)

```bash
cd frontend
vercel deploy
```

Set `NEXT_PUBLIC_API_URL` to your Railway backend URL.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `UNSTOP_EMAIL` | — | Unstop login email |
| `UNSTOP_PASSWORD` | — | Unstop login password |
| `GOOGLE_CLIENT_ID` | — | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | — | OAuth 2.0 client secret |
| `GOOGLE_REFRESH_TOKEN` | — | Long-lived refresh token |
| `GOOGLE_CALENDAR_ID` | `primary` | Target calendar (use email for a specific calendar) |
| `DATABASE_URL` | `sqlite:///./unstop_sync.db` | Postgres URL for production |

---

## Roadmap (future)

- [ ] Telegram / Discord reminders
- [ ] Email digest (weekly summary)
- [ ] AI priority summary (which events to prioritise)
- [ ] Dedicated "Unstop Events" calendar
- [ ] Multi-account support

---

## Notes

- The Playwright scraper logs in with your Unstop credentials on each sync run. If Unstop adds CAPTCHA or 2FA, you may need to handle that separately.
- Google Calendar reminders are **popup** type. Change `"method"` to `"email"` in `google_calendar.py` to get email reminders instead.
- For production, store `DATABASE_URL` as a Postgres connection string (Railway / Render both offer free Postgres instances).
