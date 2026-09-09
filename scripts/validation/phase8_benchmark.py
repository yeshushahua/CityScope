"""Run Phase 8 real-data cases, component timings, topology checks, and EXPLAIN."""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal, engine  # noqa: E402
from app.schemas.routing import RoutePoint  # noqa: E402
from app.services.living_circle import (  # noqa: E402
    CONCAVE_HULL_TARGET_PERCENT,
    PEDESTRIAN_EDGES_SQL,
    WALK_SPEED_MPS,
    analyze_living_circle,
    snap_to_pedestrian_network,
)

OUTPUT = PROJECT_ROOT / "docs" / "phase-8-benchmark.json"
CASES = (
    ("中心城区", 103.8343, 36.0611),
    ("七里河", 103.7700, 36.0600),
    ("安宁", 103.7200, 36.1000),
    ("东部", 103.9300, 36.0500),
    ("西部", 103.6500, 36.0800),
    ("南部边缘", 103.8242, 35.9932),
    ("北部边缘", 103.8325, 36.1470),
    ("东部边界", 104.0595, 36.0800),
    ("西部边界", 103.6100, 36.0700),
    ("东北边缘", 104.0197, 36.1485),
)


def elapsed_ms(action) -> tuple[Any, float]:
    started = time.perf_counter()
    value = action()
    return value, round((time.perf_counter() - started) * 1000, 3)


def component_benchmark(db, start_node: int, connector_s: float) -> dict[str, float]:
    db.execute(text("DROP TABLE IF EXISTS phase8_benchmark_driving"))
    _, pgr_ms = elapsed_ms(lambda: db.execute(text("""
      CREATE TEMP TABLE phase8_benchmark_driving ON COMMIT DROP AS
      SELECT node, agg_cost FROM pgr_drivingDistance(
        :edges_sql, CAST(:start_node AS bigint),
        GREATEST(0.0, 900.0 - :connector_s), directed => true
      )
    """), {
        "edges_sql": PEDESTRIAN_EDGES_SQL,
        "start_node": start_node,
        "connector_s": connector_s,
    }).close())
    _, poi_ms = elapsed_ms(lambda: db.execute(text("""
      SELECT COUNT(*) FROM phase8_benchmark_driving d
      JOIN poi_walk_access a ON a.node_id=d.node
      JOIN pois p ON p.id=a.poi_id
      WHERE p.category IN ('commercial','healthcare','education','recreation','transport')
        AND :connector_s + d.agg_cost + a.snap_distance_m/:speed <= 900
    """), {"connector_s": connector_s, "speed": WALK_SPEED_MPS}).scalar_one())
    _, geometry_ms = elapsed_ms(lambda: db.execute(text("""
      WITH thresholds(value) AS (VALUES (300),(600),(900))
      SELECT COUNT(*) FROM thresholds t
      CROSS JOIN LATERAL (
        SELECT ST_ConcaveHull(
          ST_Collect(ST_Transform(n.geometry,32648)), :hull, false
        ) AS geometry
        FROM phase8_benchmark_driving d
        JOIN pedestrian_nodes n ON n.osm_node_id=d.node
        WHERE d.agg_cost + :connector_s <= t.value
      ) area
      WHERE area.geometry IS NOT NULL
    """), {
        "connector_s": connector_s,
        "hull": CONCAVE_HULL_TARGET_PERCENT,
    }).scalar_one())
    return {
        "pgr_driving_distance_ms": pgr_ms,
        "poi_reachable_join_ms": poi_ms,
        "geometry_construction_ms": geometry_ms,
    }


def explain(connection, sql: str, params: dict[str, Any]) -> list[str]:
    rows = connection.execute(
        text("EXPLAIN (ANALYZE, BUFFERS) " + sql), params
    ).scalars()
    return [str(row) for row in rows]


def graph_quality(connection) -> dict[str, Any]:
    row = connection.execute(text("""
      SELECT
        (SELECT COUNT(*) FROM pedestrian_nodes) nodes,
        (SELECT COUNT(*) FROM pedestrian_edges) edges,
        (SELECT SUM(length_m) FROM pedestrian_edges) total_directed_edge_length_m,
        (SELECT COUNT(*) FROM pedestrian_edges
         WHERE source IS NULL OR target IS NULL) null_endpoints,
        (SELECT COUNT(*) FROM pedestrian_edges
         WHERE geometry IS NULL OR ST_IsEmpty(geometry) OR NOT ST_IsValid(geometry)) invalid_geometry,
        (SELECT COUNT(*) FROM pedestrian_edges WHERE ST_SRID(geometry)<>4326) wrong_srid,
        (SELECT COUNT(*) FROM pedestrian_edges
         WHERE length_m<=0 OR walk_speed_kph<=0 OR travel_time_s<=0 OR cost<=0) invalid_costs
    """)).mappings().one()
    topology = connection.execute(text("""
      WITH sampled AS (
        SELECT * FROM pedestrian_edges ORDER BY md5(id::text) LIMIT 100
      )
      SELECT MAX(ST_Distance(ST_StartPoint(e.geometry)::geography,s.geometry::geography)) start_error_m,
             MAX(ST_Distance(ST_EndPoint(e.geometry)::geography,t.geometry::geography)) end_error_m
      FROM sampled e
      JOIN pedestrian_nodes s ON s.osm_node_id=e.source
      JOIN pedestrian_nodes t ON t.osm_node_id=e.target
    """)).mappings().one()
    highway = connection.execute(text("""
      SELECT highway, COUNT(*) count FROM pedestrian_edges
      GROUP BY highway ORDER BY count DESC NULLS LAST
    """)).mappings()
    weak = connection.execute(text("""
      WITH memberships AS (
        SELECT component, COUNT(*) size FROM pgr_connectedComponents(
          'SELECT id,source,target,cost,reverse_cost FROM pedestrian_edges'
        ) GROUP BY component
      )
      SELECT COUNT(*) components, MAX(size) largest,
             MAX(size)::double precision/(SELECT COUNT(*) FROM pedestrian_nodes) largest_ratio
      FROM memberships
    """)).mappings().one()
    strong = connection.execute(text("""
      WITH memberships AS (
        SELECT component, COUNT(*) size FROM pgr_strongComponents(
          'SELECT id,source,target,cost,reverse_cost FROM pedestrian_edges'
        ) GROUP BY component
      )
      SELECT COUNT(*) components, MAX(size) largest,
             MAX(size)::double precision/(SELECT COUNT(*) FROM pedestrian_nodes) largest_ratio
      FROM memberships
    """)).mappings().one()
    return {
        **dict(row),
        "topology_sample_size": 100,
        "topology_max_start_error_m": float(topology["start_error_m"]),
        "topology_max_end_error_m": float(topology["end_error_m"]),
        "weak_components": dict(weak),
        "strong_components": dict(strong),
        "highway_counts": [dict(item) for item in highway],
    }


def poi_mapping_quality(connection) -> dict[str, Any]:
    overall = connection.execute(text("""
      SELECT (SELECT COUNT(*) FROM pois) total,
             COUNT(a.poi_id) mapped,
             (SELECT COUNT(*) FROM pois)-COUNT(a.poi_id) unmapped,
             AVG(a.snap_distance_m) average_snap_distance_m,
             MAX(a.snap_distance_m) maximum_snap_distance_m
      FROM poi_walk_access a
    """)).mappings().one()
    by_category = connection.execute(text("""
      SELECT p.category, COUNT(*) total, COUNT(a.poi_id) mapped,
             COUNT(*)-COUNT(a.poi_id) unmapped,
             AVG(a.snap_distance_m) average_snap_distance_m,
             MAX(a.snap_distance_m) maximum_snap_distance_m
      FROM pois p LEFT JOIN poi_walk_access a ON a.poi_id=p.id
      GROUP BY p.category ORDER BY p.category
    """)).mappings()
    return {**dict(overall), "by_category": [dict(row) for row in by_category]}


def hull_parameter_comparison(connection, node_id: int, connector_s: float) -> list[dict[str, Any]]:
    rows = connection.execute(text("""
      WITH driving AS MATERIALIZED (
        SELECT node,agg_cost FROM pgr_drivingDistance(
          'SELECT id,source,target,cost,reverse_cost FROM pedestrian_edges',
          CAST(:node AS bigint),900-:connector,directed=>true
        )
      ), percents(pct) AS (VALUES (0.70),(0.80),(0.85),(0.90)),
      thresholds(sec) AS (VALUES (300),(600),(900)),
      geometries AS (
        SELECT p.pct,t.sec,
               ST_ConcaveHull(ST_Collect(ST_Transform(n.geometry,32648)),p.pct,false) geometry
        FROM percents p CROSS JOIN thresholds t
        JOIN driving d ON d.agg_cost+:connector<=t.sec
        JOIN pedestrian_nodes n ON n.osm_node_id=d.node
        GROUP BY p.pct,t.sec
      )
      SELECT pct,sec,ST_Area(geometry)/1000000.0 area_km2,
             ST_IsValid(geometry) valid,ST_NumGeometries(ST_Multi(geometry)) parts
      FROM geometries ORDER BY pct,sec
    """), {"node": node_id, "connector": connector_s}).mappings()
    return [dict(row) for row in rows]


def timing_summary(cases: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    keys = (
        "origin_snapping_ms", "pgr_driving_distance_ms",
        "poi_reachable_join_ms", "geometry_construction_ms", "api_total_ms",
    )
    return {
        key: {
            "average": round(statistics.mean(case["timings"][key] for case in cases), 3),
            "min": min(case["timings"][key] for case in cases),
            "max": max(case["timings"][key] for case in cases),
        }
        for key in keys
    }


def main() -> None:
    results: list[dict[str, Any]] = []
    with SessionLocal() as db:
        # Warm up the database, pgRouting graph load, PostGIS functions, and Python models.
        analyze_living_circle(db, origin=RoutePoint(lon=CASES[0][1], lat=CASES[0][2]), max_snap_m=300)
        for name, lon, lat in CASES:
            origin = RoutePoint(lon=lon, lat=lat)
            snap, snap_ms = elapsed_ms(
                lambda: snap_to_pedestrian_network(db, lon=lon, lat=lat, max_snap_m=300)
            )
            components = component_benchmark(db, snap.node_id, snap.connector_time_s)
            response, total_ms = elapsed_ms(
                lambda: analyze_living_circle(db, origin=origin, max_snap_m=300)
            )
            bands = response.isochrones.features
            results.append({
                "name": name,
                "origin": {"lon": lon, "lat": lat},
                "snap_distance_m": response.origin_snap.snap_distance_m,
                "origin_connector_time_s": response.origin_snap.connector_time_s,
                "node_counts": {str(b.properties.minutes): b.properties.reachable_node_count for b in bands},
                "area_15min_km2": response.summary.area_15min_km2,
                "reachable_poi_count": response.summary.reachable_poi_count,
                "categories": {item.category: item.reachable_poi_count for item in response.categories},
                "covered_categories": response.summary.covered_categories,
                "coverage_ratio": response.summary.category_coverage_ratio,
                "timings": {"origin_snapping_ms": snap_ms, **components, "api_total_ms": total_ms},
            })
        db.rollback()

    with engine.connect() as connection:
        with Session(bind=connection) as db:
            center_snap = snap_to_pedestrian_network(
                db, lon=CASES[0][1], lat=CASES[0][2], max_snap_m=300
            )
        explanations = {
            "origin_snap": explain(connection, """
              WITH q AS (SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography geometry)
              SELECT n.osm_node_id FROM pedestrian_nodes n CROSS JOIN q
              WHERE ST_DWithin(n.geometry::geography,q.geometry,300)
              ORDER BY n.geometry::geography <-> q.geometry LIMIT 1
            """, {"lon": CASES[0][1], "lat": CASES[0][2]}),
            "poi_walk_access": explain(connection,
              "SELECT * FROM poi_walk_access WHERE node_id=:node", {"node": center_snap.node_id}),
            "reachable_poi_join": explain(connection, """
              WITH d AS MATERIALIZED (
                SELECT node,agg_cost FROM pgr_drivingDistance(
                  :edges_sql,CAST(:node AS bigint),900,directed=>true)
              )
              SELECT COUNT(*) FROM d JOIN poi_walk_access a ON a.node_id=d.node
              JOIN pois p ON p.id=a.poi_id
            """, {"edges_sql": PEDESTRIAN_EDGES_SQL, "node": center_snap.node_id}),
            "pgr_driving_distance": explain(connection, """
              SELECT * FROM pgr_drivingDistance(
                :edges_sql,CAST(:node AS bigint),900,directed=>true)
            """, {"edges_sql": PEDESTRIAN_EDGES_SQL, "node": center_snap.node_id}),
        }
        document = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cases": results,
            "timing_summary_ms": timing_summary(results),
            "graph_quality": graph_quality(connection),
            "poi_walk_access": poi_mapping_quality(connection),
            "concave_hull_parameter": {
                "selected": CONCAVE_HULL_TARGET_PERCENT,
                "reason": "valid single-part center geometries with more network detail than 0.90",
                "center_comparison": hull_parameter_comparison(
                    connection, center_snap.node_id, center_snap.connector_time_s
                ),
            },
            "explain_analyze_buffers": explanations,
        }
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(json.dumps(document, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
