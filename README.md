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

The `/api/map/demo-geojson` endpoint combines both layers into one GeoJSON FeatureCollection. The map keeps volunteers and clients on the same map and shows their skills, needs, addresses, and schedules in the marker popups. The original privacy-preserving `/api/map/geojson` endpoint remains available separately.

## Repository layout

- `frontend/` — copied Eldana experience, including the Leaflet map.
- `backend/` — FastAPI API, SQLite seed data, planner, and map routes.
- `backend/demo_data/` — synthetic hackathon volunteer/client GeoJSON layers.
- `docs/` — architecture and roadmap notes.
