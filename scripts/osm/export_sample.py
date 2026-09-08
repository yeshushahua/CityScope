import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from scripts.osm.config import PROJECT_ROOT, SAMPLE_DIR

BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import engine  # noqa: E402


def _feature(row: dict[str, Any], geometry: dict[str, Any] | str) -> dict[str, Any]:
    geometry_value = json.loads(geometry) if isinstance(geometry, str) else geometry
    properties = {key: value for key, value in row.items() if key != "geometry"}
    return {"type": "Feature", "geometry": geometry_value, "properties": properties}


def export_sample() -> Path:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        poi_rows = connection.execute(
            text(
                """
                SELECT id, osm_type, osm_id, name, category, subcategory,
                       'OpenStreetMap' AS source,
                       ST_AsGeoJSON(geometry)::json AS geometry
                FROM pois ORDER BY id LIMIT 10
                """
            )
        ).mappings()
        building_rows = connection.execute(
            text(
                """
                SELECT id, osm_type, osm_id, name, building_type, area_m2,
                       'OpenStreetMap' AS source,
                       ST_AsGeoJSON(geometry)::json AS geometry
                FROM buildings ORDER BY id LIMIT 5
                """
            )
        ).mappings()
        features = [
            _feature(dict(row), row["geometry"])
            for row in [*poi_rows, *building_rows]
        ]
    collection = {
        "type": "FeatureCollection",
        "name": "CityScope Lanzhou OSM sample",
        "source": "© OpenStreetMap contributors",
        "features": features,
    }
    path = SAMPLE_DIR / "lanzhou_osm_sample.geojson"
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Sample: exported {len(features)} real OSM features to {path}")
    return path
