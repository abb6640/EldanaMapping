"""Egglog-backed matching for the synthetic map demo."""

from __future__ import annotations

import json
from pathlib import Path


def _records(root: Path, filename: str) -> list[dict]:
    with (root / filename).open(encoding="utf-8") as handle:
        return json.load(handle)["features"]


def _candidates(volunteers: list[dict], clients: list[dict]) -> list[dict]:
    matches = []
    for volunteer in volunteers:
        vp = volunteer["properties"]
        for client in clients:
            cp = client["properties"]
            shared_skills = sorted(set(vp.get("skills", [])) & set(cp.get("needs", [])))
            if not shared_skills:
                continue
            for day, volunteer_shifts in vp.get("availability", {}).items():
                client_shifts = set(cp.get("schedule", {}).get(day, []))
                for shift in volunteer_shifts:
                    if shift in client_shifts:
                        matches.append({
                            "volunteer_id": volunteer.get("id"),
                            "volunteer": vp["name"],
                            "client_id": client.get("id"),
                            "client": cp["name"],
                            "day": day,
                            "shift": shift,
                            "skills": shared_skills,
                            "volunteer_coordinates": volunteer["geometry"]["coordinates"],
                            "client_coordinates": client["geometry"]["coordinates"],
                        })
    return matches


def _egglog_matches(volunteers: list[dict], clients: list[dict], candidates: list[dict]) -> list[dict]:
    """Derive candidate matches through the Egglog relation rule."""
    from egglog import EGraph, String, relation, rule, run, vars_

    volunteer = relation("volunteer", String, String, String)
    client = relation("client", String, String, String)
    volunteer_skill = relation("volunteer-skill", String, String)
    client_need = relation("client-need", String, String)
    match = relation("match", String, String, String, String, String)
    v, c, day, shift, skill = vars_("v c day shift skill", String)

    graph = EGraph()
    facts = []
    for feature in volunteers:
        p = feature["properties"]
        for record_day, shifts in p.get("availability", {}).items():
            for record_shift in shifts:
                facts.append(volunteer(String(p["name"]), String(record_day), String(record_shift)))
        for record_skill in p.get("skills", []):
            facts.append(volunteer_skill(String(p["name"]), String(record_skill)))
    for feature in clients:
        p = feature["properties"]
        for record_day, shifts in p.get("schedule", {}).items():
            for record_shift in shifts:
                facts.append(client(String(p["name"]), String(record_day), String(record_shift)))
        for record_need in p.get("needs", []):
            facts.append(client_need(String(p["name"]), String(record_need)))

    graph.register(*facts)
    graph.register(rule(
        volunteer(v, day, shift),
        client(c, day, shift),
        volunteer_skill(v, skill),
        client_need(c, skill),
    ).then(match(v, c, day, shift, skill)))
    graph.run(run().saturate())

    confirmed = []
    for candidate in candidates:
        for skill_name in candidate["skills"]:
            fact = match(String(candidate["volunteer"]), String(candidate["client"]),
                         String(candidate["day"]), String(candidate["shift"]), String(skill_name))
            if graph.check_bool(fact):
                confirmed.append({**candidate, "skill": skill_name})
    return confirmed


def match_demo_records(root: Path) -> dict:
    volunteers = _records(root, "volunteers.geojson")
    clients = _records(root, "clients.geojson")
    candidates = _candidates(volunteers, clients)
    try:
        matches = _egglog_matches(volunteers, clients, candidates)
        engine = "egglog"
    except ImportError:
        matches = [{**candidate, "skill": candidate["skills"][0]} for candidate in candidates]
        engine = "compatible-fallback"
    return {"engine": engine, "rule": "shared skill + same day + same shift",
            "matches": matches, "count": len(matches)}
