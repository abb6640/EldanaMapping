"""Eldana backend (FastAPI + SQLite).

Run:  pip install -r requirements.txt && uvicorn main:app --reload
Docs: http://localhost:8000/docs

Public endpoints (no key): staff, services, map (anonymized), impact, donations, contact.
Private endpoints (header X-API-Key): everything with client or volunteer details,
including the agent tools. Set ELDANA_ADMIN_KEY in the environment.
"""
import json
import math
import os
import random
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("ELDANA_DB", "eldana.db")
ADMIN_KEY = os.environ.get("ELDANA_ADMIN_KEY", "dev-admin-key")
Slot = Literal["morning", "afternoon", "evening"]

SERVICES = {
    "grocery": "Grocery & Supplies",
    "ride": "Rides & Transportation",
    "medication": "Medication Reminders",
    "companionship": "Companionship & Reading",
    "tech": "Tech Support",
    "home_prep": "Light Home Prep",
    "mobility": "Mobility Aid Escort",
    "meal": "Meal Preparation",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY, name TEXT, title TEXT, bio TEXT, image TEXT);
CREATE TABLE IF NOT EXISTS chapters(id INTEGER PRIMARY KEY, name TEXT, description TEXT, lat REAL, lng REAL);
CREATE TABLE IF NOT EXISTS volunteers(
  id INTEGER PRIMARY KEY, name TEXT, email TEXT, phone TEXT, lat REAL, lng REAL,
  radius_miles REAL, categories TEXT, languages TEXT, availability TEXT,
  has_vehicle INTEGER, wheelchair_vehicle INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS clients(
  id INTEGER PRIMARY KEY, name TEXT, address TEXT, lat REAL, lng REAL,
  mobility TEXT, language TEXT, coordinator TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY, client_id INTEGER REFERENCES clients(id),
  volunteer_id INTEGER REFERENCES volunteers(id), service_type TEXT, date TEXT, slot TEXT,
  status TEXT DEFAULT 'open', duration_hours REAL, miles REAL DEFAULT 0, notes TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS proposals(
  id INTEGER PRIMARY KEY, appointment_id INTEGER REFERENCES appointments(id),
  volunteer_id INTEGER REFERENCES volunteers(id), score REAL, rationale TEXT,
  proposed_by TEXT, status TEXT DEFAULT 'pending', note TEXT, created_at TEXT, decided_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS donations(
  id INTEGER PRIMARY KEY, name TEXT, email TEXT, amount REAL, frequency TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, name TEXT, email TEXT, role TEXT, subject TEXT, body TEXT, created_at TEXT);
"""


# ---------- helpers ----------
@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


def haversine(lat1, lng1, lat2, lng2):
    """Distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def vol(r):
    d = dict(r)
    for k in ("categories", "languages", "availability"):
        d[k] = json.loads(d[k])
    for k in ("has_vehicle", "wheelchair_vehicle", "active"):
        d[k] = bool(d[k])
    return d


def log(con, actor, action, detail):
    con.execute("INSERT INTO audit_log(ts,actor,action,detail) VALUES(?,?,?,?)",
                (now(), actor, action, json.dumps(detail)))


def require_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != ADMIN_KEY:
        raise HTTPException(401, "Missing or invalid X-API-Key")


# ---------- seed data (taken from the current site) ----------
def seed(con):
    if con.execute("SELECT COUNT(*) FROM volunteers").fetchone()[0]:
        return
    staff = [
        ("Phat Nguyen", "Co-Founder & CEO", "Phat Nguyen is the co-founder and CEO of Eldana. He is a Schreyer honors scholar, studying integrative science at Penn State Harrisburg and completing a master of public health at the Penn State College of Medicine.", "headshot.jpg"),
        ("Vedant Patel", "Co-Founder & Director of Training", "Vedant is a co-founder of Eldana, overseeing all volunteer training. He is a Schreyer honors scholar, studying mechanical engineering at Penn State University.", "IMG_8316.jpeg"),
        ("Emily Kiefer", "Secretary", "Emily is the secretary of Eldana. She is a Schreyer honors scholar studying biobehavioral health at Penn State Harrisburg and completing a master of public health at the Penn State College of Medicine.", "IMG_0713.JPG"),
        ("Bob Moreland", "Auditor, Lead Researcher", "Bob Moreland is the auditor and lead researcher for Eldana. He is a STAT 1000 teacher at Central Dauphin High School, overseeing the study advisory board, participation in the National DataJam, and six sigma courses.", "image.png"),
        ("Miller Habib", "Co-Director of Research, Graphic Designer", "Miller is the co-director of Eldana | Research as well as the front-end developer and graphic designer for Eldana. He is studying Neuroscience at the University of Pennsylvania.", "IMG_2148.jpg"),
        ("Khoa Ngo", "Student Manager", "Khoa is a senior at Central Dauphin High School; he manages the youth advisory board and directs fundraising efforts alongside managing students in the six sigma programs.", "IMG_6524.JPG"),
    ]
    con.executemany("INSERT INTO staff(name,title,bio,image) VALUES(?,?,?,?)", staff)
    con.executemany("INSERT INTO chapters(name,description,lat,lng) VALUES(?,?,?,?)", [
        ("Eldana HQ Chapter", "Regional Dispatch Center", 39.9526, -75.1652),
        ("North Philly Chapter", "Community Hub & Resource Center", 39.980, -75.140)])

    wk = lambda days, slots: {"days": days, "slots": slots}
    vols = [
        ("Phat Nguyen", 39.955, -75.160, 15, ["grocery", "ride", "companionship"], ["English"], wk([0, 1, 2, 3, 4], ["morning", "afternoon"]), 1, 0),
        ("Marcus Vance", 39.948, -75.175, 15, ["companionship", "ride", "grocery", "meal"], ["English"], wk([0, 2, 3, 5], ["morning", "afternoon", "evening"]), 1, 1),
        ("David Chen", 39.962, -75.150, 15, ["tech", "companionship"], ["English", "Mandarin"], wk([0, 1, 3], ["morning", "afternoon"]), 0, 0),
        ("Maria Santos", 39.945, -75.165, 15, ["ride", "medication", "grocery"], ["English", "Spanish"], wk([1, 2, 3, 4], ["morning", "afternoon"]), 1, 0),
    ]
    for n, la, ln, r, cats, langs, av, car, wc in vols:
        con.execute("INSERT INTO volunteers(name,email,lat,lng,radius_miles,categories,languages,availability,has_vehicle,wheelchair_vehicle) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (n, n.split()[0].lower() + "@example.org", la, ln, r, json.dumps(cats), json.dumps(langs), json.dumps(av), car, wc))
    clients = [
        ("Eleanor Vance", "Philadelphia, PA", 39.940, -75.168, "wheelchair", "English", "Sarah Jenkins, MSW", "Doctor escort needs wheelchair-accessible vehicle"),
        ("Arthur Pendelton", "Philadelphia, PA", 39.958, -75.180, "walker", "English", "Sarah Jenkins, MSW", "Weekly grocery"),
        ("Clara Higgins", "Philadelphia, PA", 39.932, -75.155, "none", "English", "Sarah Jenkins, MSW", "Wants help with video calls"),
    ]
    con.executemany("INSERT INTO clients(name,address,lat,lng,mobility,language,coordinator,notes) VALUES(?,?,?,?,?,?,?,?)", clients)

    # Generated history so dashboards are not empty. Deterministic, clearly seed data.
    rng = random.Random(7)
    today = date(2026, 10, 11)
    allv = [vol(r) for r in con.execute("SELECT * FROM volunteers")]
    allc = [dict(r) for r in con.execute("SELECT * FROM clients")]
    for v in allv:
        for _ in range(rng.randint(12, 28)):
            c, svc = rng.choice(allc), rng.choice(v["categories"])
            miles = round(2 * haversine(v["lat"], v["lng"], c["lat"], c["lng"]), 1)
            con.execute("INSERT INTO appointments(client_id,volunteer_id,service_type,date,slot,status,duration_hours,miles,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (c["id"], v["id"], svc, (today - timedelta(days=rng.randint(1, 90))).isoformat(),
                         rng.choice(["morning", "afternoon"]), "completed", rng.choice([1, 1.5, 2, 2.5, 3]), miles, now()))
    # Upcoming work: two open (the agent's job), one already matched.
    up = [(1, None, "ride", "2026-10-14", "afternoon", "open"),
          (2, None, "grocery", "2026-10-15", "morning", "open"),
          (3, 3, "tech", "2026-10-12", "morning", "matched")]
    for cid, vid, svc, d, sl, st in up:
        con.execute("INSERT INTO appointments(client_id,volunteer_id,service_type,date,slot,status,created_at) VALUES(?,?,?,?,?,?,?)",
                    (cid, vid, svc, d, sl, st, now()))


# ---------- matching: hard constraints first, then a transparent score ----------
def hard_constraints(v, c, a, wd, busy):
    """Pure rule check shared by matching, the map planner and the benchmark.
    Returns (reason_or_None, distance_miles). `busy` is the set of volunteer ids already booked in that slot."""
    d = haversine(v["lat"], v["lng"], c["lat"], c["lng"])
    if a["service_type"] not in v["categories"]:
        return "does not offer this service", d
    if d > v["radius_miles"]:
        return f"{d:.1f} mi away, travel limit is {v['radius_miles']:.0f} mi", d
    if wd not in v["availability"]["days"] or a["slot"] not in v["availability"]["slots"]:
        return "not available that day and slot", d
    if v["id"] in busy:
        return "already booked in that slot", d
    if a["service_type"] == "ride" and not v["has_vehicle"]:
        return "no vehicle", d
    if a["service_type"] == "ride" and c["mobility"] == "wheelchair" and not v["wheelchair_vehicle"]:
        return "client needs a wheelchair-accessible vehicle", d
    return None, d


def evaluate(con, appt_id):
    a = con.execute("SELECT * FROM appointments WHERE id=?", (appt_id,)).fetchone()
    if not a:
        raise HTTPException(404, "Appointment not found")
    c = con.execute("SELECT * FROM clients WHERE id=?", (a["client_id"],)).fetchone()
    wd = date.fromisoformat(a["date"]).weekday()
    busy = {r[0] for r in con.execute(
        "SELECT volunteer_id FROM appointments WHERE date=? AND slot=? AND status='matched' AND volunteer_id IS NOT NULL AND id!=?",
        (a["date"], a["slot"], a["id"]))}
    history = Counter(r[0] for r in con.execute(
        "SELECT volunteer_id FROM appointments WHERE client_id=? AND status='completed'", (a["client_id"],)))
    ok, excluded = [], []
    for r in con.execute("SELECT * FROM volunteers WHERE active=1"):
        v = vol(r)
        why, d = hard_constraints(v, c, a, wd, busy)
        if why:
            excluded.append({"volunteer_id": v["id"], "name": v["name"], "reason": why})
            continue
        score, reasons = 50.0 + max(0.0, 30 - 2 * d), [f"{d:.1f} mi from client"]
        if c["language"] in v["languages"]:
            score += 15
            reasons.append(f"speaks {c['language']}")
        elif c["language"] != "English":
            score -= 20
            reasons.append(f"does not speak {c['language']}")
        if history[v["id"]]:
            score += min(10, 2 * history[v["id"]])
            reasons.append(f"{history[v['id']]} prior visit(s) with this client")
        ok.append({"volunteer_id": v["id"], "name": v["name"], "score": round(score, 1), "reasons": reasons})
    ok.sort(key=lambda x: -x["score"])
    return dict(a), dict(c), ok, excluded


# ---------- app ----------
app = FastAPI(title="Eldana API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
private = APIRouter(prefix="/api", dependencies=[Depends(require_key)])


@app.on_event("startup")
def startup():
    with db() as con:
        con.executescript(SCHEMA)
        seed(con)


# ----- public -----
@app.get("/api/services")
def services():
    return SERVICES


@app.get("/api/staff")
def staff():
    with db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM staff ORDER BY id")]


@app.get("/api/map")
def public_map():
    """Anonymized: first names for volunteers, no client names, coordinates rounded to ~1 km."""
    with db() as con:
        vs = [{"type": "vol", "title": "Volunteer: " + r["name"].split()[0], "lat": round(r["lat"], 2), "lng": round(r["lng"], 2),
               "desc": "Available for " + ", ".join(SERVICES[c] for c in json.loads(r["categories"])[:2])}
              for r in con.execute("SELECT * FROM volunteers WHERE active=1")]
        cs = [{"type": "client", "title": "Client (private)", "lat": round(r["lat"], 2), "lng": round(r["lng"], 2), "desc": "Active client"}
              for r in con.execute("SELECT * FROM clients")]
        ch = [{"type": "chap", "title": r["name"], "lat": r["lat"], "lng": r["lng"], "desc": r["description"]}
              for r in con.execute("SELECT * FROM chapters")]
    return vs + cs + ch


@app.get("/api/impact")
def impact(amount: float = Query(..., ge=0)):
    """Same tiers as the donation page."""
    if amount < 25:
        return {"label": "2 Prescription Deliveries & Wellness Check", "bar_percent": 25}
    if amount < 75:
        return {"label": "5 Grocery Delivery Rides & 2 Companion Hours", "bar_percent": 65}
    return {"label": "Full Month Mobility Escorts & Tech Mentorship", "bar_percent": 100}


class DonationIn(BaseModel):
    name: str = Field(min_length=1)
    email: str
    amount: float = Field(ge=5)
    frequency: Literal["once", "monthly"] = "once"


@app.post("/api/donations", status_code=201)
def donate(d: DonationIn):
    """Records the pledge only. Do NOT collect card numbers here; use Stripe/PayPal for real payments."""
    with db() as con:
        cur = con.execute("INSERT INTO donations(name,email,amount,frequency,created_at) VALUES(?,?,?,?,?)",
                          (d.name, d.email, d.amount, d.frequency, now()))
    return {"id": cur.lastrowid, "status": "recorded", "note": "No payment was processed."}


class ContactIn(BaseModel):
    name: str
    email: str
    role: str
    subject: str
    body: str


@app.post("/api/contact", status_code=201)
def contact(m: ContactIn):
    with db() as con:
        cur = con.execute("INSERT INTO messages(name,email,role,subject,body,created_at) VALUES(?,?,?,?,?,?)",
                          (m.name, m.email, m.role, m.subject, m.body, now()))
    return {"id": cur.lastrowid}


# ----- private: site data -----
@private.get("/admin/map")
def admin_map():
    with db() as con:
        return {"volunteers": [vol(r) for r in con.execute("SELECT * FROM volunteers")],
                "clients": [dict(r) for r in con.execute("SELECT * FROM clients")]}


@private.get("/volunteers")
def volunteers():
    with db() as con:
        return [vol(r) for r in con.execute("SELECT * FROM volunteers")]


@private.get("/volunteers/{vid}/metrics")
def metrics(vid: int):
    with db() as con:
        v = con.execute("SELECT * FROM volunteers WHERE id=?", (vid,)).fetchone()
        if not v:
            raise HTTPException(404, "Volunteer not found")
        rows = con.execute("SELECT * FROM appointments WHERE volunteer_id=? AND status='completed'", (vid,)).fetchall()
        upcoming = con.execute("SELECT * FROM appointments WHERE volunteer_id=? AND status='matched' ORDER BY date", (vid,)).fetchall()
    by = Counter(r["service_type"] for r in rows)
    n = len(rows)
    return {
        "hours": sum(r["duration_hours"] or 0 for r in rows),
        "miles": round(sum(r["miles"] or 0 for r in rows), 1),
        "appointments": n,
        "radius_miles": v["radius_miles"],
        "breakdown": [{"service": SERVICES[k], "sessions": c, "percent": round(100 * c / n)} for k, c in by.most_common()],
        "upcoming": [dict(r) for r in upcoming],
    }


class VolPrefs(BaseModel):
    categories: list[str]
    radius_miles: float = Field(ge=1, le=50)


@private.put("/volunteers/{vid}/preferences")
def vol_prefs(vid: int, p: VolPrefs):
    bad = [c for c in p.categories if c not in SERVICES]
    if bad:
        raise HTTPException(422, f"Unknown services: {bad}")
    with db() as con:
        cur = con.execute("UPDATE volunteers SET categories=?, radius_miles=? WHERE id=?",
                          (json.dumps(p.categories), p.radius_miles, vid))
        if not cur.rowcount:
            raise HTTPException(404, "Volunteer not found")
    return {"ok": True}


@private.get("/clients/{cid}")
def client(cid: int):
    with db() as con:
        c = con.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Client not found")
        nxt = con.execute("SELECT a.*, v.name AS volunteer FROM appointments a LEFT JOIN volunteers v ON v.id=a.volunteer_id "
                          "WHERE client_id=? AND status IN ('open','matched') AND date>=? ORDER BY date LIMIT 1",
                          (cid, "2026-10-11")).fetchone()
        hist = con.execute("SELECT a.date, v.name AS volunteer, a.service_type FROM appointments a JOIN volunteers v ON v.id=a.volunteer_id "
                           "WHERE client_id=? AND status='completed' ORDER BY date DESC LIMIT 20", (cid,)).fetchall()
    return {**dict(c), "next_visit": dict(nxt) if nxt else None, "history": [dict(h) for h in hist]}


class ClientPrefs(BaseModel):
    mobility: Literal["wheelchair", "walker", "none"]
    language: str


@private.put("/clients/{cid}/preferences")
def client_prefs(cid: int, p: ClientPrefs):
    with db() as con:
        cur = con.execute("UPDATE clients SET mobility=?, language=? WHERE id=?", (p.mobility, p.language, cid))
        if not cur.rowcount:
            raise HTTPException(404, "Client not found")
    return {"ok": True}


class ApptIn(BaseModel):
    client_id: int
    service_type: str
    date: date
    slot: Slot
    notes: str = ""


@private.post("/appointments", status_code=201)
def create_appt(a: ApptIn):
    if a.service_type not in SERVICES:
        raise HTTPException(422, "Unknown service")
    with db() as con:
        if not con.execute("SELECT 1 FROM clients WHERE id=?", (a.client_id,)).fetchone():
            raise HTTPException(404, "Client not found")
        cur = con.execute("INSERT INTO appointments(client_id,service_type,date,slot,status,notes,created_at) VALUES(?,?,?,?,?,?,?)",
                          (a.client_id, a.service_type, a.date.isoformat(), a.slot, "open", a.notes, now()))
        log(con, "api", "appointment_created", {"id": cur.lastrowid})
    return {"id": cur.lastrowid, "status": "open"}


@private.get("/appointments")
def list_appts(status: Optional[str] = None, client_id: Optional[int] = None, volunteer_id: Optional[int] = None):
    q, args = "SELECT * FROM appointments WHERE 1=1", []
    for col, val in (("status", status), ("client_id", client_id), ("volunteer_id", volunteer_id)):
        if val is not None:
            q += f" AND {col}=?"
            args.append(val)
    with db() as con:
        return [dict(r) for r in con.execute(q + " ORDER BY date", args)]


class CompleteIn(BaseModel):
    duration_hours: float = Field(gt=0, le=12)


@private.post("/appointments/{aid}/complete")
def complete(aid: int, body: CompleteIn):
    with db() as con:
        a, c = con.execute("SELECT * FROM appointments WHERE id=?", (aid,)).fetchone(), None
        if not a or a["status"] != "matched":
            raise HTTPException(409, "Only matched appointments can be completed")
        v = con.execute("SELECT * FROM volunteers WHERE id=?", (a["volunteer_id"],)).fetchone()
        c = con.execute("SELECT * FROM clients WHERE id=?", (a["client_id"],)).fetchone()
        miles = round(2 * haversine(v["lat"], v["lng"], c["lat"], c["lng"]), 1)
        con.execute("UPDATE appointments SET status='completed', duration_hours=?, miles=? WHERE id=?",
                    (body.duration_hours, miles, aid))
    return {"ok": True, "miles": miles}


@private.post("/appointments/{aid}/cancel")
def cancel(aid: int):
    with db() as con:
        cur = con.execute("UPDATE appointments SET status='cancelled' WHERE id=? AND status IN ('open','matched')", (aid,))
        if not cur.rowcount:
            raise HTTPException(409, "Cannot cancel")
        log(con, "api", "appointment_cancelled", {"id": aid})
    return {"ok": True}


@private.get("/calendar")
def calendar_view(year: int, month: int = Query(..., ge=1, le=12),
                  client_id: Optional[int] = None, volunteer_id: Optional[int] = None):
    """Per-day entries for the month. Frontend decides the badge (client: matched/completed, volunteer: open)."""
    start, end = f"{year}-{month:02d}-01", f"{year + (month == 12)}-{(month % 12) + 1:02d}-01"
    q, args = "SELECT id,date,slot,service_type,status,client_id,volunteer_id FROM appointments WHERE date>=? AND date<?", [start, end]
    if client_id:
        q, args = q + " AND client_id=?", args + [client_id]
    if volunteer_id:
        q, args = q + " AND (volunteer_id=? OR status='open')", args + [volunteer_id]
    days = {}
    with db() as con:
        for r in con.execute(q, args):
            days.setdefault(r["date"], []).append(dict(r))
    return {"year": year, "month": month, "days": days}


# ----- private: agent tools (the agent proposes, the coordinator decides) -----
@private.get("/agent/open-work")
def open_work():
    """Appointments that still need a volunteer, with how many people are eligible."""
    with db() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM appointments WHERE status='open' ORDER BY date")]
        out = []
        for i in ids:
            a, c, ok, _ = evaluate(con, i)
            out.append({**a, "client": c["name"], "eligible_count": len(ok)})
    return out


@private.get("/agent/appointments/{aid}/matches")
def matches(aid: int):
    """Eligible volunteers ranked by score, plus who was excluded and why."""
    with db() as con:
        a, c, ok, ex = evaluate(con, aid)
    return {"appointment": a, "client": {"id": c["id"], "mobility": c["mobility"], "language": c["language"]},
            "candidates": ok, "excluded": ex}


class ProposalIn(BaseModel):
    appointment_id: int
    volunteer_id: int
    rationale: str = Field(min_length=5)
    proposed_by: str = "agent"


@private.post("/agent/proposals", status_code=201)
def propose(p: ProposalIn):
    """Guardrail: a volunteer who fails the hard constraints cannot be proposed."""
    with db() as con:
        a, _, ok, ex = evaluate(con, p.appointment_id)
        if a["status"] != "open":
            raise HTTPException(409, f"Appointment is {a['status']}")
        hit = next((o for o in ok if o["volunteer_id"] == p.volunteer_id), None)
        if not hit:
            why = next((e["reason"] for e in ex if e["volunteer_id"] == p.volunteer_id), "unknown volunteer")
            raise HTTPException(422, f"Volunteer is not eligible: {why}")
        cur = con.execute("INSERT INTO proposals(appointment_id,volunteer_id,score,rationale,proposed_by,created_at) VALUES(?,?,?,?,?,?)",
                          (p.appointment_id, p.volunteer_id, hit["score"], p.rationale, p.proposed_by, now()))
        log(con, p.proposed_by, "proposal_created", {"proposal": cur.lastrowid, "appointment": p.appointment_id, "volunteer": p.volunteer_id})
    return {"id": cur.lastrowid, "status": "pending", "score": hit["score"]}


@private.get("/agent/proposals")
def proposals(status: Optional[str] = "pending"):
    q = ("SELECT p.*, v.name AS volunteer, c.name AS client, a.service_type, a.date, a.slot FROM proposals p "
         "JOIN volunteers v ON v.id=p.volunteer_id JOIN appointments a ON a.id=p.appointment_id JOIN clients c ON c.id=a.client_id")
    with db() as con:
        rows = con.execute(q + (" WHERE p.status=?" if status else ""), (status,) if status else ()).fetchall()
    return [dict(r) for r in rows]


class DecisionIn(BaseModel):
    approve: bool
    coordinator: str
    note: str = ""


@private.post("/agent/proposals/{pid}/decision")
def decide(pid: int, d: DecisionIn):
    with db() as con:
        p = con.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not p:
            raise HTTPException(404, "Proposal not found")
        if p["status"] != "pending":
            raise HTTPException(409, f"Already {p['status']}")
        if d.approve:
            a, _, ok, _ = evaluate(con, p["appointment_id"])  # re-check: things may have changed
            if a["status"] != "open" or not any(o["volunteer_id"] == p["volunteer_id"] for o in ok):
                raise HTTPException(409, "No longer valid; ask the agent for a new proposal")
            con.execute("UPDATE appointments SET volunteer_id=?, status='matched' WHERE id=?", (p["volunteer_id"], p["appointment_id"]))
            con.execute("UPDATE proposals SET status='superseded' WHERE appointment_id=? AND status='pending' AND id!=?", (p["appointment_id"], pid))
        con.execute("UPDATE proposals SET status=?, note=?, decided_at=? WHERE id=?",
                    ("approved" if d.approve else "rejected", d.note, now(), pid))
        log(con, d.coordinator, "proposal_approved" if d.approve else "proposal_rejected", {"proposal": pid, "note": d.note})
    return {"ok": True}


@private.get("/agent/activity")
def activity(limit: int = Query(50, le=500)):
    with db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]


app.include_router(private)


# Map module imports names from this file, so it must be imported last.
from map_api import admin_router, public_router  # noqa: E402

app.include_router(public_router)
app.include_router(admin_router)