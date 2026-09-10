import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.main import app
from app.services.network_snapping import (
    EDGE_SNAP_SQL,
    SnapNotFoundError,
    WithPointsRegistry,
    snap_point_to_edge,
)


client = TestClient(app)
CENTER = {"lon": 103.8343, "lat": 36.0611}


def _point(edge_id: int, fraction: float) -> dict[str, float]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT ST_X(ST_LineInterpolatePoint(geometry,:fraction)) AS lon,
                       ST_Y(ST_LineInterpolatePoint(geometry,:fraction)) AS lat
                FROM routing_edges WHERE id=:edge_id
                """
            ),
            {"edge_id": edge_id, "fraction": fraction},
        ).mappings().one()
    return {"lon": float(row["lon"]), "lat": float(row["lat"])}


@pytest.fixture(scope="module")
def bidirectional_pair() -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    """
                    SELECT e.id,e.source,e.target,e.length_m,e.cost,
                           r.id AS reverse_id,r.cost AS reverse_cost
                    FROM routing_edges e
                    JOIN routing_edges r
                      ON r.source=e.target AND r.target=e.source
                     AND r.osm_id=e.osm_id AND r.id<>e.id
                    WHERE e.id<r.id AND e.source<>e.target AND e.length_m>100
                      AND ST_HausdorffDistance(
                            ST_Transform(e.geometry,32648),
                            ST_Transform(r.geometry,32648)
                          ) <= 1
                    ORDER BY e.length_m DESC,e.id LIMIT 1
                    """
                )
            ).mappings().one()
        )


@pytest.fixture(scope="module")
def strict_oneway_edge() -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    """
                    SELECT e.id,e.source,e.target,e.length_m,e.cost
                    FROM routing_edges e
                    WHERE e.oneway AND e.source<>e.target AND e.length_m>100
                      AND NOT EXISTS (
                        SELECT 1 FROM routing_edges r
                        WHERE r.source=e.target AND r.target=e.source
                      )
                    ORDER BY e.length_m DESC,e.id LIMIT 1
                    """
                )
            ).mappings().one()
        )


def test_snap_query_uses_gist_prefilter_and_exact_geography() -> None:
    normalized = " ".join(EDGE_SNAP_SQL.lower().split())
    assert "e.geometry &&" in normalized
    assert "st_dwithin( e.geometry::geography" in normalized
    assert "st_distance(e.geometry::geography" in normalized
    assert "e.source <> e.target" in normalized


def test_edge_interior_projection_and_pid_registration(
    bidirectional_pair: dict,
) -> None:
    point = _point(bidirectional_pair["id"], 0.35)
    with SessionLocal() as db:
        snap = snap_point_to_edge(db, **point, max_snap_m=100)
    assert len(snap.candidates) == 2
    assert {item.edge_id for item in snap.candidates} == {
        bidirectional_pair["id"],
        bidirectional_pair["reverse_id"],
    }
    assert all(0 <= item.fraction <= 1 for item in snap.candidates)
    assert snap.primary.snap_distance_m < 0.1
    registry = WithPointsRegistry()
    first = registry.register(snap)
    second = registry.register(snap)
    assert first.vids == second.vids
    assert len(first.vids) == len(set(first.vids)) == 2
    assert all(vid < 0 for vid in first.vids)


def test_exact_edge_endpoints_fold_to_real_vertices(
    bidirectional_pair: dict,
) -> None:
    with SessionLocal() as db:
        source = snap_point_to_edge(
            db, **_point(bidirectional_pair["id"], 0), max_snap_m=100
        )
        target = snap_point_to_edge(
            db, **_point(bidirectional_pair["id"], 1), max_snap_m=100
        )
    assert source.primary.node_id == bidirectional_pair["source"]
    assert source.primary.fraction == 0
    assert target.primary.node_id == bidirectional_pair["target"]
    assert target.primary.fraction == 1

    response = client.post(
        "/api/v1/routing/shortest-path",
        json={
            "start": _point(bidirectional_pair["id"], 0),
            "end": _point(bidirectional_pair["id"], 1),
            "max_snap_m": 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["start_snap"]["node_id"] == bidirectional_pair["source"]
    assert body["end_snap"]["node_id"] == bidirectional_pair["target"]


def test_snap_limit_failure_keeps_422_business_semantics() -> None:
    with SessionLocal() as db, pytest.raises(SnapNotFoundError, match="within 100 meters"):
        snap_point_to_edge(db, lon=103.0, lat=35.0, max_snap_m=100)
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={"start": {"lon": 103.0, "lat": 35.0}, "end": CENTER, "max_snap_m": 100},
    )
    assert response.status_code == 422


def test_same_directed_edge_uses_only_partial_length_and_cost(
    strict_oneway_edge: dict,
) -> None:
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={
            "start": _point(strict_oneway_edge["id"], 0.25),
            "end": _point(strict_oneway_edge["id"], 0.75),
            "max_snap_m": 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"]["properties"]["edge_ids"] == [strict_oneway_edge["id"]]
    start_fraction = body["start_snap"]["fraction"]
    end_fraction = body["end_snap"]["fraction"]
    expected_cost = strict_oneway_edge["cost"] * (end_fraction - start_fraction)
    assert body["route"]["properties"]["travel_time_s"] == pytest.approx(
        expected_cost, abs=0.11
    )
    assert body["route"]["properties"]["routing_distance_m"] < strict_oneway_edge["length_m"]
    coordinates = body["route"]["geometry"]["coordinates"]
    assert coordinates[0] == pytest.approx(
        [body["start_snap"]["snapped_lon"], body["start_snap"]["snapped_lat"]]
    )
    assert coordinates[-1] == pytest.approx(
        [body["end_snap"]["snapped_lon"], body["end_snap"]["snapped_lat"]]
    )


def test_bidirectional_reverse_uses_real_reverse_edge(
    bidirectional_pair: dict,
) -> None:
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={
            "start": _point(bidirectional_pair["id"], 0.75),
            "end": _point(bidirectional_pair["id"], 0.25),
            "max_snap_m": 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["start_snap"]["edge_id"] == bidirectional_pair["reverse_id"]
    assert body["end_snap"]["edge_id"] == bidirectional_pair["reverse_id"]
    assert body["route"]["properties"]["edge_ids"] == [bidirectional_pair["reverse_id"]]
    expected = bidirectional_pair["reverse_cost"] * (
        body["end_snap"]["fraction"] - body["start_snap"]["fraction"]
    )
    assert body["route"]["properties"]["travel_time_s"] == pytest.approx(expected, abs=0.11)


def test_oneway_reverse_cannot_take_illegal_direct_segment(
    strict_oneway_edge: dict,
) -> None:
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={
            "start": _point(strict_oneway_edge["id"], 0.75),
            "end": _point(strict_oneway_edge["id"], 0.25),
            "max_snap_m": 100,
        },
    )
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        properties = response.json()["route"]["properties"]
        assert properties["edge_count"] > 1
        assert properties["travel_time_s"] > strict_oneway_edge["cost"] * 0.5


def test_identical_points_return_zero_network_route() -> None:
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={"start": CENTER, "end": CENTER},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"]["properties"]["routing_distance_m"] == 0
    assert body["route"]["properties"]["travel_time_s"] == 0
    assert body["route"]["properties"]["edge_ids"] == []


def test_self_loops_are_not_edge_snap_candidates() -> None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT ST_X(ST_LineInterpolatePoint(loop.geometry,0.5)) AS lon,
                       ST_Y(ST_LineInterpolatePoint(loop.geometry,0.5)) AS lat
                FROM routing_edges loop
                WHERE loop.source=loop.target
                  AND EXISTS (
                    SELECT 1 FROM routing_edges normal
                    WHERE normal.source<>normal.target
                      AND ST_DWithin(
                        normal.geometry::geography,
                        ST_LineInterpolatePoint(loop.geometry,0.5)::geography,
                        500
                      )
                  )
                ORDER BY loop.id LIMIT 1
                """
            )
        ).mappings().one()
    with SessionLocal() as db:
        snap = snap_point_to_edge(
            db, lon=float(row["lon"]), lat=float(row["lat"]), max_snap_m=500
        )
    assert all(item.source != item.target for item in snap.candidates)


def test_facility_isochrone_and_emergency_use_edge_metadata() -> None:
    nearest = client.get(
        "/api/v1/routing/nearest-facility",
        params={**CENTER, "category": "emergency", "subcategory": "fire_station"},
    )
    isochrone = client.get("/api/v1/routing/isochrone", params=CENTER)
    emergency = client.post(
        "/api/v1/emergency/response",
        json={"incident": CENTER, "incident_type": "fire"},
    )
    assert nearest.status_code == isochrone.status_code == emergency.status_code == 200
    nearest_body = nearest.json()
    assert nearest_body["origin_snap"]["edge_id"] is not None
    assert nearest_body["best"]["edge_id"] is not None
    assert nearest_body["best"]["travel_time_s"] == min(
        item["travel_time_s"] for item in nearest_body["candidates"]
    )
    nearest_coordinates = nearest_body["route"]["geometry"]["coordinates"]
    assert nearest_coordinates[0] == pytest.approx(
        [
            nearest_body["origin_snap"]["snapped_lon"],
            nearest_body["origin_snap"]["snapped_lat"],
        ]
    )
    assert nearest_coordinates[-1] == pytest.approx(
        [nearest_body["best"]["snapped_lon"], nearest_body["best"]["snapped_lat"]]
    )
    bands = isochrone.json()["isochrones"]["features"]
    assert [item["properties"]["threshold_s"] for item in bands] == [300, 600, 900]
    emergency_body = emergency.json()
    assert emergency_body["incident_snap"]["edge_id"] is not None
    assert emergency_body["recommended_facility"]["edge_id"] is not None
    assert (
        emergency_body["response_route"]["properties"]["routing_direction"]
        == "facility_to_incident"
    )
    coordinates = emergency_body["response_route"]["geometry"]["coordinates"]
    assert coordinates[0] == pytest.approx(
        [
            emergency_body["recommended_facility"]["snapped_lon"],
            emergency_body["recommended_facility"]["snapped_lat"],
        ]
    )
    assert coordinates[-1] == pytest.approx(
        [
            emergency_body["incident_snap"]["snapped_lon"],
            emergency_body["incident_snap"]["snapped_lat"],
        ]
    )
