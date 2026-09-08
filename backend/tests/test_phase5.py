import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.main import app
from app.schemas.routing import RoutePoint
from app.services.routing import EDGES_SQL, _path_rows, _route_feature, snap_point_to_network

client = TestClient(app)
CENTER = {"lon": 103.8343, "lat": 36.0611}


def test_road_node_geography_index_and_poi_access_mapping_exist() -> None:
    with engine.connect() as connection:
        index_definition = connection.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE tablename='road_nodes' "
                "AND indexname='idx_road_nodes_geography'"
            )
        )
        row = connection.execute(
            text(
                """
                SELECT COUNT(*) AS mapped,
                       COUNT(DISTINCT poi_id) AS unique_pois,
                       COUNT(*) FILTER (WHERE snap_distance_m > 500) AS too_far
                FROM poi_routing_access
                """
            )
        ).mappings().one()
    assert "using gist" in index_definition.lower()
    assert row == {"mapped": 106, "unique_pois": 106, "too_far": 0}


def test_snap_point_uses_meter_distance_and_real_node() -> None:
    with SessionLocal() as db:
        snap = snap_point_to_network(db, **CENTER, max_snap_m=500)
        exists = db.scalar(
            text("SELECT COUNT(*) FROM road_nodes WHERE osm_node_id=:node"),
            {"node": snap.node_id},
        )
    assert exists == 1
    assert 0 <= snap.snap_distance_m <= 500


def test_snap_failure_is_a_business_error() -> None:
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={
            "start": {"lon": 103.0, "lat": 35.0},
            "end": CENTER,
            "max_snap_m": 100,
        },
    )
    assert response.status_code == 422
    assert "within 100 meters" in response.json()["detail"]


def test_shortest_time_path_returns_real_directed_geometry() -> None:
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={"start": CENTER, "end": {"lon": 103.85, "lat": 36.07}},
    )
    assert response.status_code == 200
    body = response.json()
    route = body["route"]
    assert body["route_found"] is True
    assert route["geometry"]["type"] == "LineString"
    assert len(route["geometry"]["coordinates"]) > 2
    assert route["properties"]["routing_distance_m"] > 0
    assert route["properties"]["travel_time_s"] > 0
    assert route["properties"]["edge_count"] == len(route["properties"]["edge_ids"])
    assert body["start_snap"]["snap_distance_m"] <= 500
    assert body["end_snap"]["snap_distance_m"] <= 500


def test_route_distance_time_and_edge_continuity_match_database() -> None:
    body = client.post(
        "/api/v1/routing/shortest-path",
        json={"start": CENTER, "end": {"lon": 103.85, "lat": 36.07}},
    ).json()
    edge_ids = body["route"]["properties"]["edge_ids"]
    with engine.connect() as connection:
        rows = list(
            connection.execute(
                text(
                    "SELECT id,source,target,length_m,cost FROM routing_edges "
                    "WHERE id=ANY(:ids)"
                ),
                {"ids": edge_ids},
            ).mappings()
        )
    by_id = {row["id"]: row for row in rows}
    ordered = [by_id[edge_id] for edge_id in edge_ids]
    assert all(left["target"] == right["source"] for left, right in zip(ordered, ordered[1:]))
    assert math.isclose(
        body["route"]["properties"]["routing_distance_m"],
        sum(row["length_m"] for row in ordered),
        abs_tol=0.11,
    )
    assert math.isclose(
        body["route"]["properties"]["travel_time_s"],
        sum(row["cost"] for row in ordered),
        abs_tol=0.11,
    )


def test_same_snapped_node_returns_zero_network_route() -> None:
    with engine.connect() as connection:
        lon, lat = connection.execute(
            text("SELECT ST_X(geometry),ST_Y(geometry) FROM road_nodes ORDER BY osm_node_id LIMIT 1")
        ).one()
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={"start": {"lon": lon, "lat": lat}, "end": {"lon": lon, "lat": lat}},
    )
    assert response.status_code == 200
    properties = response.json()["route"]["properties"]
    assert properties == {
        "routing_distance_m": 0.0,
        "travel_time_s": 0.0,
        "travel_time_min": 0.0,
        "edge_count": 0,
        "edge_ids": [],
    }


def test_different_weak_components_return_no_route_not_500() -> None:
    with engine.connect() as connection:
        points = connection.execute(
            text(
                """
                WITH components AS (
                    SELECT component,node FROM pgr_connectedComponents(
                        'SELECT id,source,target,cost,reverse_cost FROM routing_edges'
                    )
                ), representatives AS (
                    SELECT component,MIN(node) node FROM components GROUP BY component
                    ORDER BY COUNT(*) DESC LIMIT 2
                )
                SELECT ST_X(n.geometry) lon,ST_Y(n.geometry) lat
                FROM representatives r JOIN road_nodes n ON n.osm_node_id=r.node
                ORDER BY r.component
                """
            )
        ).all()
    response = client.post(
        "/api/v1/routing/shortest-path",
        json={
            "start": {"lon": points[0][0], "lat": points[0][1]},
            "end": {"lon": points[1][0], "lat": points[1][1]},
            "max_snap_m": 100,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "No routable path between snapped nodes"


def test_oneway_edge_is_never_traversed_illegally_in_reverse() -> None:
    with engine.connect() as connection:
        edge = connection.execute(
            text(
                """
                SELECT e.id,e.source,e.target FROM routing_edges e
                WHERE e.oneway AND NOT EXISTS (
                    SELECT 1 FROM routing_edges r
                    WHERE r.source=e.target AND r.target=e.source
                )
                ORDER BY e.cost,e.id LIMIT 1
                """
            )
        ).mappings().one()
    with SessionLocal() as db:
        forward = _path_rows(db, edge["source"], edge["target"])
        reverse = _path_rows(db, edge["target"], edge["source"])
    assert edge["id"] in [row["edge"] for row in forward]
    assert edge["id"] not in [row["edge"] for row in reverse]
    assert "directed => true" in open("app/services/routing.py", encoding="utf-8").read()


def test_twenty_real_routes_are_continuous_and_avoid_positive_self_loops() -> None:
    with engine.connect() as connection:
        nodes = [
            row[0]
            for row in connection.execute(
                text(
                    """
                    WITH components AS (
                        SELECT component,node FROM pgr_strongComponents(
                            'SELECT id,source,target,cost,reverse_cost FROM routing_edges'
                        )
                    ), largest AS (
                        SELECT component FROM components GROUP BY component
                        ORDER BY COUNT(*) DESC LIMIT 1
                    )
                    SELECT node FROM components JOIN largest USING(component)
                    ORDER BY node LIMIT 21
                    """
                )
            )
        ]
    with SessionLocal() as db:
        for target in nodes[1:]:
            rows = _path_rows(db, nodes[0], target)
            route = _route_feature(rows)
            assert rows
            assert all(a["target"] == b["source"] for a, b in zip(rows, rows[1:]))
            assert all(row["source"] != row["target"] for row in rows)
            assert route.properties.travel_time_s == pytest.approx(
                sum(row["cost"] for row in rows), abs=0.11
            )
            assert route.properties.routing_distance_m == pytest.approx(
                sum(row["length_m"] for row in rows), abs=0.11
            )


def test_nearest_hospital_is_ranked_by_network_time() -> None:
    response = client.get(
        "/api/v1/routing/nearest-facility",
        params={**CENTER, "category": "healthcare", "subcategory": "hospital", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    times = [candidate["travel_time_s"] for candidate in body["candidates"]]
    assert times == sorted(times)
    assert body["best"] == body["candidates"][0]
    assert body["best"]["category"] == "healthcare"
    assert body["best"]["subcategory"] == "hospital"
    assert body["route"]["properties"]["travel_time_s"] == pytest.approx(times[0], abs=0.11)
    assert body["meta"]["facility_count"] == 58
    assert body["meta"]["reachable_count"] < body["meta"]["mapped_count"]


def test_network_best_hospital_differs_from_straight_nearest_real_case() -> None:
    body = client.get(
        "/api/v1/routing/nearest-facility",
        params={**CENTER, "category": "healthcare", "subcategory": "hospital", "limit": 10},
    ).json()
    straight_best = min(body["candidates"], key=lambda item: item["straight_distance_m"])
    assert straight_best["poi_id"] != body["best"]["poi_id"]
    assert straight_best["straight_distance_m"] < body["best"]["straight_distance_m"]


def test_nearest_fire_station_and_unreachable_filtering() -> None:
    response = client.get(
        "/api/v1/routing/nearest-facility",
        params={**CENTER, "category": "emergency", "subcategory": "fire_station", "limit": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {
        "facility_count": 4,
        "mapped_count": 4,
        "reachable_count": 3,
        "unreachable_count": 1,
        "returned_count": 3,
    }
    assert body["best"]["subcategory"] == "fire_station"
    assert [item["rank"] for item in body["candidates"]] == [1, 2, 3]


@pytest.mark.parametrize(
    "origin",
    [
        (103.72, 36.05),
        (103.78, 36.06),
        (103.8343, 36.0611),
        (103.90, 36.08),
        (104.00, 36.05),
    ],
)
@pytest.mark.parametrize(
    ("category", "subcategory"),
    [("healthcare", "hospital"), ("emergency", "fire_station")],
)
def test_nearest_facility_for_five_real_origins(
    origin: tuple[float, float], category: str, subcategory: str
) -> None:
    response = client.get(
        "/api/v1/routing/nearest-facility",
        params={
            "lon": origin[0],
            "lat": origin[1],
            "category": category,
            "subcategory": subcategory,
            "limit": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"]
    assert body["best"]["travel_time_s"] == min(
        item["travel_time_s"] for item in body["candidates"]
    )
    assert body["route"]["geometry"]["type"] == "LineString"


@pytest.mark.parametrize(
    "params",
    [
        {**CENTER, "category": "commercial"},
        {**CENTER, "category": "healthcare", "subcategory": "fire_station"},
        {**CENTER, "category": "emergency", "subcategory": "hospital"},
        {"lon": 102, "lat": 36, "category": "healthcare"},
        {**CENTER, "category": "healthcare", "max_snap_m": 99},
        {**CENTER, "category": "healthcare", "limit": 11},
    ],
)
def test_nearest_facility_rejects_invalid_input(params: dict[str, object]) -> None:
    assert client.get("/api/v1/routing/nearest-facility", params=params).status_code == 422


def test_shortest_path_rejects_invalid_input() -> None:
    assert client.post(
        "/api/v1/routing/shortest-path",
        json={"start": {"lon": 102, "lat": 36}, "end": CENTER},
    ).status_code == 422
    assert client.post(
        "/api/v1/routing/shortest-path",
        json={"start": CENTER, "end": CENTER, "max_snap_m": 1001},
    ).status_code == 422


def test_phase5_database_connection_and_direction_constraint() -> None:
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
        assert connection.scalar(
            text("SELECT COUNT(*) FROM routing_edges WHERE reverse_cost <> -1")
        ) == 0
    assert EDGES_SQL == "SELECT id, source, target, cost, reverse_cost FROM routing_edges"
