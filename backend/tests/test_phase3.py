import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app

client = TestClient(app)
CENTER = {"lon": 103.8343, "lat": 36.0611}


def test_nearby_pois_use_meter_radius_and_distance_order() -> None:
    response = client.get(
        "/api/v1/spatial/nearby-pois",
        params={**CENTER, "radius_m": 500, "limit": 200},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["center"] == [CENTER["lon"], CENTER["lat"]]
    assert body["meta"]["radius_m"] == 500
    assert body["meta"]["count"] == len(body["features"])
    distances = [feature["properties"]["distance_m"] for feature in body["features"]]
    assert distances
    assert distances == sorted(distances)
    assert all(0 <= distance <= 500 for distance in distances)


def test_nearby_pois_filter_category_subcategory_and_limit() -> None:
    category_response = client.get(
        "/api/v1/spatial/nearby-pois",
        params={**CENTER, "radius_m": 3000, "category": "healthcare", "limit": 5},
    )
    assert category_response.status_code == 200
    category_features = category_response.json()["features"]
    assert len(category_features) == 5
    assert all(item["properties"]["category"] == "healthcare" for item in category_features)

    subcategory_response = client.get(
        "/api/v1/spatial/nearby-pois",
        params={**CENTER, "radius_m": 3000, "subcategory": "hospital", "limit": 20},
    )
    assert subcategory_response.status_code == 200
    assert subcategory_response.json()["features"]
    assert all(
        item["properties"]["subcategory"] == "hospital"
        for item in subcategory_response.json()["features"]
    )


def test_nearby_pois_empty_result_is_not_an_error() -> None:
    response = client.get(
        "/api/v1/spatial/nearby-pois",
        params={"lon": 103, "lat": 35, "radius_m": 100},
    )
    assert response.status_code == 200
    assert response.json()["features"] == []
    assert response.json()["meta"]["count"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"lon": 102.9, "lat": 36, "radius_m": 1000},
        {"lon": 104, "lat": 37.1, "radius_m": 1000},
        {**CENTER, "radius_m": 0},
        {**CENTER, "radius_m": 10001},
        {**CENTER, "limit": 0},
        {**CENTER, "limit": 201},
        {**CENTER, "category": "unknown"},
        {**CENTER, "subcategory": "unknown"},
        {**CENTER, "category": "education", "subcategory": "hospital"},
    ],
)
def test_nearby_pois_reject_invalid_parameters(params: dict[str, object]) -> None:
    assert client.get("/api/v1/spatial/nearby-pois", params=params).status_code == 422


def test_summary_uses_database_grouping_and_intersection_area() -> None:
    response = client.get(
        "/api/v1/spatial/summary",
        params={**CENTER, "radius_m": 1000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["center"] == CENTER
    assert body["radius_m"] == 1000
    assert body["pois"]["total"] == sum(body["pois"]["by_category"].values())
    assert body["pois"]["total"] > 0
    assert body["buildings"]["count"] > 0
    assert 0 < body["buildings"]["footprint_area_m2"] < 3_141_593


def test_summary_empty_result_returns_zero_statistics() -> None:
    response = client.get(
        "/api/v1/spatial/summary",
        params={"lon": 103, "lat": 35, "radius_m": 100},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pois"] == {"total": 0, "by_category": {}}
    assert body["buildings"] == {"count": 0, "footprint_area_m2": 0.0}


def test_summary_rejects_invalid_location_and_radius() -> None:
    assert client.get(
        "/api/v1/spatial/summary", params={"lon": 102, "lat": 36, "radius_m": 1000}
    ).status_code == 422
    assert client.get(
        "/api/v1/spatial/summary", params={**CENTER, "radius_m": 10001}
    ).status_code == 422


def test_geography_expression_index_exists_in_real_postgis() -> None:
    with engine.connect() as connection:
        index_definition = connection.scalar(
            text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE tablename = 'pois' AND indexname = 'idx_pois_geography'
                """
            )
        )
    assert index_definition is not None
    assert "USING gist" in index_definition
    assert "(geometry)::geography" in index_definition
