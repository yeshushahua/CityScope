"""Repeatable Phase 5 integration benchmark against the local PostGIS database."""

import hashlib
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.routing import RoutePoint  # noqa: E402
from app.services.routing import (  # noqa: E402
    _path_rows,
    nearest_facility,
    snap_point_to_network,
)

client = TestClient(app)
EXAMPLE_PAIRS = [
    ((103.8343, 36.0611), (103.8500, 36.0700)),
    ((103.7200, 36.0500), (103.7800, 36.0600)),
    ((103.7800, 36.0600), (103.9000, 36.0800)),
]
ORIGINS = [
    (103.7200, 36.0500),
    (103.7800, 36.0600),
    (103.8343, 36.0611),
    (103.9000, 36.0800),
    (104.0000, 36.0500),
]


def milliseconds(start: float) -> float:
    return round((perf_counter() - start) * 1000, 2)


def strongest_component_points() -> list[tuple[float, float]]:
    with engine.connect() as connection:
        return [
            (float(row.lon), float(row.lat))
            for row in connection.execute(text("""
                WITH components AS (
                    SELECT component,node FROM pgr_strongComponents(
                        'SELECT id,source,target,cost,reverse_cost FROM routing_edges'
                    )
                ), largest AS (
                    SELECT component FROM components GROUP BY component
                    ORDER BY COUNT(*) DESC LIMIT 1
                ), numbered AS (
                    SELECT node, row_number() OVER (ORDER BY node) rn,
                           count(*) OVER () total
                    FROM components JOIN largest USING(component)
                )
                SELECT ST_X(n.geometry) lon,ST_Y(n.geometry) lat
                FROM numbered x JOIN road_nodes n ON n.osm_node_id=x.node
                WHERE rn IN (1, total/10, total/5, total*3/10, total*2/5,
                             total/2, total*3/5, total*7/10, total*4/5,
                             total*9/10, total)
                ORDER BY rn
            """))
        ]


def route_case(start: tuple[float, float], end: tuple[float, float]) -> dict[str, object]:
    with SessionLocal() as db:
        began = perf_counter()
        start_snap = snap_point_to_network(db, lon=start[0], lat=start[1], max_snap_m=500)
        end_snap = snap_point_to_network(db, lon=end[0], lat=end[1], max_snap_m=500)
        snap_ms = milliseconds(began)
        began = perf_counter()
        rows = _path_rows(db, start_snap.node_id, end_snap.node_id)
        routing_ms = milliseconds(began)
    began = perf_counter()
    response = client.post("/api/v1/routing/shortest-path", json={
        "start": {"lon": start[0], "lat": start[1]},
        "end": {"lon": end[0], "lat": end[1]},
    })
    api_ms = milliseconds(began)
    response.raise_for_status()
    body = response.json()
    props = body["route"]["properties"]
    return {
        "start": start,
        "end": end,
        "start_snap_m": body["start_snap"]["snap_distance_m"],
        "end_snap_m": body["end_snap"]["snap_distance_m"],
        "routing_distance_m": props["routing_distance_m"],
        "travel_time_s": props["travel_time_s"],
        "edge_count": props["edge_count"],
        "snap_ms": snap_ms,
        "routing_ms": routing_ms,
        "api_ms": api_ms,
        "direct_rows": len(rows),
    }


def facility_case(origin: tuple[float, float], category: str, subcategory: str) -> dict[str, object]:
    route_point = RoutePoint(lon=origin[0], lat=origin[1])
    with SessionLocal() as db:
        began = perf_counter()
        snap_point_to_network(db, lon=origin[0], lat=origin[1], max_snap_m=500)
        snap_ms = milliseconds(began)
        began = perf_counter()
        result = nearest_facility(
            db, origin=route_point, category=category, subcategory=subcategory,
            max_snap_m=500, limit=5,
        )
        service_ms = milliseconds(began)
    began = perf_counter()
    response = client.get("/api/v1/routing/nearest-facility", params={
        "lon": origin[0], "lat": origin[1], "category": category,
        "subcategory": subcategory, "limit": 5,
    })
    api_ms = milliseconds(began)
    response.raise_for_status()
    body = response.json()
    best = body["best"]
    straight_best = min(body["candidates"], key=lambda item: item["straight_distance_m"])
    return {
        "origin": origin,
        "best_poi_id": best["poi_id"],
        "best_name": best["name"],
        "straight_distance_m": best["straight_distance_m"],
        "network_distance_m": best["network_distance_m"],
        "travel_time_s": best["travel_time_s"],
        "facility_snap_m": best["facility_snap_distance_m"],
        "straight_best_poi_id": straight_best["poi_id"],
        "straight_best_name": straight_best["name"],
        "straight_best_distance_m": straight_best["straight_distance_m"],
        "straight_best_travel_time_s": straight_best["travel_time_s"],
        "network_best_differs_from_straight": straight_best["poi_id"] != best["poi_id"],
        "reachable_count": result.meta.reachable_count,
        "unreachable_count": result.meta.unreachable_count,
        "snap_ms": snap_ms,
        "routing_ms": round(max(0, service_ms - snap_ms), 2),
        "api_ms": api_ms,
    }


def explain_plans() -> dict[str, list[str]]:
    with engine.connect() as connection:
        snap = [row[0] for row in connection.execute(text("""
            EXPLAIN (ANALYZE, BUFFERS)
            WITH q AS (SELECT ST_SetSRID(ST_MakePoint(103.8343,36.0611),4326)::geography g)
            SELECT n.osm_node_id FROM road_nodes n CROSS JOIN q
            WHERE ST_DWithin(n.geometry::geography,q.g,500)
            ORDER BY n.geometry::geography <-> q.g,n.osm_node_id LIMIT 1
        """))]
        facility = [row[0] for row in connection.execute(text("""
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT p.id,nearest.osm_node_id,nearest.snap_distance_m
            FROM pois p
            JOIN LATERAL (
                SELECT n.osm_node_id,
                       ST_Distance(n.geometry::geography,p.geometry::geography) snap_distance_m
                FROM road_nodes n
                WHERE ST_DWithin(n.geometry::geography,p.geometry::geography,500)
                ORDER BY n.geometry::geography <-> p.geometry::geography,n.osm_node_id
                LIMIT 1
            ) nearest ON true
            WHERE p.category='healthcare' AND p.subcategory='hospital'
            ORDER BY p.id
        """))]
    return {"road_node_snap": snap, "facility_lookup": facility}


def summary(values: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    return {
        key: {
            "average_ms": round(statistics.mean(float(row[key]) for row in values), 2),
            "median_ms": round(statistics.median(float(row[key]) for row in values), 2),
            "max_ms": round(max(float(row[key]) for row in values), 2),
        }
        for key in ("snap_ms", "routing_ms", "api_ms")
    }


def main() -> None:
    strong = strongest_component_points()
    performance_pairs = [(strong[0], point) for point in strong[1:11]]
    point_to_point = [route_case(start, end) for start, end in performance_pairs]
    examples = [route_case(start, end) for start, end in EXAMPLE_PAIRS]
    hospitals = [facility_case(origin, "healthcare", "hospital") for origin in ORIGINS]
    fire_stations = [facility_case(origin, "emergency", "fire_station") for origin in ORIGINS]
    with engine.connect() as connection:
        mapping_text = connection.scalar(text("""
            SELECT string_agg(poi_id::text || ':' || node_id::text || ':' ||
                              round(snap_distance_m::numeric,6)::text, ',' ORDER BY poi_id)
            FROM poi_routing_access
        """)) or ""
        mapping_stats = [dict(row) for row in connection.execute(text("""
            SELECT p.category,COUNT(*) AS facility_count,
                   COUNT(a.poi_id) AS mapped_count,
                   COUNT(*)-COUNT(a.poi_id) AS unmapped_count,
                   round(AVG(a.snap_distance_m)::numeric,2) AS average_snap_m,
                   round(MAX(a.snap_distance_m)::numeric,2) AS max_snap_m
            FROM pois p LEFT JOIN poi_routing_access a ON a.poi_id=p.id
            WHERE p.category IN ('healthcare','emergency')
            GROUP BY p.category ORDER BY p.category
        """ )).mappings()]
        one_way = dict(connection.execute(text("""
            SELECT e.id,e.osm_id,e.name,e.highway,e.source,e.target,
                   e.length_m,e.cost
            FROM routing_edges e
            WHERE e.oneway AND NOT EXISTS (
                SELECT 1 FROM routing_edges r
                WHERE r.source=e.target AND r.target=e.source
            ) ORDER BY e.cost,e.id LIMIT 1
        """)).mappings().one())
    with SessionLocal() as db:
        forward_rows = _path_rows(db, one_way["source"], one_way["target"])
        reverse_rows = _path_rows(db, one_way["target"], one_way["source"])
    one_way.update({
        "forward_uses_edge": one_way["id"] in [row["edge"] for row in forward_rows],
        "reverse_uses_edge": one_way["id"] in [row["edge"] for row in reverse_rows],
        "reverse_route_edges": len(reverse_rows),
        "reverse_route_distance_m": round(sum(float(row["length_m"]) for row in reverse_rows),1),
        "reverse_route_time_s": round(sum(float(row["cost"]) for row in reverse_rows),1),
    })
    result = {
        "mapping": {
            "count": len(mapping_text.split(',')) if mapping_text else 0,
            "sha256": hashlib.sha256(mapping_text.encode()).hexdigest(),
            "categories": mapping_stats,
        },
        "one_way": one_way,
        "examples": examples,
        "point_to_point": point_to_point,
        "hospital": hospitals,
        "fire_station": fire_stations,
        "performance": {
            "point_to_point_10": summary(point_to_point),
            "hospital_5": summary(hospitals),
            "fire_station_5": summary(fire_stations),
        },
        "explain": explain_plans(),
    }
    output = PROJECT_ROOT / "docs" / "phase-5-benchmark.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
