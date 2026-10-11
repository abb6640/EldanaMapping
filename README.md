# EldanaMapping

This hackathon repository is an independent copy of the Eldana website and its FastAPI/SQLite coordination backend. The original `Eldana-Website` workspace remains separate and is not modified by work in this repository.

## Run the copied app

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open `frontend/Eldana.html` with Live Server. The interactive map uses the same coordinate system as the copied Eldana app and loads its map markers from the API.

## Hackathon map data

`backend/demo_data/volunteers.geojson` and `backend/demo_data/clients.geojson` contain synthetic demo records for the map. Each volunteer includes an address, useful elder-support skills, and day/shift availability. Each client includes coordinates, a request whose needs match volunteer skills, and preferred day/shift windows.

The `/api/map/demo-geojson` endpoint combines both layers into one GeoJSON FeatureCollection. The `/api/map/demo-matches` endpoint runs the same volunteer/client relations through Egglog and returns compatible skills, days, and shifts. The frontend draws those matches as dashed lines on the same map and shows their details on hover. If Egglog is not installed yet, the endpoint uses a compatible fallback so the demo still loads; install `requirements.txt` to enable the Egglog engine. The original privacy-preserving `/api/map/geojson` endpoint remains available separately.

## Repository layout

- `frontend/` — copied Eldana experience, including the Leaflet map.
- `backend/` — FastAPI API, SQLite seed data, planner, and map routes.
- `backend/demo_data/` — synthetic hackathon volunteer/client GeoJSON layers.
- `backend/egglog_engine.py` — runtime Egglog relation engine for matching demo records.
- `formal/` — inspectable Egglog rules and expected matching checks.
- `docs/` — architecture and roadmap notes.
