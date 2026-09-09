import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.living_circle import (
    LivingCircleBandCollection,
    LivingCircleBandFeature,
    LivingCircleBandProperties,
    LivingCircleCategorySummary,
    LivingCircleCoverage,
    LivingCircleDataQuality,
    LivingCircleResponse,
    LivingCircleSummary,
    PedestrianSnap,
    ReachablePoiCollection,
    ReachablePoiFeature,
    ReachablePoiProperties,
    WalkingModelMetadata,
)
from app.schemas.routing import RoutePoint

WALK_SPEED_KPH = 4.8
WALK_SPEED_MPS = WALK_SPEED_KPH / 3.6
PEDESTRIAN_EDGES_SQL = (
    "SELECT id, source, target, cost, reverse_cost FROM pedestrian_edges"
)
CORE_CATEGORIES = (
    "commercial",
    "healthcare",
    "education",
    "recreation",
    "transport",
)
CONCAVE_HULL_TARGET_PERCENT = 0.85
DEGENERATE_BUFFER_M = 20.0
NESTING_TOLERANCE_M = 0.1
DISPLAY_LIMIT_PER_CATEGORY = 30

LIVING_CIRCLE_SQL = """
WITH driving AS MATERIALIZED (
    SELECT node, agg_cost
    FROM pgr_drivingDistance(
        :edges_sql,
        CAST(:start_node AS bigint),
        GREATEST(0.0, 900.0 - CAST(:origin_connector_s AS double precision)),
        directed => true
    )
),
thresholds(minutes, threshold_s) AS (
    VALUES (5, 300), (10, 600), (15, 900)
),
node_sets AS (
    SELECT t.minutes,
           t.threshold_s,
           GREATEST(0.0, t.threshold_s - :origin_connector_s) AS network_budget_s,
           COUNT(d.node)::integer AS reachable_node_count,
           ST_Collect(ST_Transform(n.geometry, 32648)) AS points_utm
    FROM thresholds AS t
    LEFT JOIN driving AS d
      ON d.agg_cost + :origin_connector_s <= t.threshold_s
    LEFT JOIN pedestrian_nodes AS n ON n.osm_node_id = d.node
    GROUP BY t.minutes, t.threshold_s
),
raw_areas AS (
    SELECT minutes, threshold_s, network_budget_s, reachable_node_count,
           CASE
             WHEN reachable_node_count >= 3
              AND ST_Area(ST_ConvexHull(points_utm)) > 0
             THEN ST_Multi(ST_CollectionExtract(ST_MakeValid(
                    ST_ConcaveHull(points_utm, :hull_target_percent, false)
                  ), 3))
             ELSE ST_Multi(ST_Buffer(points_utm, :fallback_buffer_m))
           END AS geometry_utm
    FROM node_sets
),
area_5 AS (
    SELECT network_budget_s, reachable_node_count,
           ST_Multi(ST_CollectionExtract(ST_MakeValid(geometry_utm), 3)) AS geometry_utm
    FROM raw_areas WHERE threshold_s = 300
),
area_10 AS (
    SELECT r.network_budget_s, r.reachable_node_count,
           ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Buffer(
             ST_UnaryUnion(ST_Collect(r.geometry_utm, a.geometry_utm)),
             :nesting_tolerance_m
           )), 3)) AS geometry_utm
    FROM raw_areas AS r CROSS JOIN area_5 AS a
    WHERE r.threshold_s = 600
),
area_15 AS (
    SELECT r.network_budget_s, r.reachable_node_count,
           ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Buffer(
             ST_UnaryUnion(ST_Collect(r.geometry_utm, a.geometry_utm)),
             :nesting_tolerance_m
           )), 3)) AS geometry_utm
    FROM raw_areas AS r CROSS JOIN area_10 AS a
    WHERE r.threshold_s = 900
),
final_areas(minutes, threshold_s, network_budget_s, reachable_node_count, geometry_utm) AS (
    SELECT 5, 300, network_budget_s, reachable_node_count, geometry_utm FROM area_5
    UNION ALL
    SELECT 10, 600, network_budget_s, reachable_node_count, geometry_utm FROM area_10
    UNION ALL
    SELECT 15, 900, network_budget_s, reachable_node_count, geometry_utm FROM area_15
),
poi_times AS MATERIALIZED (
    SELECT p.id AS poi_id, p.osm_type, p.osm_id, p.name,
           p.category, p.subcategory, ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat,
           ST_AsGeoJSON(p.geometry, 15)::json AS geometry,
           d.agg_cost AS network_time_s,
           access.snap_distance_m AS poi_snap_distance_m,
           access.snap_distance_m / :walk_speed_mps AS poi_connector_time_s,
           :origin_connector_s + d.agg_cost
             + access.snap_distance_m / :walk_speed_mps AS total_walk_time_s
    FROM driving AS d
    JOIN poi_walk_access AS access ON access.node_id = d.node
    JOIN pois AS p ON p.id = access.poi_id
    WHERE p.category IN (
      'commercial', 'healthcare', 'education', 'recreation', 'transport'
    )
      AND :origin_connector_s + d.agg_cost
            + access.snap_distance_m / :walk_speed_mps <= 900
),
category_names(category) AS (
    VALUES ('commercial'), ('healthcare'), ('education'), ('recreation'), ('transport')
),
category_stats AS (
    SELECT c.category,
           COUNT(p.poi_id) FILTER (WHERE p.total_walk_time_s <= 300)::integer AS reachable_5min,
           COUNT(p.poi_id) FILTER (WHERE p.total_walk_time_s <= 600)::integer AS reachable_10min,
           COUNT(p.poi_id)::integer AS reachable_15min,
           COUNT(DISTINCT p.subcategory)::integer AS unique_subcategory_count,
           MIN(p.total_walk_time_s) AS nearest_walk_time_s,
           (jsonb_agg(jsonb_build_object(
              'poi_id', p.poi_id, 'name', p.name, 'subcategory', p.subcategory
            ) ORDER BY p.total_walk_time_s, p.poi_snap_distance_m, p.poi_id)
            FILTER (WHERE p.poi_id IS NOT NULL))->0 AS nearest_poi
    FROM category_names AS c
    LEFT JOIN poi_times AS p ON p.category = c.category
    GROUP BY c.category
),
ranked_pois AS (
    SELECT p.*,
           ROW_NUMBER() OVER (
             PARTITION BY category
             ORDER BY total_walk_time_s, poi_snap_distance_m, poi_id
           ) AS category_rank
    FROM poi_times AS p
),
display_pois AS (
    SELECT * FROM ranked_pois WHERE category_rank <= :display_limit
),
quality AS (
    SELECT (SELECT COUNT(*)::integer FROM pois) AS total_pois,
           (SELECT COUNT(*)::integer FROM poi_walk_access) AS mapped_pois,
           (SELECT COUNT(*)::integer FROM poi_times) AS reachable_core_pois_15min,
           (SELECT COUNT(*)::integer FROM display_pois) AS displayed_pois
)
SELECT
  (SELECT json_agg(json_build_object(
      'minutes', minutes,
      'threshold_s', threshold_s,
      'network_budget_s', network_budget_s,
      'reachable_node_count', reachable_node_count,
      'area_m2', ST_Area(geometry_utm),
      'geometry', ST_AsGeoJSON(ST_Transform(geometry_utm, 4326), 15)::json
    ) ORDER BY threshold_s) FROM final_areas) AS bands,
  (SELECT json_agg(json_build_object(
      'category', category,
      'reachable_5min', reachable_5min,
      'reachable_10min', reachable_10min,
      'reachable_15min', reachable_15min,
      'unique_subcategory_count', unique_subcategory_count,
      'nearest_walk_time_s', nearest_walk_time_s,
      'nearest_poi', nearest_poi
    ) ORDER BY CASE category
        WHEN 'commercial' THEN 1 WHEN 'healthcare' THEN 2
        WHEN 'education' THEN 3 WHEN 'recreation' THEN 4 ELSE 5 END
    ) FROM category_stats) AS category_stats,
  (SELECT json_agg(json_build_object(
      'poi_id', poi_id, 'osm_type', osm_type, 'osm_id', osm_id,
      'name', name, 'category', category, 'subcategory', subcategory,
      'lon', lon, 'lat', lat,
      'geometry', geometry, 'network_time_s', network_time_s,
      'poi_snap_distance_m', poi_snap_distance_m,
      'poi_connector_time_s', poi_connector_time_s,
      'total_walk_time_s', total_walk_time_s
    ) ORDER BY total_walk_time_s, poi_id) FROM display_pois) AS display_pois,
  quality.total_pois, quality.mapped_pois,
  quality.reachable_core_pois_15min, quality.displayed_pois
FROM quality
"""


class PedestrianNetworkUnavailableError(RuntimeError):
    pass


class PoiWalkAccessUnavailableError(RuntimeError):
    pass


class PedestrianSnapNotFoundError(ValueError):
    pass


class LivingCircleGeometryError(RuntimeError):
    pass


def _require_phase8_data(db: Session) -> None:
    names = ("pedestrian_nodes", "pedestrian_edges", "poi_walk_access")
    present = {
        name: db.scalar(text("SELECT to_regclass(:name)"), {"name": f"public.{name}"})
        for name in names
    }
    if not present["pedestrian_nodes"] or not present["pedestrian_edges"]:
        raise PedestrianNetworkUnavailableError("Pedestrian network is not prepared")
    node_count, edge_count = db.execute(
        text("SELECT (SELECT COUNT(*) FROM pedestrian_nodes), "
             "(SELECT COUNT(*) FROM pedestrian_edges)")
    ).one()
    if not node_count or not edge_count:
        raise PedestrianNetworkUnavailableError("Pedestrian network is empty")
    if not present["poi_walk_access"]:
        raise PoiWalkAccessUnavailableError("POI walking access is not prepared")
    if not db.scalar(text("SELECT EXISTS (SELECT 1 FROM poi_walk_access)")):
        raise PoiWalkAccessUnavailableError("POI walking access is empty")


def snap_to_pedestrian_network(
    db: Session, *, lon: float, lat: float, max_snap_m: int
) -> PedestrianSnap:
    row = db.execute(
        text("""
          WITH query_point AS (
            SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geometry
          )
          SELECT n.osm_node_id AS node_id,
                 ST_X(n.geometry) AS node_lon,
                 ST_Y(n.geometry) AS node_lat,
                 ST_Distance(n.geometry::geography, q.geometry) AS snap_distance_m
          FROM pedestrian_nodes AS n CROSS JOIN query_point AS q
          WHERE ST_DWithin(n.geometry::geography, q.geometry, :max_snap_m)
          ORDER BY n.geometry::geography <-> q.geometry, n.osm_node_id
          LIMIT 1
        """),
        {"lon": lon, "lat": lat, "max_snap_m": max_snap_m},
    ).mappings().one_or_none()
    if row is None:
        raise PedestrianSnapNotFoundError(
            f"No pedestrian network node found within {max_snap_m} meters"
        )
    distance = float(row["snap_distance_m"])
    return PedestrianSnap(
        node_id=int(row["node_id"]),
        node_lon=float(row["node_lon"]),
        node_lat=float(row["node_lat"]),
        snap_distance_m=round(distance, 1),
        connector_time_s=round(distance / WALK_SPEED_MPS, 1),
    )


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def analyze_living_circle(
    db: Session, *, origin: RoutePoint, max_snap_m: int
) -> LivingCircleResponse:
    _require_phase8_data(db)
    snap = snap_to_pedestrian_network(
        db, lon=origin.lon, lat=origin.lat, max_snap_m=max_snap_m
    )
    row = db.execute(
        text(LIVING_CIRCLE_SQL),
        {
            "edges_sql": PEDESTRIAN_EDGES_SQL,
            "start_node": snap.node_id,
            "origin_connector_s": snap.connector_time_s,
            "walk_speed_mps": WALK_SPEED_MPS,
            "hull_target_percent": CONCAVE_HULL_TARGET_PERCENT,
            "fallback_buffer_m": DEGENERATE_BUFFER_M,
            "nesting_tolerance_m": NESTING_TOLERANCE_M,
            "display_limit": DISPLAY_LIMIT_PER_CATEGORY,
        },
    ).mappings().one()

    bands_data = _json_value(row["bands"]) or []
    if len(bands_data) != 3 or any(not item.get("geometry") for item in bands_data):
        raise LivingCircleGeometryError("Walking isochrone geometry could not be built")
    bands = [
        LivingCircleBandFeature(
            geometry=item["geometry"],
            properties=LivingCircleBandProperties(
                minutes=int(item["minutes"]),
                threshold_s=int(item["threshold_s"]),
                network_budget_s=round(float(item["network_budget_s"]), 1),
                reachable_node_count=int(item["reachable_node_count"]),
                area_m2=round(float(item["area_m2"]), 1),
                area_km2=round(float(item["area_m2"]) / 1_000_000.0, 4),
            ),
        )
        for item in bands_data
    ]
    categories = [
        LivingCircleCategorySummary(
            category=item["category"],
            reachable_poi_count=int(item["reachable_15min"]),
            unique_subcategory_count=int(item["unique_subcategory_count"]),
            reachable_5min=int(item["reachable_5min"]),
            reachable_10min=int(item["reachable_10min"]),
            reachable_15min=int(item["reachable_15min"]),
            nearest_walk_time_s=(
                round(float(item["nearest_walk_time_s"]), 1)
                if item["nearest_walk_time_s"] is not None
                else None
            ),
            nearest_walk_time_min=(
                round(float(item["nearest_walk_time_s"]) / 60.0, 2)
                if item["nearest_walk_time_s"] is not None else None
            ),
            nearest_poi=item["nearest_poi"],
        )
        for item in (_json_value(row["category_stats"]) or [])
    ]
    poi_features = []
    for item in _json_value(row["display_pois"]) or []:
        total = float(item["total_walk_time_s"])
        poi_features.append(
            ReachablePoiFeature(
                geometry=item["geometry"],
                properties=ReachablePoiProperties(
                    poi_id=int(item["poi_id"]),
                    osm_type=item["osm_type"],
                    osm_id=item["osm_id"],
                    name=item["name"],
                    category=item["category"],
                    subcategory=item["subcategory"],
                    lon=float(item["lon"]),
                    lat=float(item["lat"]),
                    total_walk_time_s=round(total, 1),
                    total_walk_time_min=round(total / 60.0, 2),
                    network_time_s=round(float(item["network_time_s"]), 1),
                    origin_connector_time_s=snap.connector_time_s,
                    poi_connector_time_s=round(float(item["poi_connector_time_s"]), 1),
                    poi_snap_distance_m=round(float(item["poi_snap_distance_m"]), 1),
                ),
            )
        )

    present = sum(item.reachable_15min > 0 for item in categories)
    total_pois = int(row["total_pois"])
    mapped_pois = int(row["mapped_pois"])
    band_15 = bands[-1].properties
    reachable_total = int(row["reachable_core_pois_15min"])
    displayed_total = int(row["displayed_pois"])
    return LivingCircleResponse(
        origin=origin,
        origin_snap=snap,
        isochrones=LivingCircleBandCollection(features=bands),
        summary=LivingCircleSummary(
            reachable_poi_count=reachable_total,
            displayed_poi_count=displayed_total,
            covered_categories=present,
            category_coverage_ratio=round(present / len(CORE_CATEGORIES), 2),
            area_15min_m2=band_15.area_m2,
            area_15min_km2=band_15.area_km2,
            reachable_nodes_15min=band_15.reachable_node_count,
        ),
        coverage=LivingCircleCoverage(
            present_categories=present,
            presence_ratio=round(present / len(CORE_CATEGORIES), 2),
        ),
        categories=categories,
        reachable_pois=ReachablePoiCollection(features=poi_features),
        data_quality=LivingCircleDataQuality(
            total_pois=total_pois,
            mapped_pois=mapped_pois,
            unmapped_pois=total_pois - mapped_pois,
            mapped_ratio=round(mapped_pois / total_pois, 4) if total_pois else 0.0,
            reachable_core_pois_15min=reachable_total,
            displayed_pois=displayed_total,
        ),
        walking_model=WalkingModelMetadata(),
    )
