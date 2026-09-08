from typing import Any, Literal

from pydantic import BaseModel, Field


class RoutePoint(BaseModel):
    lon: float = Field(ge=103, le=105)
    lat: float = Field(ge=35, le=37)


class NetworkSnap(BaseModel):
    node_id: int
    node_lon: float
    node_lat: float
    snap_distance_m: float


class RouteProperties(BaseModel):
    routing_distance_m: float
    travel_time_s: float
    travel_time_min: float
    edge_count: int
    edge_ids: list[int]


class RouteFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: RouteProperties


class ShortestPathRequest(BaseModel):
    start: RoutePoint
    end: RoutePoint
    max_snap_m: int = Field(default=500, ge=100, le=1000)


class ShortestPathResponse(BaseModel):
    route_found: Literal[True] = True
    start: RoutePoint
    end: RoutePoint
    start_snap: NetworkSnap
    end_snap: NetworkSnap
    route: RouteFeature


FacilityCategory = Literal["healthcare", "emergency"]
FacilitySubcategory = Literal["hospital", "clinic", "doctors", "fire_station"]


class FacilityCandidate(BaseModel):
    rank: int
    poi_id: int
    osm_type: str
    osm_id: str
    name: str | None
    category: FacilityCategory
    subcategory: FacilitySubcategory
    lon: float
    lat: float
    node_id: int
    straight_distance_m: float
    network_distance_m: float
    travel_time_s: float
    travel_time_min: float
    facility_snap_distance_m: float


class NearestFacilityMeta(BaseModel):
    facility_count: int
    mapped_count: int
    reachable_count: int
    unreachable_count: int
    returned_count: int


class NearestFacilityResponse(BaseModel):
    origin: RoutePoint
    origin_snap: NetworkSnap
    best: FacilityCandidate
    candidates: list[FacilityCandidate]
    route: RouteFeature
    meta: NearestFacilityMeta
