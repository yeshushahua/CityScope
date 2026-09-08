import json
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
from geoalchemy2 import Geometry
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB

from scripts.osm.config import PROJECT_ROOT

BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.models import (  # noqa: E402,F401
    Building,
    Poi,
    PoiRoutingAccess,
    RoadEdge,
    RoadNode,
    RoutingEdge,
)
from scripts.osm.build_poi_routing_access import rebuild_poi_routing_access

TABLE_ORDER = (
    "road_nodes",
    "road_edges",
    "routing_edges",
    "buildings",
    "pois",
    "poi_routing_access",
)


def _existing_osm_tables() -> list[str]:
    inspector = inspect(engine)
    return [name for name in TABLE_ORDER if inspector.has_table(name)]


def import_all(processed: dict[str, object], *, replace: bool) -> dict[str, int]:
    existing = _existing_osm_tables()
    if existing and not replace:
        names = ", ".join(existing)
        raise RuntimeError(f"OSM tables already exist ({names}); rerun with --replace")

    frames: dict[str, gpd.GeoDataFrame] = processed["frames"]
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting"))
        if replace:
            Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)

        frames["road_nodes"].to_postgis(
            "road_nodes",
            connection,
            if_exists="append",
            index=False,
            chunksize=5000,
            dtype={"geometry": Geometry("POINT", srid=4326)},
        )
        frames["road_edges"].to_postgis(
            "road_edges",
            connection,
            if_exists="append",
            index=False,
            chunksize=3000,
            dtype={"geometry": Geometry("LINESTRING", srid=4326)},
        )
        frames["routing_edges"].to_postgis(
            "routing_edges",
            connection,
            if_exists="append",
            index=False,
            chunksize=3000,
            dtype={"geometry": Geometry("LINESTRING", srid=4326)},
        )
        frames["buildings"].to_postgis(
            "buildings",
            connection,
            if_exists="append",
            index=False,
            chunksize=2000,
            dtype={"geometry": Geometry("MULTIPOLYGON", srid=4326)},
        )
        poi_frame = frames["pois"].copy()
        poi_frame["source_tags"] = poi_frame["source_tags"].map(
            lambda value: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )
        poi_frame.to_postgis(
            "pois",
            connection,
            if_exists="append",
            index=False,
            chunksize=3000,
            dtype={"source_tags": JSONB, "geometry": Geometry("POINT", srid=4326)},
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_pois_geography
                ON pois USING GIST ((geometry::geography))
                """
            )
        )
        rebuild_poi_routing_access(connection)
        for table in TABLE_ORDER:
            connection.execute(text(f"ANALYZE {table}"))

    with engine.connect() as connection:
        counts = {
            table: int(connection.scalar(text(f"SELECT COUNT(*) FROM {table}")) or 0)
            for table in TABLE_ORDER
        }
    for table, count in counts.items():
        print(f"{table}: imported {count:,} rows")
    return counts
