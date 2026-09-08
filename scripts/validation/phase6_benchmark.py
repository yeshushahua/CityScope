"""Run repeatable Phase 6 benchmarks against the real CityScope database."""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.routing import (  # noqa: E402
    CONCAVE_HULL_TARGET_PERCENT,
    DEGENERATE_BUFFER_M,
    EDGES_SQL,
    ISOCHRONE_SQL,
    NESTING_TOLERANCE_M,
    snap_point_to_network,
)

POINTS = [
    ("west_edge", 103.6200, 36.0700),
    ("west", 103.6800, 36.0900),
    ("qilihe_west", 103.7200, 36.0500),
    ("qilihe", 103.7800, 36.0600),
    ("city_center", 103.8343, 36.0611),
    ("chengguan_east", 103.8800, 36.0600),
    ("east", 103.9300, 36.0500),
    ("east_edge", 104.0000, 36.0600),
    ("northwest_edge", 103.7500, 36.1300),
    ("northeast_edge", 103.9100, 36.1200),
]

DRIVING_SQL = """
SELECT node, edge, agg_cost
FROM pgr_drivingDistance(
    :edges_sql, CAST(:start_node AS bigint), 900, directed => true
)
"""

SNAP_SQL = """
WITH query_point AS (
    SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geometry
)
SELECT n.osm_node_id,
       ST_Distance(n.geometry::geography, q.geometry) AS snap_distance_m
FROM road_nodes AS n
CROSS JOIN query_point AS q
WHERE ST_DWithin(n.geometry::geography, q.geometry, 500)
ORDER BY n.geometry::geography <-> q.geometry, n.osm_node_id
LIMIT 1
"""


def elapsed_ms(action):
    started = perf_counter()
    value = action()
    return value, (perf_counter() - started) * 1000


def summary(values: list[float]) -> dict[str, float]:
    return {
        "average": round(statistics.mean(values), 3),
        "minimum": round(min(values), 3),
        "maximum": round(max(values), 3),
    }


def explain(connection, sql: str, params: dict) -> list[str]:
    rows = connection.execute(
        text("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql), params
    ).scalars()
    return list(rows)


def main() -> None:
    client = TestClient(app)
    geometry_params = {
        "edges_sql": EDGES_SQL,
        "hull_target_percent": CONCAVE_HULL_TARGET_PERCENT,
        "fallback_buffer_m": DEGENERATE_BUFFER_M,
        "nesting_tolerance_m": NESTING_TOLERANCE_M,
    }

    # Warm the connection pool, pgRouting edge load, geometry functions, and TestClient.
    client.get("/api/v1/health/database")
    client.get(
        "/api/v1/routing/isochrone",
        params={"lon": POINTS[0][1], "lat": POINTS[0][2]},
    )

    cases: list[dict] = []
    for label, lon, lat in POINTS:
        with SessionLocal() as session:
            snap, snap_ms = elapsed_ms(
                lambda: snap_point_to_network(
                    session, lon=lon, lat=lat, max_snap_m=500
                )
            )
        with engine.connect() as connection:
            driving_rows, driving_ms = elapsed_ms(
                lambda: connection.execute(
                    text(DRIVING_SQL),
                    {"edges_sql": EDGES_SQL, "start_node": snap.node_id},
                ).fetchall()
            )
            geometry_rows, database_ms = elapsed_ms(
                lambda: connection.execute(
                    text(ISOCHRONE_SQL),
                    {**geometry_params, "start_node": snap.node_id},
                ).fetchall()
            )
        response, total_api_ms = elapsed_ms(
            lambda: client.get(
                "/api/v1/routing/isochrone", params={"lon": lon, "lat": lat}
            )
        )
        response.raise_for_status()
        body = response.json()
        cases.append(
            {
                "label": label,
                "origin": {"lon": lon, "lat": lat},
                "snap": body["snap"],
                "timing_ms": {
                    "snap": round(snap_ms, 3),
                    "driving_distance": round(driving_ms, 3),
                    "geometry": round(max(database_ms - driving_ms, 0), 3),
                    "database_total": round(database_ms, 3),
                    "total_api": round(total_api_ms, 3),
                },
                "driving_row_count": len(driving_rows),
                "database_band_count": len(geometry_rows),
                "bands": [feature["properties"] for feature in body["isochrones"]["features"]],
            }
        )

    with engine.connect() as connection:
        center_snap = cases[4]["snap"]
        snap_plan = explain(
            connection,
            SNAP_SQL,
            {"lon": POINTS[4][1], "lat": POINTS[4][2]},
        )
        core_plan = explain(
            connection,
            ISOCHRONE_SQL,
            {**geometry_params, "start_node": center_snap["node_id"]},
        )
        versions = connection.execute(
            text(
                "SELECT version(), PostGIS_Full_Version(), pgr_version(), "
                "(SELECT COUNT(*) FROM road_nodes), "
                "(SELECT COUNT(*) FROM routing_edges)"
            )
        ).one()
        one_way = connection.execute(
            text(
                "SELECT id,osm_id,source,target,cost,reverse_cost "
                "FROM routing_edges WHERE id=13266 AND osm_id='420345709'"
            )
        ).mappings().one()
        forward = connection.execute(
            text(DRIVING_SQL + " WHERE node=:finish"),
            {
                "edges_sql": EDGES_SQL,
                "start_node": one_way["source"],
                "finish": one_way["target"],
            },
        ).mappings().one_or_none()
        reverse = connection.execute(
            text(DRIVING_SQL + " WHERE node=:finish"),
            {
                "edges_sql": EDGES_SQL,
                "start_node": one_way["target"],
                "finish": one_way["source"],
            },
        ).mappings().one_or_none()

    timing_fields = [
        "snap", "driving_distance", "geometry", "database_total", "total_api"
    ]
    output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "method": {
            "cost_model": "static_travel_time",
            "directed": True,
            "thresholds_s": [300, 600, 900],
            "single_driving_distance_per_query": True,
            "concave_hull_target_percent": CONCAVE_HULL_TARGET_PERCENT,
            "degenerate_buffer_m": DEGENERATE_BUFFER_M,
            "nesting_tolerance_m": NESTING_TOLERANCE_M,
            "geometry_timing_note": "database_total minus standalone driving-distance time",
        },
        "database": {
            "postgresql": versions[0],
            "postgis": versions[1],
            "pgrouting": versions[2],
            "road_nodes": versions[3],
            "routing_edges": versions[4],
        },
        "cases": cases,
        "summary_ms": {
            field: summary([case["timing_ms"][field] for case in cases])
            for field in timing_fields
        },
        "one_way_validation": {
            "edge": dict(one_way),
            "forward_target_result": dict(forward) if forward else None,
            "reverse_source_result": dict(reverse) if reverse else None,
            "reverse_did_not_use_forbidden_edge": reverse is None
            or reverse.get("edge") != one_way["id"],
        },
        "explain": {
            "snap": snap_plan,
            "isochrone_core": core_plan,
        },
    }
    target = PROJECT_ROOT / "docs" / "phase-6-benchmark.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["summary_ms"], ensure_ascii=False, indent=2))
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
