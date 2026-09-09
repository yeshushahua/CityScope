from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.routing import RoutePoint

LivingCircleCategory = Literal[
    "commercial", "healthcare", "education", "recreation", "transport"
]


class LivingCircleRequest(BaseModel):
    origin: RoutePoint
    max_snap_m: int = Field(default=300, ge=50, le=300)


class PedestrianSnap(BaseModel):
    node_id: int
    node_lon: float
    node_lat: float
    snap_distance_m: float
    connector_time_s: float


class LivingCircleBandProperties(BaseModel):
    minutes: Literal[5, 10, 15]
    threshold_s: Literal[300, 600, 900]
    network_budget_s: float
    reachable_node_count: int
    area_m2: float
    area_km2: float


class LivingCircleBandFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: LivingCircleBandProperties


class LivingCircleBandCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[LivingCircleBandFeature]


class NearestLivingCirclePoi(BaseModel):
    poi_id: int
    name: str | None
    subcategory: str


class LivingCircleCategorySummary(BaseModel):
    category: LivingCircleCategory
    reachable_poi_count: int
    unique_subcategory_count: int
    reachable_5min: int
    reachable_10min: int
    reachable_15min: int
    nearest_walk_time_min: float | None
    nearest_walk_time_s: float | None
    nearest_poi: NearestLivingCirclePoi | None


class ReachablePoiProperties(BaseModel):
    poi_id: int
    osm_type: str
    osm_id: str
    name: str | None
    category: LivingCircleCategory
    subcategory: str
    lon: float
    lat: float
    total_walk_time_s: float
    total_walk_time_min: float
    network_time_s: float
    origin_connector_time_s: float
    poi_connector_time_s: float
    poi_snap_distance_m: float


class ReachablePoiFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: ReachablePoiProperties


class ReachablePoiCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ReachablePoiFeature]


class LivingCircleCoverage(BaseModel):
    present_categories: int
    total_categories: Literal[5] = 5
    presence_ratio: float
    definition: Literal["reachable_core_category_presence"] = (
        "reachable_core_category_presence"
    )


class LivingCircleSummary(BaseModel):
    reachable_poi_count: int
    displayed_poi_count: int
    covered_categories: int
    primary_categories: Literal[5] = 5
    category_coverage_ratio: float
    area_15min_m2: float
    area_15min_km2: float
    reachable_nodes_15min: int


class LivingCircleDataQuality(BaseModel):
    total_pois: int
    mapped_pois: int
    unmapped_pois: int
    mapped_ratio: float
    reachable_core_pois_15min: int
    displayed_pois: int
    display_limit_per_category: Literal[30] = 30


class WalkingModelMetadata(BaseModel):
    network_type: Literal["walk"] = "walk"
    cost_model: Literal["static_walking_time"] = "static_walking_time"
    walk_speed_kph: Literal[4.8] = 4.8
    directed: Literal[True] = True
    origin_connector_included: Literal[True] = True
    poi_connector_included: Literal[True] = True
    poi_eligibility: Literal["network_cost"] = "network_cost"
    service_area_method: Literal["reachable_pedestrian_vertex_concave_hull"] = (
        "reachable_pedestrian_vertex_concave_hull"
    )


class LivingCircleResponse(BaseModel):
    origin: RoutePoint
    origin_snap: PedestrianSnap
    isochrones: LivingCircleBandCollection
    summary: LivingCircleSummary
    coverage: LivingCircleCoverage
    categories: list[LivingCircleCategorySummary]
    reachable_pois: ReachablePoiCollection
    data_quality: LivingCircleDataQuality
    walking_model: WalkingModelMetadata
