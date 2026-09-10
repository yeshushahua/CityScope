from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.routing import IsochroneFeatureCollection, NetworkSnap, RoutePoint

IncidentType = Literal["medical", "fire"]


class EmergencyResponseRequest(BaseModel):
    incident: RoutePoint
    incident_type: IncidentType
    max_snap_m: int = Field(default=500, ge=100, le=1000)
    candidate_limit: int = Field(default=3, ge=1, le=10)


class EmergencyFacilityCandidate(BaseModel):
    network_rank: int
    poi_id: int
    osm_type: str
    osm_id: str
    name: str | None
    category: Literal["healthcare", "emergency"]
    subcategory: Literal["hospital", "fire_station"]
    lon: float
    lat: float
    node_id: int | None
    edge_id: int | None = None
    fraction: float | None = Field(default=None, ge=0, le=1)
    snapped_lon: float | None = None
    snapped_lat: float | None = None
    facility_snap_distance_m: float
    straight_distance_m: float
    response_time_s: float
    response_time_min: float


class EmergencyFacilityStatistics(BaseModel):
    total: int
    mapped: int
    unmapped: int
    reachable: int
    unreachable: int
    returned: int


class EmergencyRouteProperties(BaseModel):
    network_distance_m: float
    response_time_s: float
    response_time_min: float
    edge_count: int
    edge_ids: list[int]
    routing_direction: Literal["facility_to_incident"] = "facility_to_incident"


class EmergencyRouteFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: EmergencyRouteProperties


class EmergencyComparison(BaseModel):
    straight_nearest_facility_id: int
    network_best_facility_id: int
    straight_nearest_is_network_best: bool


class EmergencyModelMetadata(BaseModel):
    cost_model: Literal["static_travel_time"] = "static_travel_time"
    directed: Literal[True] = True
    routing_direction: Literal["facility_to_incident"] = "facility_to_incident"
    service_area_method: Literal["reachable_vertex_concave_hull"] = (
        "reachable_vertex_concave_hull"
    )


class EmergencyResponse(BaseModel):
    incident_type: IncidentType
    incident: RoutePoint
    incident_snap: NetworkSnap
    facility_statistics: EmergencyFacilityStatistics
    recommended_facility: EmergencyFacilityCandidate
    candidate_facilities: list[EmergencyFacilityCandidate]
    response_route: EmergencyRouteFeature
    response_isochrones: IsochroneFeatureCollection
    comparison: EmergencyComparison
    model_metadata: EmergencyModelMetadata
