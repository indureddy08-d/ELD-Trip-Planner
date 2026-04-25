# ELD Trip Planner – HOS-Compliant Route Planning

## Project Overview

ELD Trip Planner is a full-stack web application that helps plan trucking trips in compliance with FMCSA Hours of Service (HOS) regulations. Given a current location, pickup, and dropoff, the planner calculates route distance and drive time, inserts mandatory 30-minute breaks, sleeper berth resets, and fuel stops where required, and generates FMCSA-format ELD daily log sheets for each day of the trip.

The application is designed for property-carrying drivers operating under the **70-hour / 8-day cycle** (49 CFR Part 395).

---

## Key Features

- **HOS-compliant trip planning** — current location, pickup, and dropoff with cycle hours input
- **Compliance status** — compliant, cycle-low warning, or cycle-exhausted verdict
- **Route summary** — total distance, on-road days, cycle hours remaining after trip
- **Live map** — interactive Leaflet/OpenStreetMap route display when `ORS_API_KEY` is configured
- **Fallback routing** — lookup-table distance estimates when no API key is present; trip planning still works fully
- **Stops & rests timeline** — every stop in sequence with arrival time, duration, and departure
- **Route instructions** — step-by-step driving instructions with HOS context
- **ELD log sheet generation** — FMCSA-format daily logs (49 CFR 395.8) with 24-hour duty grid, hours summary, remarks, and certification footer
- **Print / Save as PDF** — single-page landscape PDF output per log day
- **Driver & log metadata** — driver name, carrier, office address, vehicle numbers, co-driver, shipper & commodity
- **Demo scenarios** — four preloaded test cases covering short haul, break required, fuel stop, and cycle exhausted

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, JavaScript, CSS |
| Map | Leaflet, OpenStreetMap |
| Backend | Django, Django REST Framework, Python |
| Routing | OpenRouteService API with fallback provider |
| Database | SQLite (local development) |

---

## Project Structure

```
DriverLogBook/
├── frontend/
│   ├── src/
│   │   ├── api/            # API client (tripApi.js)
│   │   ├── components/     # UI components
│   │   │   ├── results/    # Summary, map, timeline, instructions, ELD sheets
│   │   │   ├── history/    # Recent trips panel and preview modal
│   │   │   ├── TripForm.jsx
│   │   │   └── HeaderDutyControl.jsx
│   │   ├── hooks/          # useTripPlanner, useRouteData, useDutySession, useRecentTrips
│   │   └── utils/          # Formatters
│   └── vite.config.js
│
└── backend/
    ├── trips/              # Trip model, HOS planner, serializers, views, URLs
    ├── compliance/         # HOS rules engine
    ├── routing/            # ORS API provider and fallback lookup table
    ├── logs/               # ELD log model
    └── core/               # Django settings, URLs, WSGI/ASGI
```

---

## Setup Instructions

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/api/`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## Environment Variables

Create a `.env` file inside the `backend/` directory. A template is provided at `backend/.env.example`.

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DJANGO_ENV` | Set to `local` for development |
| `ORS_API_KEY` | OpenRouteService API key (optional) |

### ORS API Key

The `ORS_API_KEY` enables live route coordinates and polyline rendering on the map tab. Without it, the application falls back to a lookup-table provider that estimates distances between major cities. **Trip planning, HOS calculations, and ELD log generation all work fully without the key** — only the interactive map display requires it.

```
ORS_API_KEY=your_openrouteservice_api_key_here
```

A free API key is available at [openrouteservice.org](https://openrouteservice.org/dev/#/signup).

---

## How to Use

1. Enter **Current Location**, **Pickup**, and **Dropoff** (City, State format)
2. Enter **Cycle Hours Used** — hours already consumed in the current 70h/8-day cycle
3. Optionally expand **Driver & Log Info** and fill in driver name, carrier, vehicle numbers, and shipper details for personalized ELD output
4. Click **Plan Trip**
5. Review the results across five tabs:
   - **Summary** — compliance verdict, key metrics, and planning assumptions
   - **Map & Route** — interactive route map with leg breakdown
   - **Stops & Rests** — full stop-by-stop timeline
   - **Route Instructions** — step-by-step instructions with HOS context
   - **ELD Log Sheets** — FMCSA-format daily logs
6. On the ELD Log Sheets tab, click **Print / Save as PDF** to export

---

## Demo Scenarios

Four preloaded scenarios are available in the sidebar under **Demo scenarios**:

| Scenario | Description |
|---|---|
| **Short Haul** | ~180 mi, same-day, no breaks required |
| **Break Required** | ~520 mi, triggers mandatory 30-min off-duty break |
| **Fuel Stop** | ~1,100 mi, forces a mid-route fuel stop |
| **Cycle Exhausted** | 70h used at departure, shows cycle-limit warning |

---

## HOS Assumptions

| Rule | Value |
|---|---|
| Cycle | 70-hour / 8-day (property-carrying) |
| Driving limit | 11 hours per shift |
| On-duty window | 14 hours per shift |
| Mandatory break | 30 minutes off-duty after 8 cumulative driving hours |
| Pickup / dropoff | 1 hour on-duty (not driving) each |
| Fuel stop interval | Every 1,000 miles |
| Speed estimate | 55 mph fixed (HOS simulation) |
| Route API time | Shown separately as estimated real-world driving time |
| Sleeper berth reset | Full 10-hour reset; split sleeper provision supported (49 CFR 395.1(g)) |

---

## Final Output

A completed trip plan produces:

- **Summary dashboard** — compliance status, total distance, days on road, cycle remaining
- **Interactive route map** — polyline route with waypoint markers (requires ORS API key)
- **Stops & rests timeline** — every stop with type, location, timing, and duration
- **Route instructions** — numbered steps with day/time, distance, and HOS context
- **ELD daily log sheets** — one FMCSA-format log per day, including 24-hour duty grid, hours totals, remarks, driver signature block, and certification statement
- **Printable PDF** — landscape Letter format, one log per page

---

## Limitations / Notes

- This is a **planning and educational project**. It is not a certified ELD device and does not replace official telematics equipment.
- Live route accuracy depends on the OpenRouteService API. Fallback distances are estimates based on a lookup table and may not reflect actual road distances.
- HOS calculations use a fixed 55 mph speed estimate. Actual drive times will vary.
- Real-world compliance must be verified against official FMCSA guidance, carrier policy, and applicable state regulations.

---

## Author

Developed by: [Your Name]
