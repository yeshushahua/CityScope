import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import linemerge

from scripts.osm.config import AREA_CRS, INTERIM_DIR, SOURCE_CRS, SOURCE_TAG_COLUMNS

DEFAULT_SPEED_KPH = {
    "motorway": 80.0,
    "trunk": 60.0,
    "primary": 50.0,
    "secondary": 40.0,
    "tertiary": 35.0,
    "residential": 30.0,
    "unclassified": 25.0,
    "living_street": 15.0,
    "service": 20.0,
    "motorway_link": 50.0,
    "trunk_link": 40.0,
    "primary_link": 35.0,
    "secondary_link": 30.0,
    "tertiary_link": 25.0,
    "busway": 30.0,
    "escape": 20.0,
    "road": 25.0,
}
FALLBACK_SPEED_KPH = 25.0


@dataclass(frozen=True)
class CleaningStats:
    downloaded: int
    valid: int
    removed: int


def _scalar(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)
    return str(value)


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"yes", "true", "1"}


def _parse_maxspeed(value: object) -> float | None:
    text_value = _scalar(value)
    if not text_value:
        return None
    values: list[float] = []
    for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(mph)?", text_value.lower()):
        speed = float(number) * (1.609344 if unit else 1.0)
        if 5 <= speed <= 120:
            values.append(speed)
    return min(values) if values else None


def _default_speed(highway: str | None) -> float:
    classes = [item.strip() for item in (highway or "").split(";") if item.strip()]
    speeds = [DEFAULT_SPEED_KPH[item] for item in classes if item in DEFAULT_SPEED_KPH]
    return min(speeds) if speeds else FALLBACK_SPEED_KPH


def build_routing_edges(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    routing = edges.rename(columns={"u": "source", "v": "target"}).copy()
    parsed_speeds = routing["maxspeed"].map(_parse_maxspeed)
    routing["speed_source"] = parsed_speeds.map(lambda value: "osm" if pd.notna(value) else "default")
    routing["speed_kph"] = [
        float(speed) if pd.notna(speed) else _default_speed(highway)
        for speed, highway in zip(parsed_speeds, routing["highway"], strict=True)
    ]
    routing["travel_time_s"] = routing["length_m"] / (routing["speed_kph"] / 3.6)
    routing["cost"] = routing["travel_time_s"]
    routing["reverse_cost"] = -1.0
    routing["road_edge_id"] = routing["id"]
    routing = routing[
        [
            "id", "road_edge_id", "source", "target", "osm_id", "edge_key", "name",
            "highway", "oneway", "maxspeed", "speed_kph", "speed_source", "length_m",
            "travel_time_s", "cost", "reverse_cost", "geometry",
        ]
    ]
    return gpd.GeoDataFrame(routing, geometry="geometry", crs=SOURCE_CRS)


def _line_geometry(geometry: object) -> LineString | None:
    if geometry is None or not hasattr(geometry, "is_empty") or geometry.is_empty:
        return None
    fixed = make_valid(geometry)
    if isinstance(fixed, LineString):
        return fixed
    if isinstance(fixed, MultiLineString):
        merged = linemerge(fixed)
        if isinstance(merged, LineString):
            return merged
        return max(merged.geoms, key=lambda item: item.length)
    if isinstance(fixed, GeometryCollection):
        lines = [item for item in fixed.geoms if isinstance(item, LineString)]
        return max(lines, key=lambda item: item.length) if lines else None
    return None


def _polygon_geometry(geometry: object) -> MultiPolygon | None:
    if geometry is None or not hasattr(geometry, "is_empty") or geometry.is_empty:
        return None
    fixed = make_valid(geometry)
    if isinstance(fixed, Polygon):
        return MultiPolygon([fixed])
    if isinstance(fixed, MultiPolygon):
        return fixed
    if isinstance(fixed, GeometryCollection):
        polygons: list[Polygon] = []
        for item in fixed.geoms:
            if isinstance(item, Polygon):
                polygons.append(item)
            elif isinstance(item, MultiPolygon):
                polygons.extend(item.geoms)
        return MultiPolygon(polygons) if polygons else None
    return None


def clean_roads(graph_path: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, CleaningStats]]:
    graph = ox.load_graphml(graph_path)
    raw_nodes, raw_edges = ox.graph_to_gdfs(graph, nodes=True, edges=True, fill_edge_geometry=True)

    nodes = raw_nodes.reset_index().rename(columns={"osmid": "osm_node_id"})
    nodes = nodes[["osm_node_id", "geometry"]].copy()
    nodes = nodes[nodes.geometry.notna() & ~nodes.geometry.is_empty]
    nodes["osm_node_id"] = nodes["osm_node_id"].astype("int64")
    nodes = nodes.drop_duplicates(subset=["osm_node_id"])
    nodes = gpd.GeoDataFrame(nodes, geometry="geometry", crs=SOURCE_CRS)

    edges = raw_edges.reset_index().rename(columns={"key": "edge_key", "osmid": "osm_id"})
    edges["geometry"] = edges.geometry.map(_line_geometry)
    edges = edges[edges.geometry.notna()].copy()
    edges["osm_id"] = edges["osm_id"].map(_scalar).fillna("unknown")
    edges["name"] = edges.get("name", pd.Series(index=edges.index, dtype=object)).map(_scalar)
    edges["highway"] = edges.get("highway", pd.Series(index=edges.index, dtype=object)).map(_scalar)
    edges["maxspeed"] = edges.get("maxspeed", pd.Series(index=edges.index, dtype=object)).map(_scalar)
    oneway = edges.get("oneway", pd.Series(False, index=edges.index))
    edges["oneway"] = oneway.map(_boolean)
    edges["length_m"] = pd.to_numeric(edges["length"], errors="coerce")
    edges = edges.dropna(subset=["length_m"])
    edges = edges[["u", "v", "edge_key", "osm_id", "name", "highway", "oneway", "maxspeed", "length_m", "geometry"]]
    edges = edges.drop_duplicates(subset=["u", "v", "edge_key"])
    edges = edges.sort_values(["u", "v", "edge_key"], kind="stable").reset_index(drop=True)
    edges.insert(0, "id", range(1, len(edges) + 1))
    edges = gpd.GeoDataFrame(edges, geometry="geometry", crs=SOURCE_CRS)

    stats = {
        "road_nodes": CleaningStats(len(raw_nodes), len(nodes), len(raw_nodes) - len(nodes)),
        "road_edges": CleaningStats(len(raw_edges), len(edges), len(raw_edges) - len(edges)),
    }
    return nodes, edges, stats


def clean_buildings(raw: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, CleaningStats]:
    buildings = raw.copy()
    buildings["geometry"] = buildings.geometry.map(_polygon_geometry)
    buildings = buildings[buildings.geometry.notna()].copy()
    buildings = buildings.drop_duplicates(subset=["osm_type", "osm_id"])
    name_zh = buildings.get("name:zh", pd.Series(index=buildings.index, dtype=object))
    name = buildings.get("name", pd.Series(index=buildings.index, dtype=object))
    buildings["name"] = name_zh.combine_first(name).map(_scalar)
    buildings["building_type"] = buildings.get(
        "building", pd.Series(index=buildings.index, dtype=object)
    ).map(_scalar)
    height = pd.to_numeric(
        buildings.get("height", pd.Series(index=buildings.index, dtype=object)),
        errors="coerce",
    )
    levels = pd.to_numeric(
        buildings.get("building:levels", pd.Series(index=buildings.index, dtype=object)),
        errors="coerce",
    )
    buildings["osm_height_m"] = height.where((height > 0) & (height <= 1000))
    buildings["building_levels"] = levels.where((levels > 0) & (levels <= 200))
    buildings["display_height_m"] = buildings["osm_height_m"].combine_first(
        buildings["building_levels"] * 3.0
    )
    buildings["height_source"] = "unknown"
    buildings.loc[buildings["building_levels"].notna(), "height_source"] = "levels_estimate"
    buildings.loc[buildings["osm_height_m"].notna(), "height_source"] = "osm_height"
    buildings = gpd.GeoDataFrame(buildings, geometry="geometry", crs=SOURCE_CRS)
    buildings["area_m2"] = buildings.to_crs(AREA_CRS).geometry.area.round(2)
    buildings = buildings[
        [
            "osm_type", "osm_id", "name", "building_type", "area_m2",
            "osm_height_m", "building_levels", "display_height_m", "height_source",
            "geometry",
        ]
    ]
    stats = CleaningStats(len(raw), len(buildings), len(raw) - len(buildings))
    return buildings, stats


def _tag(row: pd.Series, name: str) -> str | None:
    value = row.get(name)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value)


def _poi_category(row: pd.Series) -> tuple[str, str] | None:
    amenity = _tag(row, "amenity")
    if amenity in {"hospital", "clinic", "doctors"}:
        return "healthcare", amenity
    if amenity == "fire_station":
        return "emergency", amenity
    if amenity in {"school", "college", "university", "kindergarten"}:
        return "education", amenity
    if amenity == "police":
        return "public_safety", amenity
    if amenity == "marketplace":
        return "commercial", amenity
    if _tag(row, "leisure") == "park":
        return "recreation", "park"
    if _tag(row, "highway") == "bus_stop":
        return "transport", "bus_stop"
    railway = _tag(row, "railway")
    if railway in {"station", "subway_entrance"}:
        return "transport", railway
    public_transport = _tag(row, "public_transport")
    if public_transport:
        return "transport", public_transport
    shop = _tag(row, "shop")
    if shop in {"supermarket", "mall"}:
        return "commercial", shop
    return None


def _source_tags(row: pd.Series) -> dict[str, Any]:
    tags: dict[str, Any] = {}
    for column in SOURCE_TAG_COLUMNS:
        value = _tag(row, column)
        if value:
            tags[column] = value
    return tags


def clean_pois(raw: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, CleaningStats]:
    records: list[dict[str, Any]] = []
    for _, row in raw.iterrows():
        geometry = row.geometry
        category = _poi_category(row)
        if geometry is None or geometry.is_empty or category is None:
            continue
        fixed = make_valid(geometry)
        if fixed.is_empty:
            continue
        name = _tag(row, "name:zh") or _tag(row, "name")
        records.append(
            {
                "osm_type": str(row["osm_type"]),
                "osm_id": str(row["osm_id"]),
                "name": name,
                "category": category[0],
                "subcategory": category[1],
                "source_tags": _source_tags(row),
                "geometry": fixed if fixed.geom_type == "Point" else fixed.representative_point(),
            }
        )
    pois = gpd.GeoDataFrame(records, geometry="geometry", crs=SOURCE_CRS)
    pois = pois.drop_duplicates(subset=["osm_type", "osm_id"])
    stats = CleaningStats(len(raw), len(pois), len(raw) - len(pois))
    return pois, stats


def _write_frame(frame: gpd.GeoDataFrame, path: Path, layer: str) -> None:
    path.unlink(missing_ok=True)
    output = frame.copy()
    if "source_tags" in output.columns:
        output["source_tags"] = output["source_tags"].map(
            lambda value: json.dumps(value, ensure_ascii=False)
        )
    output.to_file(path, layer=layer, driver="GPKG", engine="pyogrio")


def preprocess_all(downloaded: dict[str, object]) -> dict[str, object]:
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    nodes, edges, road_stats = clean_roads(downloaded["graph_path"])
    routing_edges = build_routing_edges(edges)
    buildings, building_stats = clean_buildings(downloaded["buildings"])
    pois, poi_stats = clean_pois(downloaded["pois"])

    frames = {
        "road_nodes": nodes,
        "road_edges": edges,
        "routing_edges": routing_edges,
        "buildings": buildings,
        "pois": pois,
    }
    for name, frame in frames.items():
        _write_frame(frame, INTERIM_DIR / f"{name}.gpkg", name)

    stats = {**road_stats, "buildings": building_stats, "pois": poi_stats}
    stats_dict = {name: asdict(value) for name, value in stats.items()}
    (INTERIM_DIR / "cleaning_stats.json").write_text(
        json.dumps(stats_dict, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, values in stats_dict.items():
        print(
            f"{name}: downloaded={values['downloaded']:,}, "
            f"valid={values['valid']:,}, removed={values['removed']:,}"
        )
    return {"frames": frames, "stats": stats_dict}
