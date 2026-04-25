# ELD-Trip-Planner — HOS-Compliant Route Planning & Driver Log Sheet Generator

## Overview

A full-stack web application for planning commercial truck trips with Hours of Service (HOS) compliance. Given a current location, pickup, and dropoff, the planner calculates a compliant route, schedules mandatory breaks, sleeper berth resets, and fuel stops, then generates printable ELD-style daily log sheets for each day of the trip.

Built for property-carrying drivers operating under the **70-hour / 8-day cycle** (49 CFR Part 395).

---

## Key Features

- Trip planning with current location, pickup, and dropoff inputs
- 70-hour / 8-day cycle hours input and tracking
- HOS compliance checking with compliant / cycle-low / cycle-exhausted status
- Automatic 30-minute break scheduling after 8 cumulative driving hours
- Sleeper berth reset handling (10-hour reset, resets 11h driving and 14h on-duty windows)
- Fuel stop planning every 1,000 miles
- Route summary with total distance, on-road days, and cycle hours remaining
- Stop-by-stop timeline with arrival times, durations, and departures
- Step-by-step route instructions with HOS context
- Live map route display using OpenRouteService when `ORS_API_KEY` is configured
- Fallback lookup-table routing when `ORS_API_KEY` is not set — trip planning still works fully
- ELD-style daily log sheet generation (24-hour duty grid, hours summary, remarks, certification)
- Print / Save as PDF support for ELD log sheets
- Recent trip history stored locally in the browser
- Optional live session tracker — separate from trip planning and ELD generation

---

## Tech Stack

**Frontend**
- React
- Vite
- Leaflet / OpenStreetMap
- CSS

**Backend**
- Django
- Django REST Framework
- SQLite (local development)
- PostgreSQL-ready production settings
- OpenRouteService API integration with fallback provider

---

## Project Structure

```
ELD-Trip-Planner/
├── backend/          # Django REST API — HOS engine, ELD generator, routing
├── frontend/         # React app — trip form, results tabs, ELD log sheets
├── README.md
└── .gitignore
```

**`backend/`** contains the Django project with apps for trip planning (`trips`), HOS rules (`compliance`), ELD log generation (`logs`), and routing (`routing`).

**`frontend/`** contains the React application with components for the trip form, summary, map, stops timeline, route instructions, and ELD log sheets.

---

## Environment Variables

The backend requires a `.env` file at `backend/.env`. This file must **not** be committed to version control.

A template is provided at `backend/.env.example`. Copy it and fill in the values before running the server.

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key |
| `DJANGO_ENV` | Yes | Set to `local` for development |
| `ALLOWED_HOSTS` | Production | Comma-separated allowed hostnames |
| `CORS_ALLOWED_ORIGINS` | Production | Comma-separated allowed origins |
| `ORS_API_KEY` | Optional | OpenRouteService API key |

**`ORS_API_KEY` is optional.** Without it, the app uses a built-in lookup table for distances and trip planning works fully. Live map coordinates and route polylines require a valid key. Free keys are available at [openrouteservice.org](https://openrouteservice.org/dev/#/signup).

---

## Backend Setup

Run these commands in Windows PowerShell:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000`.

---

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## Running the Full App

1. Start the backend first: `python manage.py runserver` (from `backend/` with venv active)
2. Start the frontend: `npm run dev` (from `frontend/`)
3. Open `http://localhost:5173` in your browser

The frontend expects the backend at `http://127.0.0.1:8000`. Both must be running for trip planning to work.

---

## Testing

**Backend**

```powershell
cd backend
python manage.py test
```

**Frontend**

```powershell
cd frontend
npm run lint
npm run build
```

---

## Demo Scenarios

Four built-in demo scenarios are available in the sidebar under **Demo scenarios**:

| Scenario | Description |
|---|---|
| **Short Haul** | ~230 mi, same-day, no breaks required |
| **Break Required** | ~520 mi, triggers mandatory 30-min off-duty break |
| **Fuel Stop** | ~1,100 mi, long-haul route with fuel stop and sleeper berth reset |
| **Cycle Exhausted** | 70h used at departure, shows cycle-limit warning |

Click any demo button to pre-fill the form, then click **Plan Trip**.

---

## Print / PDF

ELD log sheets can be printed or saved as PDF directly from the **ELD Log Sheets** tab. Click **Print / Save as PDF** to open the browser print dialog. Each log day prints on one landscape Letter page.

---

## Important Notes

- This project is for planning, demonstration, and educational purposes.
- It is not a certified ELD device and does not replace official telematics equipment.
- The **Session Tracker** in the header is an optional live duty timer only. It is separate from trip planning and ELD log generation and does not affect any calculated output.
- Production use would require verified routing data, legal review, and integration with a certified ELD system compliant with FMCSA regulations.
- Route distances and drive times are estimates. Actual road conditions, traffic, and carrier policies will vary.

---

## Final Submission Checklist

- [ ] Backend tests pass — `python manage.py test`
- [ ] Frontend lint passes — `npm run lint`
- [ ] Frontend build passes — `npm run build`
- [ ] `backend/.env` is not committed to version control
- [ ] `ORS_API_KEY` is stored only in the local `.env` or production environment
- [ ] All four demo scenarios tested and produce results
- [ ] PDF export verified from the ELD Log Sheets tab
