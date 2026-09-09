"""Download, normalize, and import the real OSMnx walking graph for CityScope."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
from geoalchemy2 import Geometry
from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, MultiLineString
from shapely.ops import linemerge
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import engine  # noqa: E402
from scripts.osm.build_poi_walk_access import (  # noqa: E402
    mapping_fingerprint,
    rebuild_poi_walk_access,
)
from scripts.osm.config import DEMO_BBOX, INTERIM_DIR, RAW_DIR, SOURCE_CRS  # noqa: E402
from scripts.osm.download_osm import configure_osmnx  # noqa: E402

WALK_SPEED_KPH = 4.8
RAW_GRAPH = RAW_DIR / "lanzhou_walk.graphml"
NODES_GPKG = INTERIM_DIR / "pedestrian_nodes.gpkg"
EDGES_GPKG = INTERIM_DIR / "pedestrian_edges.gpkg"
MIGRATION = PROJECT_ROOT / "database" / "migrations" / "006_phase8_pedestrian_network.sql"


def scalar(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)
    return str(value)


def line_geometry(value: object) -> LineString | None:
    if value is None or not hasattr(value, "is_empty") or value.is_empty:
        return None
    fixed = make_valid(value)
    if isinstance(fixed, LineString):
        return fixed
    if isinstance(fixed, MultiLineString):
        merged = linemerge(fixed)
        return merged if isinstance(merged, LineString) else max(merged.geoms, key=lambda g: g.length)
    if isinstance(fixed, GeometryCollection):
        lines = [g for g in fixed.geoms if isinstance(g, LineString)]
        return max(lines, key=lambda g: g.length) if lines else None
    return None


def load_or_download_graph() -> ox.graph.MultiDiGraph:
    configure_osmnx()
    if RAW_GRAPH.exists():
        print(f"Walking graph: using cache {RAW_GRAPH}")
        return ox.load_graphml(RAW_GRAPH)
    print(f"Walking graph: downloading OSMnx network_type=walk for bbox={DEMO_BBOX}")
    graph = ox.graph_from_bbox(
        DEMO_BBOX,
        network_type="walk",
        simplify=True,
        retain_all=True,
        truncate_by_edge=True,
    )
    ox.save_graphml(graph, RAW_GRAPH)
    print(f"Walking graph: cached {len(graph.nodes):,} nodes / {len(graph.edges):,} edges")
    return graph


def normalize_graph(graph) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    raw_nodes, raw_edges = ox.graph_to_gdfs(
        graph, nodes=True, edges=True, fill_edge_geometry=True
    )
    nodes = raw_nodes.reset_index().rename(columns={"osmid": "osm_node_id"})
    nodes = nodes[["osm_node_id", "geometry"]].copy()
    nodes = nodes[nodes.geometry.notna() & ~nodes.geometry.is_empty]
    nodes["osm_node_id"] = nodes["osm_node_id"].astype("int64")
    nodes = nodes.drop_duplicates("osm_node_id").sort_values("osm_node_id")
    nodes = gpd.GeoDataFrame(nodes, geometry="geometry", crs=SOURCE_CRS)
    node_geometry = nodes.set_index("osm_node_id").geometry

    edges = raw_edges.reset_index().rename(columns={"key": "edge_key", "osmid": "osm_id"})
    edges["geometry"] = edges.geometry.map(line_geometry)
    edges = edges[edges.geometry.notna()].copy()
    edges["osm_id"] = edges.get("osm_id", pd.Series(index=edges.index, dtype=object)).map(scalar).fillna("unknown")
    edges["highway"] = edges.get("highway", pd.Series(index=edges.index, dtype=object)).map(scalar)
    edges["name"] = edges.get("name", pd.Series(index=edges.index, dtype=object)).map(scalar)
    edges["length_m"] = pd.to_numeric(edges["length"], errors="coerce")
    edges = edges.dropna(subset=["length_m"])
    edges = edges[edges["length_m"] > 0].copy()
    edges["u"] = edges["u"].astype("int64")
    edges["v"] = edges["v"].astype("int64")
    edges = edges[edges["u"].isin(node_geometry.index) & edges["v"].isin(node_geometry.index)]

    def orient(row):
        geometry = row.geometry
        source = node_geometry.loc[int(row.u)]
        start = LineString(geometry.coords).coords[0]
        end = LineString(geometry.coords).coords[-1]
        start_error = (start[0] - source.x) ** 2 + (start[1] - source.y) ** 2
        end_error = (end[0] - source.x) ** 2 + (end[1] - source.y) ** 2
        return LineString(list(geometry.coords)[::-1]) if end_error < start_error else geometry

    edges["geometry"] = edges.apply(orient, axis=1)
    edges = edges.drop_duplicates(["u", "v", "edge_key"])
    edges = edges.sort_values(["u", "v", "edge_key"], kind="stable").reset_index(drop=True)
    edges.insert(0, "id", range(1, len(edges) + 1))
    edges["source"] = edges["u"]
    edges["target"] = edges["v"]
    edges["walk_speed_kph"] = WALK_SPEED_KPH
    edges["travel_time_s"] = edges["length_m"] / (WALK_SPEED_KPH / 3.6)
    edges["cost"] = edges["travel_time_s"]
    edges["reverse_cost"] = -1.0
    edges = edges[
        [
            "id", "osm_id", "source", "target", "u", "v", "edge_key",
            "highway", "name", "length_m", "walk_speed_kph", "travel_time_s",
            "cost", "reverse_cost", "geometry",
        ]
    ]
    edges = gpd.GeoDataFrame(edges, geometry="geometry", crs=SOURCE_CRS)
    return nodes.reset_index(drop=True), edges


def write_cache(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame) -> None:
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    for path, layer, frame in (
        (NODES_GPKG, "pedestrian_nodes", nodes),
        (EDGES_GPKG, "pedestrian_edges", edges),
    ):
        path.unlink(missing_ok=True)
        frame.to_file(path, layer=layer, driver="GPKG", engine="pyogrio")


def apply_migration(connection) -> None:
    connection.exec_driver_sql(MIGRATION.read_text(encoding="utf-8"))


def import_graph(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame, replace: bool) -> dict:
    with engine.begin() as connection:
        apply_migration(connection)
        existing = int(connection.scalar(text("SELECT COUNT(*) FROM pedestrian_nodes")) or 0)
        if existing and not replace:
            raise RuntimeError("Pedestrian tables already contain data; rerun with --replace")
        if replace:
            connection.execute(text("TRUNCATE poi_walk_access, pedestrian_edges, pedestrian_nodes"))
        nodes.to_postgis(
            "pedestrian_nodes", connection, if_exists="append", index=False,
            chunksize=5000, dtype={"geometry": Geometry("POINT", srid=4326)},
        )
        edges.to_postgis(
            "pedestrian_edges", connection, if_exists="append", index=False,
            chunksize=3000, dtype={"geometry": Geometry("LINESTRING", srid=4326)},
        )
        mapped = rebuild_poi_walk_access(connection)
        for table in ("pedestrian_nodes", "pedestrian_edges", "poi_walk_access"):
            connection.execute(text(f"ANALYZE {table}"))
        fingerprint = mapping_fingerprint(connection)
    return {
        "pedestrian_nodes": len(nodes),
        "pedestrian_edges": len(edges),
        "poi_walk_access": mapped,
        "poi_walk_access_sha256": fingerprint,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="replace pedestrian graph rows transactionally")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph = load_or_download_graph()
    nodes, edges = normalize_graph(graph)
    write_cache(nodes, edges)
    counts = import_graph(nodes, edges, args.replace)
    metadata = {
        "source": "OpenStreetMap contributors",
        "retrieved_at": datetime.fromtimestamp(RAW_GRAPH.stat().st_mtime, timezone.utc).isoformat(),
        "bbox": DEMO_BBOX,
        "network_type": "walk",
        "walk_speed_kph": WALK_SPEED_KPH,
        **counts,
    }
    target = INTERIM_DIR / "pedestrian_metadata.json"
    target.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
