"""Bulk map data: 16 volunteers, 60 clients and 45 requests (added to the 4 and 3 from the site) around Philadelphia.

Everything here is synthetic: invented names, random points inside real neighborhood areas, no real addresses.
Requests cluster in three days and the volunteer pool is small, so requests compete for the same people
(a dense pool made every request easy and left the planner nothing to improve). Volunteers are concentrated in the center and west, clients lean toward the northeast and southwest, so the map
has real coverage gaps for the agent to find. Deterministic and safe to run twice.

Run:  python seed_map.py
"""
import json
import random
from datetime import date, timedelta

from main import SCHEMA, db, hard_constraints, seed, vol

SLOTS = ["morning", "afternoon", "evening"]
# name: (lat, lng, volunteer weight, client weight)
HOODS = {
    "Center City": (39.9526, -75.1652, 10, 5),
    "South Philadelphia": (39.9260, -75.1700, 6, 6),
    "West Philadelphia": (39.9570, -75.2100, 8, 5),
    "North Philadelphia": (39.9900, -75.1550, 4, 7),
    "Germantown": (40.0350, -75.1740, 4, 5),
    "Roxborough": (40.0350, -75.2200, 3, 3),
    "Kensington": (39.9900, -75.1200, 2, 7),
    "Northeast Philadelphia": (40.0400, -75.0600, 1, 8),
    "Southwest Philadelphia": (39.9300, -75.2300, 1, 7),
}
FIRST = ["Ava", "Noah", "Maya", "Liam", "Sofia", "Ethan", "Priya", "Lucas", "Nia", "Omar", "Grace", "Jin", "Rosa", "Elijah",
         "Hana", "Mateo", "Zoe", "Arjun", "Lena", "Caleb", "Imani", "Theo", "Mei", "Diego", "Ruth", "Amir", "Nora", "Kofi"]
LAST = ["Brooks", "Patel", "Nguyen", "Garcia", "Okafor", "Kim", "Rivera", "Cohen", "Ali", "Moreau", "Hughes", "Tran",
        "Silva", "Bennett", "Reyes", "Walker", "Chen", "Foster", "Diaz", "Mitchell", "Shah", "Lopez", "Grant", "Park"]
RADII = [4, 5, 6, 8, 10]  # travel radius choices in miles
ALL_SERVICES = ["grocery", "ride", "medication", "companionship", "tech", "home_prep", "mobility", "meal"]


def pick_point(rng, weight_index):
    names = list(HOODS)
    h = rng.choices(names, weights=[HOODS[n][weight_index] for n in names])[0]
    lat, lng = HOODS[h][0], HOODS[h][1]
    return h, round(lat + rng.uniform(-0.012, 0.012), 5), round(lng + rng.uniform(-0.015, 0.015), 5)


def run(n_vol=16, n_cli=60, n_req=45, seed_value=11):
    rng = random.Random(seed_value)
    with db() as con:
        con.executescript(SCHEMA)
        seed(con)
        if con.execute("SELECT COUNT(*) FROM volunteers").fetchone()[0] >= 20:
            return "already seeded"
        # The four volunteers from the site data get a tighter radius so coverage gaps exist in this dataset.
        con.execute("UPDATE volunteers SET radius_miles=6")
        for _ in range(n_vol):
            _, lat, lng = pick_point(rng, 2)
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            car = rng.random() < 0.6
            langs = ["English"] + (["Spanish"] if rng.random() < 0.2 else []) + (["Mandarin"] if rng.random() < 0.08 else [])
            av = {"days": sorted(rng.sample(range(7), rng.randint(3, 5))), "slots": sorted(rng.sample(SLOTS, rng.randint(1, 3)))}
            con.execute("INSERT INTO volunteers(name,email,lat,lng,radius_miles,categories,languages,availability,has_vehicle,wheelchair_vehicle) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (name, name.split()[0].lower() + str(rng.randint(10, 99)) + "@example.org", lat, lng, rng.choice(RADII),
                         json.dumps(rng.sample(ALL_SERVICES, rng.randint(2, 4))), json.dumps(langs), json.dumps(av),
                         int(car), int(car and rng.random() < 0.25)))
        for _ in range(n_cli):
            hood, lat, lng = pick_point(rng, 3)
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            con.execute("INSERT INTO clients(name,address,lat,lng,mobility,language,coordinator,notes) VALUES(?,?,?,?,?,?,?,?)",
                        (name, hood, lat, lng, rng.choices(["wheelchair", "walker", "none"], [2, 4, 4])[0],
                         rng.choices(["English", "Spanish", "Mandarin"], [15, 3, 1])[0], "Sarah Jenkins, MSW", "synthetic"))

        vols = [vol(r) for r in con.execute("SELECT * FROM volunteers")]
        clients = [dict(r) for r in con.execute("SELECT * FROM clients WHERE notes='synthetic'")]
        first_day, matched = date(2026, 10, 12), 0
        for i, c in enumerate(rng.sample(clients, n_req)):
            d = (first_day + timedelta(days=rng.randint(0, 2))).isoformat()
            a = {"service_type": rng.choice(ALL_SERVICES), "date": d, "slot": rng.choice(SLOTS[:2])}
            cur = con.execute("INSERT INTO appointments(client_id,service_type,date,slot,status,created_at) VALUES(?,?,?,?,?,?)",
                              (c["id"], a["service_type"], d, a["slot"], "open", "2026-10-11T00:00:00"))
            if i < 12:  # pre-match some so the map shows existing assignment lines
                busy = {r[0] for r in con.execute("SELECT volunteer_id FROM appointments WHERE date=? AND slot=? AND status='matched'", (d, a["slot"]))}
                wd = date.fromisoformat(d).weekday()
                options = [(dist, v["id"]) for v in vols for why, dist in [hard_constraints(v, c, a, wd, busy)] if not why]
                if options:
                    con.execute("UPDATE appointments SET volunteer_id=?, status='matched' WHERE id=?", (min(options)[1], cur.lastrowid))
                    matched += 1
        return f"seeded {n_vol} volunteers, {n_cli} clients, {n_req} requests ({matched} pre-matched)"


if __name__ == "__main__":
    print(run())