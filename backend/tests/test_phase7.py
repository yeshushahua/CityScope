import json
import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import emergency as emergency_api
from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.routing import RoutePoint
from app.services.emergency import (
    EMERGENCY_COSTS_SQL,
    FACILITY_FILTERS,
    _costs_from_facilities_to_incident,
)
from app.services.routing import (
    EDGES_SQL,
    FacilityNotFoundError,
    IsochroneGeometryError,
    ReachableFacilityNotFoundError,
    _facility_rows,
)

client = TestClient(app)
CENTER = {"lon": 103.8343, "lat": 36.0611}


@pytest.fixture(scope="module")
def medical_response() -> dict:
    response = client.post(
        "/api/v1/emergency/response",
        json={"incident": CENTER, "incident_type": "medical"},
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture(scope="module")
def fire_response() -> dict:
    response = client.post(
        "/api/v1/emergency/response",
        json={"incident": CENTER, "incident_type": "fire"},
    )
    assert response.status_code == 200
    return response.json()


def test_medical_uses_only_real_mapped_hospitals(medical_response: dict) -> None:
    assert FACILITY_FILTERS["medical"] == ("healthcare", "hospital")
    stats = medical_response["facility_statistics"]
    assert stats == {
        "total": 58,
        "mapped": 58,
        "unmapped": 0,
        "reachable": 57,
        "unreachable": 1,
        "returned": 3,
    }
    assert medical_response["recommended_facility"]["subcategory"] == "hospital"


def test_fire_uses_only_real_mapped_fire_stations(fire_response: dict) -> None:
    assert FACILITY_FILTERS["fire"] == ("emergency", "fire_station")
    stats = fire_response["facility_statistics"]
    assert stats["total"] == stats["mapped"] == 4
    assert stats["unmapped"] == 0
    assert stats["reachable"] + stats["unreachable"] == stats["mapped"]
    assert stats["returned"] == 3
    assert fire_response["recommended_facility"]["subcategory"] == "fire_station"


@pytest.mark.parametrize(
    "body",
    [
        {"incident": CENTER, "incident_type": "police"},
        {"incident": {"lon": 102.9, "lat": 36.0}, "incident_type": "medical"},
        {"incident": {"lon": 103.8, "lat": 37.1}, "incident_type": "medical"},
        {"incident": CENTER, "incident_type": "medical", "candidate_limit": 0},
        {"incident": CENTER, "incident_type": "medical", "candidate_limit": 11},
        {"incident": CENTER, "incident_type": "medical", "max_snap_m": 99},
        {"incident": CENTER, "incident_type": "medical", "max_snap_m": 1001},
    ],
)
def test_invalid_incident_parameters_return_422(body: dict) -> None:
    assert client.post("/api/v1/emergency/response", json=body).status_code == 422


def test_incident_snap_failure_returns_422() -> None:
    response = client.post(
        "/api/v1/emergency/response",
        json={
            "incident": {"lon": 103.0, "lat": 35.0},
            "incident_type": "medical",
            "max_snap_m": 100,
        },
    )
    assert response.status_code == 422
    assert "within 100 meters" in response.json()["detail"]


def test_many_sources_to_one_incident_sql_is_directed() -> None:
    normalized = " ".join(EMERGENCY_COSTS_SQL.lower().split())
    assert "pgr_dijkstracost" in normalized
    assert ":source_nodes" in normalized
    assert "cast(:incident_node as bigint)" in normalized
    assert "directed => true" in normalized
    assert EDGES_SQL == "SELECT id, source, target, cost, reverse_cost FROM routing_edges"


def test_recommended_facility_is_global_minimum_network_cost(
    medical_response: dict,
) -> None:
    candidates = medical_response["candidate_facilities"]
    assert medical_response["recommended_facility"] == candidates[0]
    assert [item["response_time_s"] for item in candidates] == sorted(
        item["response_time_s"] for item in candidates
    )


def test_candidate_ranking_excludes_unreachable_and_is_sorted(fire_response: dict) -> None:
    candidates = fire_response["candidate_facilities"]
    assert [candidate["network_rank"] for candidate in candidates] == [1, 2, 3]
    assert [candidate["response_time_s"] for candidate in candidates] == sorted(
        candidate["response_time_s"] for candidate in candidates
    )
    statistics = fire_response["facility_statistics"]
    assert statistics["reachable"] >= len(candidates)
    assert statistics["unreachable"] == statistics["mapped"] - statistics["reachable"]


@pytest.mark.parametrize("fixture_name", ["medical_response", "fire_response"])
def test_response_route_runs_facility_to_incident(
    fixture_name: str, request: pytest.FixtureRequest
) -> None:
    body = request.getfixturevalue(fixture_name)
    route = body["response_route"]
    edge_ids = route["properties"]["edge_ids"]
    assert route["properties"]["routing_direction"] == "facility_to_incident"
    assert route["properties"]["network_distance_m"] > 0
    assert route["properties"]["response_time_s"] > 0
    assert route["properties"]["edge_count"] == len(edge_ids) > 0
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id,source,target,length_m,cost FROM routing_edges "
                "WHERE id=ANY(:ids)"
            ),
            {"ids": edge_ids},
        ).mappings()
        by_id = {int(row["id"]): row for row in rows}
    ordered = [by_id[edge_id] for edge_id in edge_ids]
    assert all(a["target"] == b["source"] for a, b in zip(ordered, ordered[1:]))
    coordinates = route["geometry"]["coordinates"]
    assert coordinates[0] == pytest.approx(
        [
            body["recommended_facility"]["snapped_lon"],
            body["recommended_facility"]["snapped_lat"],
        ]
    )
    assert coordinates[-1] == pytest.approx(
        [body["incident_snap"]["snapped_lon"], body["incident_snap"]["snapped_lat"]]
    )
    assert route["properties"]["response_time_s"] <= sum(
        float(row["cost"]) for row in ordered
    )


def test_straight_nearest_comparison_is_real(fire_response: dict) -> None:
    comparison = fire_response["comparison"]
    assert comparison["network_best_facility_id"] == fire_response["recommended_facility"]["poi_id"]
    assert comparison["straight_nearest_is_network_best"] is (
        comparison["straight_nearest_facility_id"]
        == comparison["network_best_facility_id"]
    )


def test_recommended_facility_isochrones_are_valid_and_nested(
    fire_response: dict,
) -> None:
    features = fire_response["response_isochrones"]["features"]
    assert [feature["properties"]["minutes"] for feature in features] == [5, 10, 15]
    assert [feature["properties"]["reachable_node_count"] for feature in features] == sorted(
        feature["properties"]["reachable_node_count"] for feature in features
    )
    geometries = [json.dumps(feature["geometry"]) for feature in features]
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                WITH g AS (
                  SELECT ST_GeomFromGeoJSON(:a) a,
                         ST_GeomFromGeoJSON(:b) b,
                         ST_GeomFromGeoJSON(:c) c
                )
                SELECT ST_IsValid(a) AND ST_IsValid(b) AND ST_IsValid(c),
                       ST_Covers(b,a), ST_Covers(c,b)
                FROM g
                """
            ),
            {"a": geometries[0], "b": geometries[1], "c": geometries[2]},
        ).one()
    assert result == (True, True, True)


def test_phase5_incident_to_facility_direction_remains_unchanged() -> None:
    phase5 = client.get(
        "/api/v1/routing/nearest-facility",
        params={**CENTER, "category": "emergency", "subcategory": "fire_station"},
    )
    phase7 = client.post(
        "/api/v1/emergency/response",
        json={"incident": CENTER, "incident_type": "fire"},
    )
    assert phase5.status_code == phase7.status_code == 200
    assert phase5.json()["route"]["properties"]["edge_ids"] != phase7.json()["response_route"]["properties"]["edge_ids"]


def test_real_one_way_edge_is_not_used_in_forbidden_response_direction() -> None:
    with engine.connect() as connection:
        edge = connection.execute(
            text(
                "SELECT id,source,target,reverse_cost FROM routing_edges "
                "WHERE id=13266 AND osm_id='420345709'"
            )
        ).mappings().one()
        forward = connection.execute(
            text(
                """
                SELECT agg_cost FROM pgr_dijkstraCost(
                  'SELECT id, source, target, cost, reverse_cost FROM routing_edges',
                  ARRAY[CAST(:source AS bigint)], CAST(:target AS bigint), directed => true
                )
                """
            ),
            {"source": edge["source"], "target": edge["target"]},
        ).scalar_one()
        reverse_path_edges = connection.execute(
            text(
                """
                SELECT edge FROM pgr_dijkstra(
                  'SELECT id, source, target, cost, reverse_cost FROM routing_edges',
                  CAST(:source AS bigint), CAST(:target AS bigint), directed => true
                ) WHERE edge <> -1 ORDER BY path_seq
                """
            ),
            {"source": edge["target"], "target": edge["source"]},
        ).scalars().all()
    assert edge["reverse_cost"] == -1
    assert forward > 0
    assert edge["id"] not in reverse_path_edges


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (FacilityNotFoundError("none"), 404),
        (ReachableFacilityNotFoundError("unreachable"), 404),
        (IsochroneGeometryError("geometry"), 503),
        (OperationalError("SELECT", {}, Exception("db")), 503),
    ],
)
def test_emergency_error_classification(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(emergency_api, "analyze_emergency_response", fail)
    response = client.post(
        "/api/v1/emergency/response",
        json={"incident": CENTER, "incident_type": "medical"},
    )
    assert response.status_code == status
