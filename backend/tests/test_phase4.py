from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app

client = TestClient(app)
CENTRAL_BBOX = "103.82,36.04,103.84,36.06"


def test_pgrouting_extension_is_available() -> None:
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT pgr_version()"))
    assert version is not None


def test_routing_edges_are_complete_and_traceable() -> None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT COUNT(*) AS edges,
                       COUNT(*) FILTER (WHERE source IS NULL) AS null_source,
                       COUNT(*) FILTER (WHERE target IS NULL) AS null_target,
                       COUNT(*) FILTER (WHERE r.road_edge_id IS NULL) AS untraced,
                       COUNT(e.id) AS matched_raw_edges
                FROM routing_edges r
                LEFT JOIN road_edges e ON e.id = r.road_edge_id
                """
            )
        ).mappings().one()
    assert row == {
        "edges": 18441,
        "null_source": 0,
        "null_target": 0,
        "untraced": 0,
        "matched_raw_edges": 18441,
    }


def test_routing_costs_and_geometry_are_valid() -> None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT COUNT(*) FILTER (WHERE source = target) AS self_loops,
                       COUNT(*) FILTER (
                         WHERE geometry IS NULL OR ST_IsEmpty(geometry)
                            OR NOT ST_IsValid(geometry) OR ST_SRID(geometry) <> 4326
                            OR length_m <= 0 OR speed_kph <= 0 OR travel_time_s <= 0
                            OR cost <= 0 OR abs(cost - travel_time_s) > 1e-9
                       ) AS invalid
                FROM routing_edges
                """
            )
        ).mappings().one()
    assert row["invalid"] == 0
    assert row["self_loops"] == 39


def test_directed_edge_reverse_cost_convention() -> None:
    with engine.connect() as connection:
        values = connection.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (WHERE oneway) AS oneway_edges,
                  COUNT(*) FILTER (WHERE NOT oneway) AS bidirectional_edges,
                  COUNT(*) FILTER (WHERE reverse_cost >= 0) AS invented_reverse_costs
                FROM routing_edges
                """
            )
        ).mappings().one()
    assert values["oneway_edges"] > 0
    assert values["bidirectional_edges"] > 0
    assert values["invented_reverse_costs"] == 0


def test_non_oneway_osmnx_edge_has_explicit_reverse_edge() -> None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT e.id, e.source, e.target, r.id AS reverse_id
                FROM routing_edges e
                JOIN routing_edges r ON r.source = e.target AND r.target = e.source
                WHERE NOT e.oneway
                ORDER BY e.id
                LIMIT 1
                """
            )
        ).mappings().one()
    assert row["reverse_id"] != row["id"]


def test_osm_and_default_speed_sources_are_both_present() -> None:
    with engine.connect() as connection:
        counts = dict(
            connection.execute(
                text("SELECT speed_source, COUNT(*) FROM routing_edges GROUP BY speed_source")
            ).all()
        )
    assert counts["osm"] == 430
    assert counts["default"] == 18011


def test_multiple_osm_edges_with_same_uv_are_preserved() -> None:
    with engine.connect() as connection:
        raw = connection.execute(
            text(
                """
                SELECT u, v, COUNT(*) AS count, COUNT(DISTINCT edge_key) AS keys
                FROM road_edges GROUP BY u, v
                HAVING COUNT(*) > 1 AND COUNT(DISTINCT edge_key) > 1
                ORDER BY count DESC, u, v LIMIT 1
                """
            )
        ).mappings().one()
        routing_count = connection.scalar(
            text(
                "SELECT COUNT(*) FROM routing_edges WHERE source = :u AND target = :v"
            ),
            {"u": raw["u"], "v": raw["v"]},
        )
    assert raw["count"] >= 2
    assert raw["keys"] == raw["count"]
    assert routing_count == raw["count"]


def test_routing_indexes_exist() -> None:
    with engine.connect() as connection:
        indexes = dict(
            connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'routing_edges'"
                )
            ).all()
        )
    assert "using gist" in indexes["idx_routing_edges_geometry"].lower()
    assert "ix_routing_edges_source" in indexes
    assert "ix_routing_edges_target" in indexes


def test_edge_endpoints_match_source_and_target_nodes() -> None:
    with engine.connect() as connection:
        maximum = connection.execute(
            text(
                """
                WITH sample AS (
                    SELECT * FROM routing_edges WHERE id % 181 = 0 LIMIT 100
                )
                SELECT MAX(ST_Distance(ST_StartPoint(s.geometry)::geography, a.geometry::geography)),
                       MAX(ST_Distance(ST_EndPoint(s.geometry)::geography, b.geometry::geography))
                FROM sample s
                JOIN road_nodes a ON a.osm_node_id = s.source
                JOIN road_nodes b ON b.osm_node_id = s.target
                """
            )
        ).one()
    assert maximum[0] < 0.01
    assert maximum[1] < 0.01


def test_network_edges_require_valid_small_bbox() -> None:
    assert client.get("/api/v1/network/edges").status_code == 422
    assert client.get(
        "/api/v1/network/edges", params={"bbox": "103.6,35.98,104.08,36.16"}
    ).status_code == 422
    assert client.get(
        "/api/v1/network/edges", params={"bbox": "bad"}
    ).status_code == 422


def test_network_edges_return_real_geojson() -> None:
    response = client.get(
        "/api/v1/network/edges", params={"bbox": CENTRAL_BBOX, "limit": 20}
    )
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == 20
    assert all(feature["geometry"]["type"] == "LineString" for feature in features)
    assert all(feature["properties"]["source"] != feature["properties"]["target"] for feature in features)
    assert all(feature["properties"]["source_dataset"] == "OpenStreetMap / OSMnx" for feature in features)


def test_network_edges_support_highway_filter_and_limit() -> None:
    response = client.get(
        "/api/v1/network/edges",
        params={"bbox": CENTRAL_BBOX, "highway": "primary", "limit": 3},
    )
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == 3
    assert all("primary" in item["properties"]["highway"].split("; ") for item in features)


def test_network_edges_can_return_empty_collection() -> None:
    response = client.get(
        "/api/v1/network/edges",
        params={"bbox": "103.00,35.00,103.01,35.01", "limit": 10},
    )
    assert response.status_code == 200
    assert response.json() == {"type": "FeatureCollection", "features": []}


def test_network_stats_report_real_database_metrics() -> None:
    response = client.get("/api/v1/network/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["nodes"] == 8286
    assert body["edges"] == 18441
    assert body["oneway_edges"] + body["bidirectional_edges"] == body["edges"]
    assert body["length_km"] > 0
    assert body["avg_speed_kph"] > 0
    assert body["weak_components"] > 0
    assert 0.9 < body["largest_component_ratio"] <= 1
    assert sum(body["highway_counts"].values()) == body["edges"]
    assert sum(body["speed_source_counts"].values()) == body["edges"]
