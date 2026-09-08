import hashlib
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import engine  # noqa: E402

FACILITY_MAX_SNAP_M = 500


def rebuild_poi_routing_access(connection: Connection) -> int:
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_road_nodes_geography
            ON road_nodes USING GIST ((geometry::geography))
            """
        )
    )
    connection.execute(text("TRUNCATE TABLE poi_routing_access"))
    result = connection.execute(
        text(
            """
            INSERT INTO poi_routing_access (poi_id, node_id, snap_distance_m)
            SELECT p.id, nearest.osm_node_id, nearest.snap_distance_m
            FROM pois AS p
            JOIN LATERAL (
                SELECT n.osm_node_id,
                       ST_Distance(n.geometry::geography, p.geometry::geography)
                           AS snap_distance_m
                FROM road_nodes AS n
                WHERE ST_DWithin(
                    n.geometry::geography,
                    p.geometry::geography,
                    :max_snap_m
                )
                ORDER BY n.geometry::geography <-> p.geometry::geography,
                         n.osm_node_id
                LIMIT 1
            ) AS nearest ON true
            WHERE p.category IN ('healthcare', 'emergency')
            ORDER BY p.id
            """
        ),
        {"max_snap_m": FACILITY_MAX_SNAP_M},
    )
    return int(result.rowcount or 0)


def main() -> None:
    with engine.begin() as connection:
        count = rebuild_poi_routing_access(connection)
        connection.execute(text("ANALYZE poi_routing_access"))
        mapping = connection.scalar(text("""
            SELECT string_agg(poi_id::text || ':' || node_id::text || ':' ||
                              round(snap_distance_m::numeric,6)::text, ',' ORDER BY poi_id)
            FROM poi_routing_access
        """)) or ""
    fingerprint = hashlib.sha256(mapping.encode()).hexdigest()
    print(f"poi_routing_access: mapped {count:,} facilities; sha256={fingerprint}")


if __name__ == "__main__":
    main()
