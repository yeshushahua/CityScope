import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import geopandas as gpd
import osmnx as ox
import pandas as pd

from scripts.osm.config import (
    DEMO_BBOX,
    GRID_COLUMNS,
    GRID_ROWS,
    MAX_DOWNLOAD_ATTEMPTS,
    OVERPASS_ENDPOINTS,
    OVERPASS_TIMEOUT_SECONDS,
    POI_TAGS,
    RAW_DIR,
    SOURCE_CRS,
    SOURCE_TAG_COLUMNS,
)

T = TypeVar("T")


def configure_osmnx() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = RAW_DIR / "osmnx-cache"
    ox.settings.requests_timeout = OVERPASS_TIMEOUT_SECONDS
    ox.settings.overpass_rate_limit = True
    ox.settings.log_console = True


def _with_retry(label: str, operation: Callable[[], T]) -> T:
    last_error: Exception | None = None
    for attempt in range(MAX_DOWNLOAD_ATTEMPTS):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        ox.settings.overpass_url = endpoint
        try:
            print(f"{label}: attempt {attempt + 1}/{MAX_DOWNLOAD_ATTEMPTS} via {endpoint}")
            return operation()
        except Exception as exc:  # OSMnx raises several network/parser exception types.
            last_error = exc
            print(f"{label}: {exc.__class__.__name__}: {exc}")
            if attempt + 1 < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{label} failed after {MAX_DOWNLOAD_ATTEMPTS} attempts") from last_error


def _tile_bboxes() -> list[tuple[float, float, float, float]]:
    west, south, east, north = DEMO_BBOX
    width = (east - west) / GRID_COLUMNS
    height = (north - south) / GRID_ROWS
    return [
        (
            west + column * width,
            south + row * height,
            west + (column + 1) * width,
            south + (row + 1) * height,
        )
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    ]


def _serialize_value(value: object) -> object:
    if isinstance(value, (list, tuple, dict, set)):
        return json.dumps(list(value) if isinstance(value, set) else value, ensure_ascii=False)
    return value


def _cache_frame(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    cached = frame.reset_index()
    rename_columns: dict[str, str] = {}
    if "element" in cached.columns:
        rename_columns["element"] = "osm_type"
    if "element_type" in cached.columns:
        rename_columns["element_type"] = "osm_type"
    if "id" in cached.columns:
        rename_columns["id"] = "osm_id"
    cached = cached.rename(columns=rename_columns)
    if "osm_type" not in cached.columns or "osm_id" not in cached.columns:
        raise ValueError("OSM feature result does not expose element type and id")
    keep = ["osm_type", "osm_id", *SOURCE_TAG_COLUMNS, "geometry"]
    cached = cached[[column for column in keep if column in cached.columns]].copy()
    cached["osm_type"] = cached["osm_type"].astype(str)
    cached["osm_id"] = cached["osm_id"].astype(str)
    for column in cached.columns:
        if column != "geometry":
            cached[column] = cached[column].map(_serialize_value)
    return gpd.GeoDataFrame(cached, geometry="geometry", crs=frame.crs or SOURCE_CRS)


def download_roads() -> Path:
    configure_osmnx()
    graph_path = RAW_DIR / "lanzhou_roads.graphml"
    if graph_path.exists():
        print(f"Roads: using cache {graph_path}")
        return graph_path
    graph = _with_retry(
        "Roads",
        lambda: ox.graph_from_bbox(
            DEMO_BBOX,
            network_type="drive",
            simplify=True,
            retain_all=True,
            truncate_by_edge=True,
        ),
    )
    ox.save_graphml(graph, graph_path)
    print(f"Roads: cached {len(graph.nodes):,} nodes / {len(graph.edges):,} edges")
    return graph_path


def download_feature_tiles(
    kind: str,
    tags: dict[str, bool | str | list[str]],
) -> list[Path]:
    configure_osmnx()
    paths: list[Path] = []
    for index, bbox in enumerate(_tile_bboxes()):
        path = RAW_DIR / f"lanzhou_{kind}_{index:02d}.gpkg"
        paths.append(path)
        if path.exists():
            print(f"{kind.title()} tile {index + 1}: using cache {path.name}")
            continue
        frame = _with_retry(
            f"{kind.title()} tile {index + 1}/{GRID_COLUMNS * GRID_ROWS}",
            lambda bbox=bbox: ox.features_from_bbox(bbox, tags),
        )
        cached = _cache_frame(frame)
        cached.to_file(path, layer=kind, driver="GPKG", engine="pyogrio")
        print(f"{kind.title()} tile {index + 1}: cached {len(cached):,} features")
    return paths


def load_feature_tiles(kind: str, paths: list[Path]) -> gpd.GeoDataFrame:
    frames = [gpd.read_file(path, layer=kind, engine="pyogrio") for path in paths]
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=SOURCE_CRS)
    combined = combined.drop_duplicates(subset=["osm_type", "osm_id"], keep="first")
    return combined


def download_all() -> dict[str, object]:
    graph_path = download_roads()
    building_paths = download_feature_tiles("buildings", {"building": True})
    poi_paths = download_feature_tiles("pois", POI_TAGS)
    cache_paths = [graph_path, *building_paths, *poi_paths]
    retrieved_at = datetime.fromtimestamp(
        max(path.stat().st_mtime for path in cache_paths), timezone.utc
    ).isoformat()
    metadata = {
        "source": "OpenStreetMap contributors",
        "retrieved_at": retrieved_at,
        "bbox": DEMO_BBOX,
        "crs": SOURCE_CRS,
        "road_cache": graph_path.name,
        "building_tiles": [path.name for path in building_paths],
        "poi_tiles": [path.name for path in poi_paths],
    }
    (RAW_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "graph_path": graph_path,
        "buildings": load_feature_tiles("buildings", building_paths),
        "pois": load_feature_tiles("pois", poi_paths),
        "metadata": metadata,
    }
