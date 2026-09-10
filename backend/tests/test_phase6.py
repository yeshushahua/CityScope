import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import routing as routing_api
from app.db.session import engine
from app.main import app
from app.services.routing import (
    CONCAVE_HULL_TARGET_PERCENT,
    DEGENERATE_BUFFER_M,
    EDGES_SQL,
    ISOCHRONE_SQL,
    NESTING_TOLERANCE_M,
    WITH_POINTS_ISOCHRONE_SQL,
)

client = TestClient(app)
CENTER = {"lon": 103.8343, "lat": 36.0611}


@pytest.fixture(scope="module")
def center_isochrone() -> dict:
    response = client.get("/api/v1/routing/isochrone", params=CENTER)
    assert response.status_code == 200
    return response.json()


def test_isochrone_api_contract(center_isochrone: dict) -> None:
    assert center_isochrone["origin"] == CENTER
    assert center_isochrone["cost_model"] == "static_travel_time"
    assert center_isochrone["directed"] is True
    assert center_isochrone["max_analysis_time_s"] == 900
    features = center_isochrone["isochrones"]["features"]
    assert [item["properties"]["minutes"] for item in features] == [5, 10, 15]
    assert [item["properties"]["threshold_s"] for item in features] == [300, 600, 900]


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"lon": 102.9, "lat": 36.0}, "lon"),
        ({"lon": 105.1, "lat": 36.0}, "lon"),
        ({"lon": 103.8, "lat": 34.9}, "lat"),
        ({"lon": 103.8, "lat": 37.1}, "lat"),
        ({**CENTER, "max_snap_m": 99}, "max_snap_m"),
        ({**CENTER, "max_snap_m": 1001}, "max_snap_m"),
    ],
)
def test_isochrone_rejects_invalid_parameters(params: dict, field: str) -> None:
    response = client.get("/api/v1/routing/isochrone", params=params)
    assert response.status_code == 422
    assert field in response.text


def test_isochrone_snap_failure_is_a_business_error() -> None:
    response = client.get(
        "/api/v1/routing/isochrone",
        params={"lon": 103.0, "lat": 35.0, "max_snap_m": 100},
    )
    assert response.status_code == 422
    assert "within 100 meters" in response.json()["detail"]


def test_isochrone_database_error_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("database unavailable"))

    monkeypatch.setattr(routing_api, "isochrone", fail)
    response = client.get("/api/v1/routing/isochrone", params=CENTER)
    assert response.status_code == 503
    assert response.json()["detail"] == "Isochrone query failed"


def test_core_sql_uses_one_directed_900_second_driving_distance() -> None:
    normalized = " ".join(ISOCHRONE_SQL.lower().split())
    assert normalized.count("pgr_drivingdistance") == 1
    assert "900" in normalized
    assert "directed => true" in normalized
    assert "select id, source, target, cost, reverse_cost from routing_edges" not in normalized
    # The fixed edge SQL is supplied by the backend as a bind parameter.
    assert ":edges_sql" in normalized
    assert "d.agg_cost <= t.threshold_s" in normalized
    assert EDGES_SQL == "SELECT id, source, target, cost, reverse_cost FROM routing_edges"


def test_reachable_node_sets_are_nested() -> None:
    normalized = " ".join(WITH_POINTS_ISOCHRONE_SQL.lower().split())
    assert "pgr_withpointsdd" in normalized
    assert "cast(:start_vids as bigint[])" in normalized
    assert "equicost => true" in normalized
    assert "directed => true" in normalized


def test_reachable_sets_and_areas_are_monotonic(center_isochrone: dict) -> None:
    properties = [feature["properties"] for feature in center_isochrone["isochrones"]["features"]]
    counts = [item["reachable_node_count"] for item in properties]
    areas = [item["area_m2"] for item in properties]
    assert 0 < counts[0] <= counts[1] <= counts[2]
    assert 0 < areas[0] <= areas[1] <= areas[2]


def test_geometry_is_valid_polygonal_wgs84_and_nested(center_isochrone: dict) -> None:
    geometries = [feature["geometry"] for feature in center_isochrone["isochrones"]["features"]]
    assert all(geometry["type"] in {"Polygon", "MultiPolygon"} for geometry in geometries)
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                WITH geometries AS (
                    SELECT ST_SetSRID(ST_GeomFromGeoJSON(:iso5), 4326) AS iso5,
                           ST_SetSRID(ST_GeomFromGeoJSON(:iso10), 4326) AS iso10,
                           ST_SetSRID(ST_GeomFromGeoJSON(:iso15), 4326) AS iso15
                )
                SELECT ST_IsValid(iso5) AND ST_IsValid(iso10) AND ST_IsValid(iso15),
                       ST_SRID(iso5), ST_SRID(iso10), ST_SRID(iso15),
                       ST_Covers(iso10, iso5), ST_Covers(iso15, iso10)
                FROM geometries
                """
            ),
            {
                "iso5": json.dumps(geometries[0]),
                "iso10": json.dumps(geometries[1]),
                "iso15": json.dumps(geometries[2]),
            },
        ).one()
    assert result == (True, 4326, 4326, 4326, True, True)


def test_snap_distance_respects_requested_limit(center_isochrone: dict) -> None:
    assert 0 <= center_isochrone["snap"]["snap_distance_m"] <= 500


def test_degenerate_reachable_component_uses_safe_polygon_fallback() -> None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT ST_X(n.geometry) AS lon, ST_Y(n.geometry) AS lat
                FROM road_nodes AS n
                WHERE NOT EXISTS (
                    SELECT 1 FROM routing_edges AS e WHERE e.source = n.osm_node_id
                )
                ORDER BY n.osm_node_id
                LIMIT 1
                """
            )
        ).mappings().one()
    response = client.get("/api/v1/routing/isochrone", params=dict(row))
    assert response.status_code == 200
    features = response.json()["isochrones"]["features"]
    assert [item["properties"]["reachable_node_count"] for item in features] == [1, 1, 1]
    assert all(item["properties"]["area_m2"] > 0 for item in features)
    assert all(item["geometry"]["type"] in {"Polygon", "MultiPolygon"} for item in features)


def test_geometry_parameters_are_fixed_and_documentable() -> None:
    assert CONCAVE_HULL_TARGET_PERCENT == 0.85
    assert DEGENERATE_BUFFER_M == 20.0
    assert NESTING_TOLERANCE_M == 0.1


def test_one_way_edge_remains_directed_in_driving_distance() -> None:
    with engine.connect() as connection:
        edge = connection.execute(
            text(
                "SELECT id,source,target,cost,reverse_cost FROM routing_edges "
                "WHERE id=13266 AND osm_id='420345709'"
            )
        ).mappings().one()
        forward_edges = connection.execute(
            text(
                """
                SELECT edge FROM pgr_drivingDistance(
                    'SELECT id, source, target, cost, reverse_cost FROM routing_edges',
                    CAST(:start AS bigint), 900, directed => true
                ) WHERE node=:finish
                """
            ),
            {"start": edge["source"], "finish": edge["target"]},
        ).scalars().all()
        reverse_edges = connection.execute(
            text(
                """
                SELECT edge FROM pgr_drivingDistance(
                    'SELECT id, source, target, cost, reverse_cost FROM routing_edges',
                    CAST(:start AS bigint), 900, directed => true
                ) WHERE node=:finish
                """
            ),
            {"start": edge["target"], "finish": edge["source"]},
        ).scalars().all()
    assert edge["reverse_cost"] == -1
    assert edge["id"] in forward_edges
    assert edge["id"] not in reverse_edges
