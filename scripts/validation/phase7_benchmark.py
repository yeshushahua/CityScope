"""Run repeatable Phase 7 emergency-response checks on the real database."""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import BigInteger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.routing import RoutePoint  # noqa: E402
from app.services.emergency import (  # noqa: E402
    EMERGENCY_COSTS_SQL,
    FACILITY_FILTERS,
    _costs_from_facilities_to_incident,
)
from app.services.routing import (  # noqa: E402
    EDGES_SQL,
    _facility_rows,
    _path_rows,
    build_isochrones_from_node,
    build_route_between_nodes,
    nearest_facility,
    snap_point_to_network,
)

CASES = [
    ("medical_center", "medical", 103.8343, 36.0611),
    ("medical_qilihe", "medical", 103.7800, 36.0600),
    ("medical_west", "medical", 103.6800, 36.0900),
    ("medical_east", "medical", 103.9300, 36.0500),
    ("medical_north_edge", "medical", 103.7500, 36.1300),
    ("fire_center", "fire", 103.8343, 36.0611),
    ("fire_qilihe", "fire", 103.7800, 36.0600),
    ("fire_west", "fire", 103.6800, 36.0900),
    ("fire_east", "fire", 103.9300, 36.0500),
    ("fire_north_edge", "fire", 103.7500, 36.1300),
]

SNAP_SQL = """
WITH query_point AS (
    SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geometry
)
SELECT n.osm_node_id
FROM road_nodes AS n CROSS JOIN query_point AS q
WHERE ST_DWithin(n.geometry::geography, q.geometry, 500)
ORDER BY n.geometry::geography <-> q.geometry, n.osm_node_id
LIMIT 1
"""

FACILITY_SQL = """
SELECT p.id, access.node_id, access.snap_distance_m
FROM pois AS p
JOIN poi_routing_access AS access ON access.poi_id = p.id
WHERE p.category = :category AND p.subcategory = :subcategory
ORDER BY p.id
"""


def timed(action):
    started = perf_counter()
    value = action()
    return value, round((perf_counter() - started) * 1000, 3)


def timing_summary(cases: list[dict], field: str) -> dict[str, float]:
    values = [float(case["timing_ms"][field]) for case in cases]
    return {
        "average": round(statistics.mean(values), 3),
        "minimum": round(min(values), 3),
        "maximum": round(max(values), 3),
    }


def explain(connection, statement, params: dict) -> list[str]:
    return list(connection.execute(statement, params).scalars())


def run_case(client: TestClient, label: str, incident_type: str, lon: float, lat: float) -> dict:
    point = RoutePoint(lon=lon, lat=lat)
    category, subcategory = FACILITY_FILTERS[incident_type]
    with SessionLocal() as db:
        incident_snap, snap_ms = timed(
            lambda: snap_point_to_network(db, lon=lon, lat=lat, max_snap_m=500)
        )
        facility_result, facility_lookup_ms = timed(
            lambda: _facility_rows(
                db, origin=point, category=category, subcategory=subcategory
            )
        )
        facility_total, facilities = facility_result
        source_nodes = sorted({int(row["node_id"]) for row in facilities})
        costs, candidate_routing_ms = timed(
            lambda: _costs_from_facilities_to_incident(
                db,
                source_nodes=source_nodes,
                incident_node=incident_snap.node_id,
            )
        )
        reachable = [row for row in facilities if int(row["node_id"]) in costs]
        reachable.sort(
            key=lambda row: (
                costs[int(row["node_id"])],
                float(row["snap_distance_m"]),
                float(row["straight_distance_m"]),
                int(row["poi_id"]),
            )
        )
        best = reachable[0]
        _, best_route_ms = timed(
            lambda: build_route_between_nodes(
                db,
                start_node=int(best["node_id"]),
                end_node=incident_snap.node_id,
                zero_coordinate=(float(best["node_lon"]), float(best["node_lat"])),
            )
        )
        _, isochrone_ms = timed(
            lambda: build_isochrones_from_node(db, start_node=int(best["node_id"]))
        )
        phase5 = nearest_facility(
            db,
            origin=point,
            category=category,
            subcategory=subcategory,
            max_snap_m=500,
            limit=3,
        )

    response, total_api_ms = timed(
        lambda: client.post(
            "/api/v1/emergency/response",
            json={
                "incident": {"lon": lon, "lat": lat},
                "incident_type": incident_type,
                "max_snap_m": 500,
                "candidate_limit": 3,
            },
        )
    )
    response.raise_for_status()
    body = response.json()
    recommended = body["recommended_facility"]
    phase5_best = phase5.best
    return {
        "label": label,
        "incident_type": incident_type,
        "incident": {"lon": lon, "lat": lat},
        "incident_snap": body["incident_snap"],
        "facility_statistics": body["facility_statistics"],
        "recommended": recommended,
        "candidates": body["candidate_facilities"],
        "response_route": body["response_route"]["properties"],
        "isochrone_bands": [
            feature["properties"] for feature in body["response_isochrones"]["features"]
        ],
        "straight_comparison": body["comparison"],
        "phase5_incident_to_facility": {
            "best_poi_id": phase5_best.poi_id,
            "best_name": phase5_best.name,
            "travel_time_s": phase5_best.travel_time_s,
            "differs_from_phase7_facility_to_incident": (
                phase5_best.poi_id != recommended["poi_id"]
                or phase5_best.travel_time_s != recommended["response_time_s"]
            ),
        },
        "source_node_count": len(source_nodes),
        "reachable_node_count": len(reachable),
        "facility_total": facility_total,
        "timing_ms": {
            "incident_snap": snap_ms,
            "facility_lookup": facility_lookup_ms,
            "candidate_routing": candidate_routing_ms,
            "best_route": best_route_ms,
            "isochrone": isochrone_ms,
            "total_api": total_api_ms,
        },
    }


def main() -> None:
    client = TestClient(app)
    client.get("/api/v1/health/database")
    client.post(
        "/api/v1/emergency/response",
        json={
            "incident": {"lon": CASES[0][2], "lat": CASES[0][3]},
            "incident_type": CASES[0][1],
        },
    ).raise_for_status()
    cases = [run_case(client, *case) for case in CASES]

    with engine.connect() as connection:
        center = cases[0]
        category, subcategory = FACILITY_FILTERS[center["incident_type"]]
        source_nodes = [candidate["node_id"] for candidate in center["candidates"]]
        # Use every mapped medical source for the representative many-to-one plan.
        source_nodes = list(
            connection.execute(
                text(
                    "SELECT DISTINCT access.node_id FROM pois p "
                    "JOIN poi_routing_access access ON access.poi_id=p.id "
                    "WHERE p.category=:category AND p.subcategory=:subcategory "
                    "ORDER BY access.node_id"
                ),
                {"category": category, "subcategory": subcategory},
            ).scalars()
        )
        snap_plan = explain(
            connection,
            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + SNAP_SQL),
            {"lon": center["incident"]["lon"], "lat": center["incident"]["lat"]},
        )
        facility_plan = explain(
            connection,
            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + FACILITY_SQL),
            {"category": category, "subcategory": subcategory},
        )
        cost_statement = text(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + EMERGENCY_COSTS_SQL
        ).bindparams(bindparam("source_nodes", type_=ARRAY(BigInteger)))
        cost_plan = explain(
            connection,
            cost_statement,
            {
                "edges_sql": EDGES_SQL,
                "source_nodes": source_nodes,
                "incident_node": center["incident_snap"]["node_id"],
            },
        )
        versions = connection.execute(
            text(
                "SELECT version(), PostGIS_Full_Version(), pgr_version(), "
                "(SELECT COUNT(*) FROM road_nodes), "
                "(SELECT COUNT(*) FROM routing_edges), "
                "(SELECT COUNT(*) FROM pois), "
                "(SELECT COUNT(*) FROM poi_routing_access)"
            )
        ).one()
        one_way = dict(
            connection.execute(
                text(
                    "SELECT id,osm_id,name,source,target,cost,reverse_cost "
                    "FROM routing_edges WHERE id=13266 AND osm_id='420345709'"
                )
            ).mappings().one()
        )

    with SessionLocal() as db:
        forward_rows = _path_rows(db, one_way["source"], one_way["target"])
        reverse_rows = _path_rows(db, one_way["target"], one_way["source"])
    one_way.update(
        {
            "forward_uses_edge": one_way["id"] in [row["edge"] for row in forward_rows],
            "reverse_uses_forbidden_edge": one_way["id"] in [row["edge"] for row in reverse_rows],
            "reverse_route_edge_count": len(reverse_rows),
        }
    )

    fields = [
        "incident_snap",
        "facility_lookup",
        "candidate_routing",
        "best_route",
        "isochrone",
        "total_api",
    ]
    output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "method": {
            "incident_types": ["medical", "fire"],
            "medical_filter": ["healthcare", "hospital"],
            "fire_filter": ["emergency", "fire_station"],
            "routing_direction": "facility_to_incident",
            "candidate_algorithm": "pgr_dijkstraCost_many_sources_to_one_target",
            "best_route_algorithm": "pgr_dijkstra",
            "cost_model": "static_travel_time",
            "directed": True,
            "candidate_limit": 3,
            "isochrone_thresholds_s": [300, 600, 900],
        },
        "database": {
            "postgresql": versions[0],
            "postgis": versions[1],
            "pgrouting": versions[2],
            "road_nodes": versions[3],
            "routing_edges": versions[4],
            "pois": versions[5],
            "poi_routing_access": versions[6],
        },
        "cases": cases,
        "summary_ms": {field: timing_summary(cases, field) for field in fields},
        "one_way_validation": one_way,
        "explain": {
            "incident_snap": snap_plan,
            "facility_lookup": facility_plan,
            "candidate_many_to_one": cost_plan,
        },
    }
    target = PROJECT_ROOT / "docs" / "phase-7-benchmark.json"
    target.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )
    print(json.dumps(output["summary_ms"], ensure_ascii=False, indent=2))
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
