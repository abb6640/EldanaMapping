"""Benchmark for the map backend. Run before and after every change the agent makes.

    python bench.py                    measure and compare with bench_baseline.json if it exists
    python bench.py --save-baseline    store this run as the baseline

Uses a fresh temporary database with the deterministic seed, so runs are comparable.
The agent may only keep a change if ALL checks pass and the score improves.
Score order: more matched requests first, then fewer total travel miles, then lower latency.
"""
import json
import os
import statistics
import sys
import tempfile
import time

os.environ["ELDANA_DB"] = os.path.join(tempfile.mkdtemp(), "bench.db")
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import map_api  # noqa: E402
import seed_map  # noqa: E402

KEY = {"X-API-Key": os.environ.get("ELDANA_ADMIN_KEY", "dev-admin-key")}
HERE = os.path.dirname(os.path.abspath(__file__))


def latency(client, path, headers=None, n=15):
    ms = []
    for _ in range(n):
        t = time.perf_counter()
        r = client.get(path, headers=headers)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
        ms.append((time.perf_counter() - t) * 1000)
    ms.sort()
    return {"p50_ms": round(statistics.median(ms), 1), "p95_ms": round(ms[int(0.95 * (len(ms) - 1))], 1)}


def decimals(x):
    s = repr(float(x))
    return len(s.split(".")[1]) if "." in s else 0


def run():
    out = {"checks": {}, "strategies": {}, "latency": {}}
    with TestClient(main.app) as c:
        out["seed"] = seed_map.run()

        # ---- guardrail 1: the public map must not leak private data ----
        pub = c.get("/api/map/geojson").json()
        text = json.dumps(pub)
        with main.db() as con:
            names = [r["name"] for r in con.execute("SELECT name FROM clients")]
            emails = [r["email"] for r in con.execute("SELECT email FROM volunteers")]
        clients = [f for f in pub["features"] if f["properties"]["layer"] == "client"]
        vols = [f for f in pub["features"] if f["properties"]["layer"] == "vol"]
        out["checks"]["public_has_no_client_names"] = not any(n in text for n in names)
        out["checks"]["public_has_no_volunteer_emails"] = not any(e in text for e in emails)
        out["checks"]["public_client_cells_min_size"] = all(f["properties"].get("count", 0) >= map_api.K_MIN for f in clients)
        out["checks"]["public_volunteer_coords_rounded"] = all(decimals(x) <= 2 for f in vols for x in f["geometry"]["coordinates"])
        out["checks"]["admin_requires_key"] = all(
            c.get(p).status_code == 401 for p in ["/api/map/admin/geojson", "/api/map/admin/stats", "/api/map/admin/optimize/preview"])

        # ---- guardrail 2 + objective: every planner strategy ----
        for name in sorted(map_api.STRATEGIES):
            r = c.get(f"/api/map/admin/optimize/preview?strategy={name}", headers=KEY).json()
            out["checks"][f"plan_valid[{name}]"] = r["violations"] == []
            out["checks"][f"plan_complete[{name}]"] = r["matched"] + len(r["unmatched_ids"]) == r["open_requests"]
            out["strategies"][name] = {k: r[k] for k in ("matched", "total_miles", "avg_miles", "compute_ms", "open_requests")}
            out["strategies"][name]["violations"] = r["violations"][:3]

        # ---- speed of the endpoints the website calls ----
        out["latency"]["public_geojson"] = latency(c, "/api/map/geojson")
        out["latency"]["admin_geojson"] = latency(c, "/api/map/admin/geojson", KEY)
        out["latency"]["deserts"] = latency(c, "/api/map/admin/deserts", KEY)
        out["latency"]["stats"] = latency(c, "/api/map/admin/stats", KEY)

    out["all_checks_pass"] = all(out["checks"].values())
    best = max(out["strategies"].values(), key=lambda s: (s["matched"], -s["total_miles"]))
    out["score"] = {"matched": best["matched"], "total_miles": best["total_miles"],
                    "public_geojson_p95_ms": out["latency"]["public_geojson"]["p95_ms"]}
    return out


if __name__ == "__main__":
    res = run()
    base_path = os.path.join(HERE, "bench_baseline.json")
    print(json.dumps(res, indent=2))
    if "--save-baseline" in sys.argv:
        json.dump(res, open(base_path, "w"), indent=2)
        print("\nbaseline saved")
    elif os.path.exists(base_path):
        b, s = json.load(open(base_path))["score"], res["score"]
        print("\nvs baseline:",
              f"matched {b['matched']} -> {s['matched']},",
              f"miles {b['total_miles']} -> {s['total_miles']},",
              f"geojson p95 {b['public_geojson_p95_ms']} -> {s['public_geojson_p95_ms']} ms")
    sys.exit(0 if res["all_checks_pass"] else 1)