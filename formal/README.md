# Egglog matching model

`eldana_matching.egg` is a small declarative model of the hackathon demo's matching logic. It uses Egglog relations to represent volunteer availability, client schedules, skills, and needs. The final rule derives a `match` when a volunteer and client share a day, shift, and skill.

The facts mirror the synthetic GeoJSON records in `backend/demo_data/`. The FastAPI demo now loads the same relations through `backend/egglog_engine.py` and exposes derived links at `/api/map/demo-matches`; the frontend renders those links as dashed map lines.

Install Egglog using the official project instructions, then run:

```bash
egglog formal/eldana_matching.egg
```
