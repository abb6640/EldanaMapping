# EldanaMapping

EldanaMapping is a collaborative map for turning local knowledge into actionable community projects. It helps a team collect places, stories, needs, and opportunities, then organize them into hackathon-ready initiatives.

## Why it exists

Good civic ideas are often scattered across conversations, spreadsheets, and disconnected maps. EldanaMapping gives a team one calm workspace for discovering context, shaping proposals, and sharing a clear next step.

## Product pillars

- **Explore** a living map of community signals.
- **Understand** the people, places, and needs behind each signal.
- **Shape** promising signals into structured project briefs.
- **Share** a concise story with teammates and partners.

## Development

The application is intentionally dependency-light: a Python standard-library API serves a browser-native frontend. Run the local server with:

```powershell
python -m app
```

Then open `http://127.0.0.1:8000`.

## Volunteer matching data

The combined map reads two GeoJSON layers from `data/`:

- `volunteers.geojson` stores each volunteer's address, point coordinates, skills, and available day/shift windows.
- `clients.geojson` stores each client's address, point coordinates, requested help, and preferred day/shift windows.

The browser matches a client to volunteers when at least one requested skill overlaps and at least one day/shift is available for both people. The map keeps both layers visible together: orange pins represent volunteers and green pins represent clients.

## Project status

This is a hackathon foundation designed for rapid iteration. The roadmap lives in `docs/ROADMAP.md` and the architecture notes live in `docs/ARCHITECTURE.md`.
