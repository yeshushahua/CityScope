import json
import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import living_circle as living_circle_api
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.living_circle import (
    CONCAVE_HULL_TARGET_PERCENT,
    CORE_CATEGORIES,
    DEGENERATE_BUFFER_M,
    DISPLAY_LIMIT_PER_CATEGORY,
    LIVING_CIRCLE_SQL,
    NESTING_TOLERANCE_M,
    PEDESTRIAN_EDGES_SQL,
    WALK_SPEED_KPH,
    WALK_SPEED_MPS,
    LivingCircleGeometryError,
    PedestrianNetworkUnavailableError,
    PedestrianSnapNotFoundError,
    PoiWalkAccessUnavailableError,
)

client = TestClient(app)
CENTER = {"lon": 103.8343, "lat": 36.0611}


@pytest.fixture(scope="module")
def center_circle() -> dict:
    response = client.post(
        "/api/v1/living-circle/analyze",
        json={"origin": CENTER, "max_snap_m": 300},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_api_contract_uses_independent_walking_model(center_circle: dict) -> None:
    assert center_circle["origin"] == CENTER
    assert center_circle["walking_model"] == {
        "network_type": "walk",
        "cost_model": "static_walking_time",
        "walk_speed_kph": 4.8,
        "directed": True,
        "origin_connector_included": True,
        "poi_connector_included": True,
        "poi_eligibility": "network_cost",
        "service_area_method": "reachable_pedestrian_vertex_concave_hull",
    }
    assert WALK_SPEED_KPH == 4.8
    assert math.isclose(WALK_SPEED_MPS, 80 / 60)


def test_core_query_calls_one_directed_driving_distance() -> None:
    normalized = " ".join(LIVING_CIRCLE_SQL.lower().split())
    assert normalized.count("pgr_drivingdistance") == 1
    assert "directed => true" in normalized
    assert ":origin_connector_s + d.agg_cost" in normalized
    assert "access.snap_distance_m / :walk_speed_mps" in normalized
    assert "polygon" not in normalized
    assert PEDESTRIAN_EDGES_SQL == (
        "SELECT id, source, target, cost, reverse_cost FROM pedestrian_edges"
    )
    assert "routing_edges" not in PEDESTRIAN_EDGES_SQL


def test_real_pedestrian_graph_is_separate_and_contains_walking_ways() -> None:
    with engine.connect() as connection:
        pedestrian = connection.execute(
            text("SELECT (SELECT COUNT(*) FROM pedestrian_nodes), "
                 "(SELECT COUNT(*) FROM pedestrian_edges)")
        ).one()
        vehicle = connection.execute(
            text("SELECT (SELECT COUNT(*) FROM road_nodes), "
                 "(SELECT COUNT(*) FROM routing_edges)")
        ).one()
        walking_only_types = connection.scalar(text("""
          SELECT COUNT(*) FROM pedestrian_edges
          WHERE highway IN ('footway', 'path', 'pedestrian', 'steps')
        """))
    assert pedestrian[0] > 0 and pedestrian[1] > 0
    assert pedestrian != vehicle
    assert walking_only_types > 0


def test_phase8_tables_and_geometries_are_valid_wgs84() -> None:
    with engine.connect() as connection:
        tables = connection.execute(text("""
          SELECT to_regclass('public.pedestrian_nodes'),
                 to_regclass('public.pedestrian_edges'),
                 to_regclass('public.poi_walk_access')
        """)).one()
        invalid = connection.execute(text("""
          SELECT
            (SELECT COUNT(*) FROM pedestrian_nodes
             WHERE geometry IS NULL OR ST_IsEmpty(geometry)
                OR NOT ST_IsValid(geometry) OR ST_SRID(geometry)<>4326),
            (SELECT COUNT(*) FROM pedestrian_edges
             WHERE geometry IS NULL OR ST_IsEmpty(geometry)
                OR NOT ST_IsValid(geometry) OR ST_SRID(geometry)<>4326),
            (SELECT COUNT(*) FROM pedestrian_edges e
             LEFT JOIN pedestrian_nodes s ON s.osm_node_id=e.source
             LEFT JOIN pedestrian_nodes t ON t.osm_node_id=e.target
             WHERE s.osm_node_id IS NULL OR t.osm_node_id IS NULL)
        """)).one()
    assert all(tables)
    assert invalid == (0, 0, 0)


def test_pedestrian_edge_costs_are_static_directed_walking_times() -> None:
    with engine.connect() as connection:
        invalid = connection.scalar(text("""
          SELECT COUNT(*) FROM pedestrian_edges
          WHERE length_m <= 0 OR walk_speed_kph <> 4.8
             OR abs(travel_time_s - length_m / (4.8 / 3.6)) > 0.0001
             OR abs(cost - travel_time_s) > 0.0001 OR reverse_cost <> -1
             OR source <> u OR target <> v
        """))
    assert invalid == 0


def test_random_edge_topology_matches_directed_geometry_endpoints() -> None:
    with engine.connect() as connection:
        worst = connection.execute(text("""
          WITH sampled AS (
            SELECT * FROM pedestrian_edges ORDER BY md5(id::text) LIMIT 100
          )
          SELECT MAX(ST_Distance(ST_StartPoint(e.geometry)::geography, s.geometry::geography)),
                 MAX(ST_Distance(ST_EndPoint(e.geometry)::geography, t.geometry::geography))
          FROM sampled e
          JOIN pedestrian_nodes s ON s.osm_node_id=e.source
          JOIN pedestrian_nodes t ON t.osm_node_id=e.target
        """)).one()
    assert worst[0] < 1 and worst[1] < 1


def test_poi_walk_mapping_is_complete_within_explicit_limit(center_circle: dict) -> None:
    with engine.connect() as connection:
        total, mapped, invalid = connection.execute(text("""
          SELECT (SELECT COUNT(*) FROM pois),
                 (SELECT COUNT(*) FROM poi_walk_access),
                 (SELECT COUNT(*) FROM poi_walk_access
                  WHERE snap_distance_m < 0 OR snap_distance_m > 300)
        """)).one()
    quality = center_circle["data_quality"]
    assert quality["total_pois"] == total
    assert quality["mapped_pois"] == mapped
    assert quality["unmapped_pois"] == total - mapped
    assert invalid == 0


def test_origin_connector_is_counted_and_respects_snap_limit(center_circle: dict) -> None:
    snap = center_circle["origin_snap"]
    assert 0 <= snap["snap_distance_m"] <= 300
    assert math.isclose(
        snap["connector_time_s"], snap["snap_distance_m"] / WALK_SPEED_MPS,
        abs_tol=0.2,
    )
    for band in center_circle["isochrones"]["features"]:
        assert math.isclose(
            band["properties"]["network_budget_s"],
            band["properties"]["threshold_s"] - snap["connector_time_s"],
            abs_tol=0.11,
        )


def test_reachable_poi_total_time_includes_both_connectors(center_circle: dict) -> None:
    features = center_circle["reachable_pois"]["features"]
    assert features
    for feature in features:
        props = feature["properties"]
        assert props["category"] in CORE_CATEGORIES
        assert props["total_walk_time_s"] <= 900
        assert math.isclose(
            props["total_walk_time_s"],
            props["origin_connector_time_s"]
            + props["network_time_s"]
            + props["poi_connector_time_s"],
            abs_tol=0.2,
        )
        assert feature["geometry"]["type"] == "Point"


def test_category_counts_are_monotonic_and_coverage_is_presence_ratio(
    center_circle: dict,
) -> None:
    categories = center_circle["categories"]
    assert [item["category"] for item in categories] == list(CORE_CATEGORIES)
    for item in categories:
        assert 0 <= item["reachable_5min"] <= item["reachable_10min"] <= item["reachable_15min"]
    present = sum(item["reachable_15min"] > 0 for item in categories)
    assert center_circle["coverage"]["present_categories"] == present
    assert center_circle["coverage"]["presence_ratio"] == round(present / 5, 2)
    assert center_circle["coverage"]["definition"] == "reachable_core_category_presence"
    assert sum(item["reachable_poi_count"] for item in categories) == center_circle["summary"]["reachable_poi_count"]
    assert all(
        (item["nearest_poi"] is None) == (item["reachable_poi_count"] == 0)
        for item in categories
    )


def test_reachable_node_sets_are_true_subsets(center_circle: dict) -> None:
    snap = center_circle["origin_snap"]
    with engine.connect() as connection:
        rows = connection.execute(text("""
          SELECT node, agg_cost FROM pgr_drivingDistance(
            'SELECT id,source,target,cost,reverse_cost FROM pedestrian_edges',
            CAST(:node AS bigint), 900-:connector, directed=>true
          )
        """), {"node": snap["node_id"], "connector": snap["connector_time_s"]}).mappings()
        costs = {int(row["node"]): float(row["agg_cost"]) + snap["connector_time_s"] for row in rows}
    nodes5 = {node for node, cost in costs.items() if cost <= 300}
    nodes10 = {node for node, cost in costs.items() if cost <= 600}
    nodes15 = {node for node, cost in costs.items() if cost <= 900}
    assert nodes5 <= nodes10 <= nodes15


def test_display_limit_does_not_change_full_category_statistics(center_circle: dict) -> None:
    displayed = center_circle["reachable_pois"]["features"]
    for category in CORE_CATEGORIES:
        assert sum(f["properties"]["category"] == category for f in displayed) <= DISPLAY_LIMIT_PER_CATEGORY
    assert center_circle["data_quality"]["reachable_core_pois_15min"] >= len(displayed)


def test_walking_isochrones_are_valid_nested_and_monotonic(center_circle: dict) -> None:
    features = center_circle["isochrones"]["features"]
    assert [item["properties"]["minutes"] for item in features] == [5, 10, 15]
    counts = [item["properties"]["reachable_node_count"] for item in features]
    areas = [item["properties"]["area_m2"] for item in features]
    assert 0 < counts[0] <= counts[1] <= counts[2]
    assert 0 < areas[0] <= areas[1] <= areas[2]
    with engine.connect() as connection:
        result = connection.execute(text("""
          WITH g AS (
            SELECT ST_SetSRID(ST_GeomFromGeoJSON(:a),4326) a,
                   ST_SetSRID(ST_GeomFromGeoJSON(:b),4326) b,
                   ST_SetSRID(ST_GeomFromGeoJSON(:c),4326) c
          )
          SELECT ST_IsValid(a) AND ST_IsValid(b) AND ST_IsValid(c),
                 ST_Covers(b,a), ST_Covers(c,b) FROM g
        """), {
            "a": json.dumps(features[0]["geometry"]),
            "b": json.dumps(features[1]["geometry"]),
            "c": json.dumps(features[2]["geometry"]),
        }).one()
    assert result == (True, True, True)


@pytest.mark.parametrize("body", [
    {"origin": {"lon": 102.9, "lat": 36.0}},
    {"origin": {"lon": 105.1, "lat": 36.0}},
    {"origin": {"lon": 103.8, "lat": 34.9}},
    {"origin": {"lon": 103.8, "lat": 37.1}},
    {"origin": CENTER, "max_snap_m": 49},
    {"origin": CENTER, "max_snap_m": 301},
])
def test_invalid_request_parameters_return_422(body: dict) -> None:
    assert client.post("/api/v1/living-circle/analyze", json=body).status_code == 422


def test_snap_failure_returns_clear_422() -> None:
    response = client.post(
        "/api/v1/living-circle/analyze",
        json={"origin": {"lon": 103.0, "lat": 35.0}, "max_snap_m": 50},
    )
    assert response.status_code == 422
    assert "pedestrian network node" in response.json()["detail"]


@pytest.mark.parametrize(("error", "status"), [
    (PedestrianSnapNotFoundError("snap"), 422),
    (PoiWalkAccessUnavailableError("mapping"), 404),
    (PedestrianNetworkUnavailableError("network"), 503),
    (LivingCircleGeometryError("geometry"), 503),
    (OperationalError("SELECT", {}, Exception("db")), 503),
])
def test_living_circle_error_classification(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(living_circle_api, "analyze_living_circle", fail)
    response = client.post("/api/v1/living-circle/analyze", json={"origin": CENTER})
    assert response.status_code == status


def test_fixed_geometry_parameters_are_documentable() -> None:
    assert CONCAVE_HULL_TARGET_PERCENT == 0.85
    assert DEGENERATE_BUFFER_M == 20.0
    assert NESTING_TOLERANCE_M == 0.1
    normalized = " ".join(LIVING_CIRCLE_SQL.lower().split())
    assert "st_buffer(points_utm, :fallback_buffer_m)" in normalized
    assert "st_transform(n.geometry, 32648)" in normalized
