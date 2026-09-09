"""Record real Phase 9 building-height provenance and a reproducible sample."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import engine  # noqa: E402

OUTPUT = PROJECT_ROOT / "docs" / "phase-9-frontend-benchmark.json"


def main() -> None:
    with engine.connect() as connection:
        source_rows = connection.execute(
            text(
                """
                SELECT height_source, COUNT(*)::integer AS count,
                       MIN(display_height_m) AS min_height_m,
                       AVG(display_height_m) AS average_height_m,
                       MAX(display_height_m) AS max_height_m
                FROM buildings
                GROUP BY height_source ORDER BY height_source
                """
            )
        ).mappings().all()
        samples = connection.execute(
            text(
                """
                WITH ranked AS (
                  SELECT id, osm_type, osm_id, name, building_type, area_m2,
                         osm_height_m, building_levels, display_height_m, height_source,
                         ST_X(ST_PointOnSurface(geometry)) AS lon,
                         ST_Y(ST_PointOnSurface(geometry)) AS lat,
                         ROW_NUMBER() OVER (PARTITION BY height_source ORDER BY id) AS rank
                  FROM buildings
                )
                SELECT * FROM ranked
                WHERE (height_source = 'osm_height' AND rank <= 10)
                   OR (height_source = 'levels_estimate' AND rank <= 10)
                   OR (height_source = 'unknown' AND rank <= 3)
                ORDER BY height_source, rank
                """
            )
        ).mappings().all()
        consistency = connection.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (WHERE height_source='osm_height'
                    AND (display_height_m IS DISTINCT FROM osm_height_m OR osm_height_m IS NULL)) AS bad_osm,
                  COUNT(*) FILTER (WHERE height_source='levels_estimate'
                    AND (display_height_m IS DISTINCT FROM building_levels*3 OR building_levels IS NULL OR osm_height_m IS NOT NULL)) AS bad_levels,
                  COUNT(*) FILTER (WHERE height_source='unknown' AND display_height_m IS NOT NULL) AS bad_unknown
                FROM buildings
                """
            )
        ).mappings().one()

    payload = {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "height_sources": [dict(row) for row in source_rows],
        "consistency": dict(consistency),
        "sample_size": len(samples),
        "sample": [dict(row) for row in samples],
        "bundle_phase8_baseline": {
            "modules_transformed": 108,
            "main_js_kb": 1281.03,
            "main_js_gzip_kb": 354.98,
            "css_kb": 104.58,
            "worker_kb": 487.15,
        },
        "bundle_phase9": {
            "modules_transformed": 115,
            "main_js_kb": 85.86,
            "main_js_gzip_kb": 29.86,
            "city_map_js_kb": 36.57,
            "city_map_js_gzip_kb": 9.64,
            "react_vendor_js_kb": 186.49,
            "react_vendor_js_gzip_kb": 58.53,
            "maplibre_js_kb": 981.07,
            "maplibre_js_gzip_kb": 260.51,
            "maplibre_css_kb": 83.04,
            "maplibre_css_gzip_kb": 10.52,
            "app_css_kb": 30.52,
            "app_css_gzip_kb": 6.19,
            "worker_kb": 487.15,
            "warning": "MapLibre vendor chunk exceeds Vite's 500 kB warning threshold.",
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
