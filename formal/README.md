# Egglog matching model

`eldana_matching.egg` is a small declarative model of the hackathon demo's matching logic. It uses Egglog relations to represent volunteer availability, client schedules, skills, and needs. The final rule derives a `match` when a volunteer and client share a day, shift, and skill.

The facts mirror the synthetic GeoJSON records in `backend/demo_data/`. The model is intentionally separate from the FastAPI runtime so the matching policy can be inspected, tested, and extended without changing the website.

Install Egglog using the official project instructions, then run:

```bash
egglog formal/eldana_matching.egg
```
