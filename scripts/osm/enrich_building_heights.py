"""Recover real OSM building heights from the existing OSMnx response cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from scripts.osm.config import RAW_DIR  # noqa: E402

MIGRATION = PROJECT_ROOT / "database" / "migrations" / "007_phase9_building_heights.sql"
NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:m|meter|meters)?\s*$", re.I)
FEET_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:ft|feet|')\s*$", re.I)


def parse_positive_number(value: Any, *, maximum: float) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    match = NUMBER_RE.fullmatch(raw)
    multiplier = 1.0
    if not match:
        match = FEET_RE.fullmatch(raw)
        multiplier = 0.3048
    if not match:
        return None
    parsed = float(match.group(1)) * multiplier
    return round(parsed, 3) if 0 < parsed <= maximum else None


def cached_height_records() -> list[dict[str, Any]]:
    cache_dir = RAW_DIR / "osmnx-cache"
    paths = sorted(cache_dir.glob("*.json"))
    if not paths:
        raise RuntimeError(f"OSMnx response cache is missing: {cache_dir}")

    records: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            if not tags.get("building"):
                continue
            osm_height = parse_positive_number(tags.get("height"), maximum=1000)
            levels = parse_positive_number(tags.get("building:levels"), maximum=200)
            if osm_height is None and levels is None:
                continue
            height_source = "osm_height" if osm_height is not None else "levels_estimate"
            display_height = osm_height if osm_height is not None else round(levels * 3.0, 3)
            key = (str(element.get("type")), str(element.get("id")))
            records[key] = {
                "osm_type": key[0],
                "osm_id": key[1],
                "osm_height_m": osm_height,
                "building_levels": levels,
                "display_height_m": display_height,
                "height_source": height_source,
            }
    return [records[key] for key in sorted(records)]


def apply_migration(connection) -> None:
    for statement in MIGRATION.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            connection.execute(text(statement))


def enrich_buildings() -> dict[str, Any]:
    records = cached_height_records()
    with engine.begin() as connection:
        apply_migration(connection)
        connection.execute(
            text(
                """
                UPDATE buildings SET
                    osm_height_m = NULL,
                    building_levels = NULL,
                    display_height_m = NULL,
                    height_source = 'unknown'
                """
            )
        )
        if records:
            connection.execute(
                text(
                    """
                    UPDATE buildings AS b SET
                        osm_height_m = :osm_height_m,
                        building_levels = :building_levels,
                        display_height_m = :display_height_m,
                        height_source = :height_source
                    WHERE b.osm_type = :osm_type AND b.osm_id = :osm_id
                    """
                ),
                records,
            )
        connection.execute(text("ANALYZE buildings"))

    with engine.connect() as connection:
        counts = dict(
            connection.execute(
                text(
                    """
                    SELECT height_source, COUNT(*)::integer
                    FROM buildings GROUP BY height_source ORDER BY height_source
                    """
                )
            ).all()
        )
        rows = connection.execute(
            text(
                """
                SELECT id, osm_height_m, building_levels, display_height_m, height_source
                FROM buildings ORDER BY id
                """
            )
        ).all()
    digest = hashlib.sha256(
        "\n".join("|".join("" if value is None else str(value) for value in row) for row in rows).encode()
    ).hexdigest()
    return {
        "total": len(rows),
        "osm_height": counts.get("osm_height", 0),
        "levels_estimate": counts.get("levels_estimate", 0),
        "unknown": counts.get("unknown", 0),
        "sha256": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(enrich_buildings(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
