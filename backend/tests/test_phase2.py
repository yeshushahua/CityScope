from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app

client = TestClient(app)


def test_database_and_postgis_are_available() -> None:
    response = client.get("/api/v1/health/database")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "PostgreSQL",
        "postgis": True,
        "detail": None,
    }


def test_pois_return_real_geojson_and_filter_by_category() -> None:
    response = client.get(
        "/api/v1/layers/pois",
        params={"bbox": "103.60,35.98,104.08,36.16", "category": "healthcare", "limit": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"]
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert feature["properties"]["category"] == "healthcare"
        assert feature["properties"]["source"] == "OpenStreetMap"
        longitude, latitude = feature["geometry"]["coordinates"]
        assert 103.60 <= longitude <= 104.08
        assert 35.98 <= latitude <= 36.16


def test_poi_layer_supports_subcategory_and_limit() -> None:
    response = client.get(
        "/api/v1/layers/pois",
        params={"subcategory": "hospital", "limit": 3},
    )
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == 3
    assert all(feature["properties"]["subcategory"] == "hospital" for feature in features)


def test_buildings_require_a_small_bbox_and_return_geojson() -> None:
    missing = client.get("/api/v1/layers/buildings")
    assert missing.status_code == 422
    too_large = client.get(
        "/api/v1/layers/buildings", params={"bbox": "103.60,35.98,104.08,36.16"}
    )
    assert too_large.status_code == 422

    response = client.get(
        "/api/v1/layers/buildings",
        params={"bbox": "103.82,36.04,103.84,36.06", "limit": 25},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"]
    assert all(feature["properties"]["area_m2"] > 0 for feature in body["features"])
    assert all(feature["properties"]["source"] == "OpenStreetMap" for feature in body["features"])


def test_phase2_geometry_columns_are_valid_and_spatially_indexed() -> None:
    tables = ("road_nodes", "road_edges", "buildings", "pois")
    with engine.connect() as connection:
        metadata = connection.execute(
            text(
                """
                SELECT f_table_name, type, srid
                FROM geometry_columns
                WHERE f_table_name = ANY(:tables)
                ORDER BY f_table_name
                """
            ),
            {"tables": list(tables)},
        ).all()
        assert metadata == [
            ("buildings", "MULTIPOLYGON", 4326),
            ("pois", "POINT", 4326),
            ("road_edges", "LINESTRING", 4326),
            ("road_nodes", "POINT", 4326),
        ]

        for table in tables:
            invalid_count = connection.scalar(
                text(f"SELECT COUNT(*) FROM {table} WHERE NOT ST_IsValid(geometry)")
            )
            assert invalid_count == 0
            spatial_indexes = connection.scalar(
                text(
                    """
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE tablename = :table AND indexdef ILIKE '%gist%'
                    """
                ),
                {"table": table},
            )
            assert spatial_indexes and spatial_indexes > 0
