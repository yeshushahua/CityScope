import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.geojson import GeoJSONFeature, GeoJSONFeatureCollection

BBox = tuple[float, float, float, float]


def _geometry(value: dict[str, Any] | str) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


def query_pois(
    db: Session,
    *,
    bbox: BBox | None,
    category: str | None,
    subcategory: str | None,
    limit: int,
) -> GeoJSONFeatureCollection:
    filters = []
    params: dict[str, Any] = {"limit": limit}
    if bbox is not None:
        filters.append(
            "ST_Intersects(geometry, ST_MakeEnvelope(:west, :south, :east, :north, 4326))"
        )
        params.update(zip(("west", "south", "east", "north"), bbox, strict=True))
    if category:
        filters.append("category = :category")
        params["category"] = category
    if subcategory:
        filters.append("subcategory = :subcategory")
        params["subcategory"] = subcategory

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = db.execute(
        text(
            f"""
            SELECT id, osm_type, osm_id, name, category, subcategory,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM pois
            {where_clause}
            ORDER BY id
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return GeoJSONFeatureCollection(
        features=[
            GeoJSONFeature(
                geometry=_geometry(row["geometry"]),
                properties={
                    "id": row["id"],
                    "osm_type": row["osm_type"],
                    "osm_id": row["osm_id"],
                    "name": row["name"],
                    "category": row["category"],
                    "subcategory": row["subcategory"],
                    "source": "OpenStreetMap",
                },
            )
            for row in rows
        ]
    )


def query_buildings(
    db: Session,
    *,
    bbox: BBox,
    limit: int,
) -> GeoJSONFeatureCollection:
    params = dict(zip(("west", "south", "east", "north"), bbox, strict=True))
    params["limit"] = limit
    rows = db.execute(
        text(
            """
            SELECT id, osm_type, osm_id, name, building_type, area_m2,
                   osm_height_m, building_levels, display_height_m, height_source,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM buildings
            WHERE ST_Intersects(
                geometry,
                ST_MakeEnvelope(:west, :south, :east, :north, 4326)
            )
            ORDER BY id
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return GeoJSONFeatureCollection(
        features=[
            GeoJSONFeature(
                geometry=_geometry(row["geometry"]),
                properties={
                    "id": row["id"],
                    "osm_type": row["osm_type"],
                    "osm_id": row["osm_id"],
                    "name": row["name"],
                    "building_type": row["building_type"],
                    "area_m2": round(row["area_m2"], 2),
                    "osm_height_m": row["osm_height_m"],
                    "building_levels": row["building_levels"],
                    "display_height_m": row["display_height_m"],
                    "height_source": row["height_source"],
                    "source": "OpenStreetMap",
                },
            )
            for row in rows
        ]
    )
