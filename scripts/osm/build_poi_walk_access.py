"""Build deterministic POI access links to the independent pedestrian graph."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import engine  # noqa: E402

POI_WALK_MAX_SNAP_M = 300


def rebuild_poi_walk_access(connection: Connection) -> int:
    connection.execute(text("TRUNCATE TABLE poi_walk_access"))
    result = connection.execute(
        text(
            """
            INSERT INTO poi_walk_access (poi_id, node_id, snap_distance_m)
            SELECT p.id, nearest.osm_node_id, nearest.snap_distance_m
            FROM pois AS p
            JOIN LATERAL (
                SELECT n.osm_node_id,
                       ST_Distance(n.geometry::geography, p.geometry::geography)
                           AS snap_distance_m
                FROM pedestrian_nodes AS n
                WHERE ST_DWithin(
                    n.geometry::geography,
                    p.geometry::geography,
                    :max_snap_m
                )
                ORDER BY n.geometry::geography <-> p.geometry::geography,
                         n.osm_node_id
                LIMIT 1
            ) AS nearest ON true
            ORDER BY p.id
            """
        ),
        {"max_snap_m": POI_WALK_MAX_SNAP_M},
    )
    return int(result.rowcount or 0)


def mapping_fingerprint(connection: Connection) -> str:
    mapping = connection.scalar(
        text(
            """
            SELECT string_agg(
                poi_id::text || ':' || node_id::text || ':' ||
                round(snap_distance_m::numeric, 6)::text,
                ',' ORDER BY poi_id
            )
            FROM poi_walk_access
            """
        )
    ) or ""
    return hashlib.sha256(mapping.encode()).hexdigest()


def main() -> None:
    with engine.begin() as connection:
        count = rebuild_poi_walk_access(connection)
        connection.execute(text("ANALYZE poi_walk_access"))
        fingerprint = mapping_fingerprint(connection)
    print(f"poi_walk_access: mapped {count:,} POIs; sha256={fingerprint}")


if __name__ == "__main__":
    main()
