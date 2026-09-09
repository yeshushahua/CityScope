from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app

client = TestClient(app)


def test_building_api_exposes_transparent_height_provenance() -> None:
    response = client.get(
        "/api/v1/layers/buildings",
        params={"bbox": "103.82,36.04,103.84,36.06", "limit": 5000},
    )
    assert response.status_code == 200
    features = response.json()["features"]
    assert features
    for feature in features:
        properties = feature["properties"]
        assert properties["height_source"] in {"osm_height", "levels_estimate", "unknown"}
        if properties["height_source"] == "osm_height":
            assert properties["osm_height_m"] > 0
            assert properties["display_height_m"] == properties["osm_height_m"]
        elif properties["height_source"] == "levels_estimate":
            assert properties["osm_height_m"] is None
            assert properties["building_levels"] > 0
            assert properties["display_height_m"] == properties["building_levels"] * 3
        else:
            assert properties["display_height_m"] is None


def test_real_building_height_sources_and_twenty_row_sample() -> None:
    with engine.connect() as connection:
        counts = dict(
            connection.execute(
                text("SELECT height_source, COUNT(*) FROM buildings GROUP BY height_source")
            ).all()
        )
        sample = connection.execute(
            text(
                """
                SELECT osm_height_m, building_levels, display_height_m, height_source
                FROM buildings
                WHERE height_source <> 'unknown'
                ORDER BY id LIMIT 20
                """
            )
        ).all()
    assert counts["osm_height"] > 0
    assert counts["levels_estimate"] > 0
    assert counts["unknown"] > 0
    assert len(sample) == 20
    for osm_height, levels, display_height, source in sample:
        assert display_height > 0
        if source == "osm_height":
            assert display_height == osm_height
        else:
            assert osm_height is None
            assert display_height == levels * 3
