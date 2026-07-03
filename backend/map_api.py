"""Map backend: GeoJSON layers, coverage gaps, and the assignment planner.

Public routes  /api/map/*        anonymized, safe for the website.
Admin routes   /api/map/admin/*  full detail, need the X-API-Key header.

The planner (STRATEGIES) is the part the agent is expected to improve.
validate_plan() is the guardrail: a plan that breaks a hard rule is never applied.
"""
import json
import math
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from main import SERVICES, db, hard_constraints, haversine, log, now, require_key, vol

public_router = APIRouter(prefix="/api/map", tags=["map"])
admin_router = APIRouter(prefix="/api/map/admin", tags=["map (admin)"], dependencies=[Depends(require_key)])

CELL = 0.02      # public client density grid, about 2 km
K_MIN = 3        # a public grid cell is only shown if it holds at least this many clients


# ---------- small helpers ----------
def parse_bbox(bbox):
    if not bbox:
        return None
    try:
        b = [float(x) for x in bbox.split(",")]
        assert len(b) == 4
        return b
    except Exception:
        raise HTTPException(422, "bbox must be minLat,minLng,maxLat,maxLng")


def inside(b, lat, lng):
    return not b or (b[0] <= lat <= b[2] and b[1] <= lng <= b[3])


def point(lat, lng, props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": props}


def fc(features):
    return {"type": "FeatureCollection", "features": features}


# ---------- public map (anonymized) ----------
@public_router.get("/geojson")
def public_geojson(layers: str = "vol,client,chapter", service: Optional[str] = None, bbox: Optional[str] = None):
    """Volunteers: first name, location rounded to ~1 km.
    Clients: only density cells holding at least K_MIN clients, no names, no exact points."""
    want, b, feats = set(layers.split(",")), parse_bbox(bbox), []
    with db() as con:
        if "vol" in want:
            for r in con.execute("SELECT * FROM volunteers WHERE active=1"):
                v = vol(r)
                lat, lng = round(v["lat"], 2), round(v["lng"], 2)
                if (service and service not in v["categories"]) or not inside(b, lat, lng):
                    continue
                feats.append(point(lat, lng, {"layer": "vol", "title": "Volunteer: " + v["name"].split()[0],
                                              "services": [SERVICES[c] for c in v["categories"]]}))
        if "client" in want:
            cells = defaultdict(int)
            for r in con.execute("SELECT lat,lng FROM clients"):
                cells[(math.floor(r["lat"] / CELL), math.floor(r["lng"] / CELL))] += 1
            for (i, j), n in cells.items():
                lat, lng = round((i + 0.5) * CELL, 3), round((j + 0.5) * CELL, 3)
                if n >= K_MIN and inside(b, lat, lng):
                    feats.append(point(lat, lng, {"layer": "client", "title": "Clients in this area", "count": n}))
        if "chapter" in want:
            for r in con.execute("SELECT * FROM chapters"):
                if inside(b, r["lat"], r["lng"]):
                    feats.append(point(r["lat"], r["lng"], {"layer": "chapter", "title": r["name"], "desc": r["description"]}))
    return fc(feats)


@public_router.get("/demo-geojson")
def demo_geojson(layers: str = "vol,client"):
    """Hackathon demo layer with fictional volunteer/client details and schedules.

    This is intentionally separate from the privacy-preserving public map layer.
    The records are synthetic and designed to demonstrate skill + shift matching.
    """
    root = Path(__file__).resolve().parent / "demo_data"
    features = []
    wanted = set(layers.split(","))
    for layer in ("vol", "client"):
        if layer not in wanted:
            continue
        with (root / ("volunteers.geojson" if layer == "vol" else "clients.geojson")).open(encoding="utf-8") as handle:
            features.extend(json.load(handle)["features"])
    return fc(features)


# ---------- admin map (full detail) ----------
@admin_router.get("/geojson")
def admin_geojson(layers: str = "vol,client,chapter,assignment", service: Optional[str] = None, bbox: Optional[str] = None):
    want, b, feats = set(layers.split(",")), parse_bbox(bbox), []
    with db() as con:
        vols = {r["id"]: vol(r) for r in con.execute("SELECT * FROM volunteers WHERE active=1")}
        clients = {r["id"]: dict(r) for r in con.execute("SELECT * FROM clients")}
        open_by_client = defaultdict(int)
        for r in con.execute("SELECT client_id FROM appointments WHERE status='open'"):
            open_by_client[r["client_id"]] += 1
        if "vol" in want:
            for v in vols.values():
                if (service and service not in v["categories"]) or not inside(b, v["lat"], v["lng"]):
                    continue
                feats.append(point(v["lat"], v["lng"], {
                    "layer": "vol", "id": v["id"], "title": v["name"], "services": [SERVICES[c] for c in v["categories"]],
                    "radius_miles": v["radius_miles"], "languages": v["languages"], "vehicle": v["has_vehicle"]}))
        if "client" in want:
            for c in clients.values():
                if inside(b, c["lat"], c["lng"]):
                    feats.append(point(c["lat"], c["lng"], {
                        "layer": "client", "id": c["id"], "title": c["name"], "mobility": c["mobility"],
                        "language": c["language"], "open_requests": open_by_client[c["id"]]}))
        if "chapter" in want:
            for r in con.execute("SELECT * FROM chapters"):
                feats.append(point(r["lat"], r["lng"], {"layer": "chapter", "title": r["name"], "desc": r["description"]}))
        if "assignment" in want:
            for a in con.execute("SELECT * FROM appointments WHERE status='matched' AND volunteer_id IS NOT NULL"):
                v, c = vols.get(a["volunteer_id"]), clients.get(a["client_id"])
                if not v or not c:
                    continue
                feats.append({"type": "Feature",
                              "geometry": {"type": "LineString", "coordinates": [[v["lng"], v["lat"]], [c["lng"], c["lat"]]]},
                              "properties": {"layer": "assignment", "appointment_id": a["id"], "date": a["date"], "slot": a["slot"],
                                             "service": SERVICES[a["service_type"]],
                                             "miles": round(haversine(v["lat"], v["lng"], c["lat"], c["lng"]), 2)}})
    return fc(feats)


@admin_router.get("/near")
def near(lat: float, lng: float, type: str = "vol", service: Optional[str] = None,
         limit: int = Query(5, ge=1, le=50), max_miles: float = 25):
    """Nearest volunteers or clients to a point."""
    table = {"vol": "volunteers", "client": "clients"}.get(type)
    if not table:
        raise HTTPException(422, "type must be vol or client")
    out = []
    with db() as con:
        for r in con.execute(f"SELECT * FROM {table}" + (" WHERE active=1" if type == "vol" else "")):
            if type == "vol" and service and service not in vol(r)["categories"]:
                continue
            d = haversine(lat, lng, r["lat"], r["lng"])
            if d <= max_miles:
                out.append({"id": r["id"], "name": r["name"], "miles": round(d, 2)})
    return sorted(out, key=lambda x: x["miles"])[:limit]


# ---------- coverage gaps ("geographic deserts") ----------
def coverage(vols, clients):
    """For each client, how many active volunteers have them inside their travel radius."""
    res = []
    for c in clients.values():
        n = sum(1 for v in vols if haversine(v["lat"], v["lng"], c["lat"], c["lng"]) <= v["radius_miles"])
        res.append({"client_id": c["id"], "name": c["name"], "lat": c["lat"], "lng": c["lng"], "volunteers_in_range": n})
    return res


@admin_router.get("/deserts")
def deserts(min_volunteers: int = 8):
    """Clients with fewer than `min_volunteers` volunteers in range (thin coverage), grouped into areas that are
    good recruiting targets. `no_coverage` counts clients nobody can reach at all."""
    with db() as con:
        vols = [vol(r) for r in con.execute("SELECT * FROM volunteers WHERE active=1")]
        clients = {r["id"]: dict(r) for r in con.execute("SELECT * FROM clients")}
    thin = [c for c in coverage(vols, clients) if c["volunteers_in_range"] < min_volunteers]
    areas = defaultdict(list)
    for c in thin:
        areas[(math.floor(c["lat"] / CELL), math.floor(c["lng"] / CELL))].append(c)
    targets = sorted(({"lat": round((i + 0.5) * CELL, 3), "lng": round((j + 0.5) * CELL, 3), "underserved_clients": len(cs)}
                      for (i, j), cs in areas.items()), key=lambda t: -t["underserved_clients"])
    return {"min_volunteers": min_volunteers, "no_coverage": sum(1 for c in thin if c["volunteers_in_range"] == 0),
            "underserved": len(thin), "total_clients": len(clients),
            "recruiting_targets": targets, "clients": thin}


# ---------- planner: this is what the agent optimizes ----------
def load_state(con):
    vols = [vol(r) for r in con.execute("SELECT * FROM volunteers WHERE active=1")]
    clients = {r["id"]: dict(r) for r in con.execute("SELECT * FROM clients")}
    appts = [dict(r) for r in con.execute("SELECT * FROM appointments WHERE status='open' ORDER BY date, slot, id")]
    busy = defaultdict(set)
    for r in con.execute("SELECT volunteer_id,date,slot FROM appointments WHERE status='matched' AND volunteer_id IS NOT NULL"):
        busy[(r["date"], r["slot"])].add(r["volunteer_id"])
    return vols, clients, appts, busy


def plan_greedy(vols, clients, appts, busy):
    """Baseline: go through requests in date order and give each the nearest eligible volunteer.
    Fast to write, but an early request can take a volunteer that a later request needed more."""
    busy = defaultdict(set, {k: set(s) for k, s in busy.items()})
    plan, unmatched = [], []
    for a in appts:
        c, key = clients[a["client_id"]], (a["date"], a["slot"])
        wd, best = date.fromisoformat(a["date"]).weekday(), None
        for v in vols:
            why, d = hard_constraints(v, c, a, wd, busy[key])
            if not why and (best is None or d < best[1]):
                best = (v, d)
        if best:
            plan.append({"appointment_id": a["id"], "volunteer_id": best[0]["id"], "miles": round(best[1], 2)})
            busy[key].add(best[0]["id"])
        else:
            unmatched.append(a["id"])
    return plan, unmatched


STRATEGIES = {"greedy": plan_greedy}   # the agent registers better ones here


def validate_plan(vols, clients, appts, busy, plan):
    """Independent check. Returns a list of problems; empty means the plan is safe to propose."""
    vmap, amap = {v["id"]: v for v in vols}, {a["id"]: a for a in appts}
    seen, used, problems = set(), defaultdict(set), []
    for p in plan:
        a, v = amap.get(p["appointment_id"]), vmap.get(p["volunteer_id"])
        if not a or not v:
            problems.append(f"unknown appointment or volunteer in {p}")
            continue
        if a["id"] in seen:
            problems.append(f"appointment {a['id']} assigned twice")
        seen.add(a["id"])
        key = (a["date"], a["slot"])
        if v["id"] in used[key]:
            problems.append(f"volunteer {v['id']} double-booked on {key}")
        used[key].add(v["id"])
        why, _ = hard_constraints(v, clients[a["client_id"]], a, date.fromisoformat(a["date"]).weekday(), busy.get(key, set()))
        if why:
            problems.append(f"appointment {a['id']} -> volunteer {v['id']}: {why}")
    return problems


def run_strategy(name):
    if name not in STRATEGIES:
        raise HTTPException(422, f"Unknown strategy. Available: {sorted(STRATEGIES)}")
    t0 = time.perf_counter()
    with db() as con:
        state = load_state(con)
    plan, unmatched = STRATEGIES[name](*state)
    problems = validate_plan(*state, plan)
    miles = sum(p["miles"] for p in plan)
    return {"strategy": name, "open_requests": len(state[2]), "matched": len(plan), "unmatched_ids": unmatched,
            "total_miles": round(miles, 2), "avg_miles": round(miles / len(plan), 2) if plan else 0,
            "violations": problems, "compute_ms": round((time.perf_counter() - t0) * 1000, 1), "plan": plan}


@admin_router.get("/optimize/preview")
def preview(strategy: str = "greedy"):
    """Dry run. Writes nothing."""
    return run_strategy(strategy)


class ApplyIn(BaseModel):
    strategy: str = "greedy"
    proposed_by: str = "agent"


@admin_router.post("/optimize/apply")
def apply(body: ApplyIn):
    """Turns a valid plan into pending proposals. A coordinator still approves each one."""
    r = run_strategy(body.strategy)
    if r["violations"]:
        raise HTTPException(422, {"error": "plan breaks hard rules, nothing applied", "violations": r["violations"]})
    created = 0
    with db() as con:
        for p in r["plan"]:
            if con.execute("SELECT 1 FROM proposals WHERE appointment_id=? AND status='pending'", (p["appointment_id"],)).fetchone():
                continue
            con.execute("INSERT INTO proposals(appointment_id,volunteer_id,score,rationale,proposed_by,created_at) VALUES(?,?,?,?,?,?)",
                        (p["appointment_id"], p["volunteer_id"], round(max(0, 100 - 2 * p["miles"]), 1),
                         f"{body.strategy}: {p['miles']} mi travel", body.proposed_by, now()))
            created += 1
        log(con, body.proposed_by, "plan_applied", {"strategy": body.strategy, "proposals": created, "total_miles": r["total_miles"]})
    return {"proposals_created": created, "total_miles": r["total_miles"], "matched": r["matched"]}


@admin_router.get("/stats")
def stats():
    with db() as con:
        vols, clients, appts, _ = load_state(con)
        n_matched = con.execute("SELECT COUNT(*) FROM appointments WHERE status='matched'").fetchone()[0]
        miles = []
        for a in con.execute("SELECT * FROM appointments WHERE status='matched' AND volunteer_id IS NOT NULL"):
            v = next((x for x in vols if x["id"] == a["volunteer_id"]), None)
            c = clients.get(a["client_id"])
            if v and c:
                miles.append(haversine(v["lat"], v["lng"], c["lat"], c["lng"]))
    cov = coverage(vols, clients)
    return {"volunteers": len(vols), "clients": len(clients), "open_requests": len(appts), "matched": n_matched,
            "avg_matched_miles": round(sum(miles) / len(miles), 2) if miles else 0,
            "clients_without_coverage": sum(1 for c in cov if c["volunteers_in_range"] == 0)}
