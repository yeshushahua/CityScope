import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.geojson import GeoJSONFeature
from app.schemas.spatial import (
    BuildingSummary,
    NearbyMeta,
    NearbyPoiCollection,
    PoiSummary,
    QueryCenter,
    SpatialSummary,
)


def _geometry(value: dict[str, Any] | str) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


def nearby_pois(
    db: Session,
    *,
    lon: float,
    lat: float,
    radius_m: int,
    category: str | None,
    subcategory: str | None,
    limit: int,
) -> NearbyPoiCollection:
    filters = [
        "ST_DWithin(p.geometry::geography, q.center, :radius_m)",
    ]
    params: dict[str, Any] = {
        "lon": lon,
        "lat": lat,
        "radius_m": radius_m,
        "limit": limit,
    }
    if category:
        filters.append("p.category = :category")
        params["category"] = category
    if subcategory:
        filters.append("p.subcategory = :subcategory")
        params["subcategory"] = subcategory

    rows = db.execute(
        text(
            f"""
            WITH q AS (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS center
            )
            SELECT p.id, p.osm_type, p.osm_id, p.name, p.category, p.subcategory,
                   ST_AsGeoJSON(p.geometry)::json AS geometry,
                   ST_Distance(p.geometry::geography, q.center) AS distance_m
            FROM pois AS p
            CROSS JOIN q
            WHERE {' AND '.join(filters)}
            ORDER BY distance_m, p.id
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    features = [
        GeoJSONFeature(
            geometry=_geometry(row["geometry"]),
            properties={
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "subcategory": row["subcategory"],
                "osm_type": row["osm_type"],
                "osm_id": row["osm_id"],
                "distance_m": round(float(row["distance_m"]), 1),
                "source": "OpenStreetMap",
            },
        )
        for row in rows
    ]
    return NearbyPoiCollection(
        features=features,
        meta=NearbyMeta(center=(lon, lat), radius_m=radius_m, count=len(features)),
    )


def spatial_summary(
    db: Session,
    *,
    lon: float,
    lat: float,
    radius_m: int,
) -> SpatialSummary:
    params = {"lon": lon, "lat": lat, "radius_m": radius_m}
    poi_rows = db.execute(
        text(
            """
            WITH q AS (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS center
            )
            SELECT p.category, COUNT(*)::integer AS count
            FROM pois AS p
            CROSS JOIN q
            WHERE ST_DWithin(p.geometry::geography, q.center, :radius_m)
            GROUP BY GROUPING SETS ((p.category), ())
            ORDER BY p.category NULLS FIRST
            """
        ),
        params,
    ).mappings()
    total = 0
    by_category: dict[str, int] = {}
    for row in poi_rows:
        if row["category"] is None:
            total = int(row["count"])
        else:
            by_category[str(row["category"])] = int(row["count"])

    building_row = db.execute(
        text(
            """
            WITH query_area AS (
                SELECT ST_Buffer(
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius_m
                )::geometry AS geometry
            )
            SELECT COUNT(b.id)::integer AS count,
                   COALESCE(
                       SUM(
                           ST_Area(
                               ST_Transform(
                                   ST_Intersection(b.geometry, q.geometry),
                                   32648
                               )
                           )
                       ),
                       0
                   ) AS footprint_area_m2
            FROM buildings AS b
            CROSS JOIN query_area AS q
            WHERE b.geometry && q.geometry
              AND ST_Intersects(b.geometry, q.geometry)
            """
        ),
        params,
    ).mappings().one()
    return SpatialSummary(
        center=QueryCenter(lon=lon, lat=lat),
        radius_m=radius_m,
        pois=PoiSummary(total=total, by_category=by_category),
        buildings=BuildingSummary(
            count=int(building_row["count"]),
            footprint_area_m2=round(float(building_row["footprint_area_m2"]), 1),
        ),
    )
