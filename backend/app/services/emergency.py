from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.types import BigInteger

from app.schemas.emergency import (
    EmergencyComparison,
    EmergencyFacilityCandidate,
    EmergencyFacilityStatistics,
    EmergencyModelMetadata,
    EmergencyResponse,
    EmergencyRouteFeature,
    EmergencyRouteProperties,
    IncidentType,
)
from app.schemas.routing import RoutePoint
from app.services.routing import (
    EDGES_SQL,
    FacilityNotFoundError,
    ReachableFacilityNotFoundError,
    _facility_edge_locations,
    _facility_rows,
    _network_snap,
    build_isochrones_from_points,
)
from app.services.edge_routing import PathChoice, route_feature_for_choice, with_points_costs
from app.services.network_snapping import (
    EdgeSnapCandidate,
    WithPointsRegistry,
    snap_points_to_edges,
)

FACILITY_FILTERS: dict[IncidentType, tuple[str, str]] = {
    "medical": ("healthcare", "hospital"),
    "fire": ("emergency", "fire_station"),
}

EMERGENCY_COSTS_SQL = """
SELECT start_vid, end_vid, agg_cost
FROM pgr_dijkstraCost(
    :edges_sql,
    :source_nodes,
    CAST(:incident_node AS bigint),
    directed => true
)
"""


def _costs_from_facilities_to_incident(
    db: Session,
    *,
    source_nodes: list[int],
    incident_node: int,
) -> dict[int, float]:
    remaining = [node for node in source_nodes if node != incident_node]
    costs = {incident_node: 0.0} if incident_node in source_nodes else {}
    if not remaining:
        return costs
    statement = text(EMERGENCY_COSTS_SQL).bindparams(
        bindparam("source_nodes", type_=ARRAY(BigInteger))
    )
    rows = db.execute(
        statement,
        {
            "edges_sql": EDGES_SQL,
            "source_nodes": remaining,
            "incident_node": incident_node,
        },
    ).mappings()
    costs.update(
        {int(row["start_vid"]): float(row["agg_cost"]) for row in rows}
    )
    return costs


def _candidate(
    row: dict[str, Any],
    *,
    rank: int,
    response_time_s: float,
    snap: EdgeSnapCandidate,
) -> EmergencyFacilityCandidate:
    return EmergencyFacilityCandidate(
        network_rank=rank,
        poi_id=int(row["poi_id"]),
        osm_type=str(row["osm_type"]),
        osm_id=str(row["osm_id"]),
        name=row["name"],
        category=row["category"],
        subcategory=row["subcategory"],
        lon=float(row["lon"]),
        lat=float(row["lat"]),
        node_id=snap.node_id,
        edge_id=snap.edge_id,
        fraction=snap.fraction,
        snapped_lon=snap.snapped_lon,
        snapped_lat=snap.snapped_lat,
        facility_snap_distance_m=round(snap.snap_distance_m, 1),
        straight_distance_m=round(float(row["straight_distance_m"]), 1),
        response_time_s=round(response_time_s, 1),
        response_time_min=round(response_time_s / 60, 2),
    )


def analyze_emergency_response(
    db: Session,
    *,
    incident: RoutePoint,
    incident_type: IncidentType,
    max_snap_m: int,
    candidate_limit: int,
) -> EmergencyResponse:
    incident_location = snap_points_to_edges(
        db,
        points=[("incident", incident.lon, incident.lat)],
        max_snap_m=max_snap_m,
    )["incident"]
    category, subcategory = FACILITY_FILTERS[incident_type]
    facility_total, facilities = _facility_rows(
        db,
        origin=incident,
        category=category,
        subcategory=subcategory,
    )
    if not facilities:
        raise FacilityNotFoundError(
            "Matching emergency facilities are not mapped to the road network"
        )

    facility_locations = _facility_edge_locations(db, facilities)
    registry = WithPointsRegistry()
    registered_incident = registry.register(incident_location)
    registered_facilities = {
        int(row["poi_id"]): registry.register(facility_locations[int(row["poi_id"])])
        for row in facilities
    }
    start_vid_to_pois: dict[int, list[int]] = {}
    for poi_id, registered in registered_facilities.items():
        for vid in registered.vids:
            start_vid_to_pois.setdefault(vid, []).append(poi_id)
    choices = with_points_costs(
        db,
        registry=registry,
        start_vids=sorted(start_vid_to_pois),
        end_vids=registered_incident.vids,
    )
    best_choices: dict[int, PathChoice] = {}
    for choice in choices:
        for poi_id in start_vid_to_pois.get(choice.start_vid, []):
            best_choices.setdefault(poi_id, choice)
    reachable = [row for row in facilities if int(row["poi_id"]) in best_choices]
    if not reachable:
        raise ReachableFacilityNotFoundError(
            "No matching emergency facility can reach the incident node"
        )
    reachable.sort(
        key=lambda row: (
            best_choices[int(row["poi_id"])].cost,
            registered_facilities[int(row["poi_id"])].candidate_for_vid(
                best_choices[int(row["poi_id"])].start_vid
            ).snap_distance_m,
            float(row["straight_distance_m"]),
            int(row["poi_id"]),
        )
    )
    selected = reachable[:candidate_limit]
    candidates: list[EmergencyFacilityCandidate] = []
    for rank, row in enumerate(selected, start=1):
        poi_id = int(row["poi_id"])
        choice = best_choices[poi_id]
        candidates.append(
            _candidate(
                row,
                rank=rank,
                response_time_s=choice.cost,
                snap=registered_facilities[poi_id].candidate_for_vid(choice.start_vid),
            )
        )
    recommended_row = selected[0]
    recommended = candidates[0]
    recommended_poi_id = int(recommended_row["poi_id"])
    recommended_choice = best_choices[recommended_poi_id]
    recommended_snap = registered_facilities[recommended_poi_id].candidate_for_vid(
        recommended_choice.start_vid
    )
    incident_snap = registered_incident.candidate_for_vid(recommended_choice.end_vid)

    base_route = route_feature_for_choice(
        db,
        registry=registry,
        choice=recommended_choice,
        zero_coordinate=(recommended_snap.snapped_lon, recommended_snap.snapped_lat)
        if recommended_choice.start_vid == recommended_choice.end_vid
        else None,
    )
    route = EmergencyRouteFeature(
        geometry=base_route.geometry,
        properties=EmergencyRouteProperties(
            network_distance_m=base_route.properties.routing_distance_m,
            response_time_s=base_route.properties.travel_time_s,
            response_time_min=base_route.properties.travel_time_min,
            edge_count=base_route.properties.edge_count,
            edge_ids=base_route.properties.edge_ids,
        ),
    )
    response_isochrones = build_isochrones_from_points(
        db,
        registry=registry,
        start_vids=registered_facilities[recommended_poi_id].vids,
    )
    straight_nearest = min(
        facilities,
        key=lambda row: (
            float(row["straight_distance_m"]),
            float(row["snap_distance_m"]),
            int(row["poi_id"]),
        ),
    )
    straight_id = int(straight_nearest["poi_id"])

    return EmergencyResponse(
        incident_type=incident_type,
        incident=incident,
        incident_snap=_network_snap(incident_snap),
        facility_statistics=EmergencyFacilityStatistics(
            total=facility_total,
            mapped=len(facilities),
            unmapped=facility_total - len(facilities),
            reachable=len(reachable),
            unreachable=len(facilities) - len(reachable),
            returned=len(candidates),
        ),
        recommended_facility=recommended,
        candidate_facilities=candidates,
        response_route=route,
        response_isochrones=response_isochrones,
        comparison=EmergencyComparison(
            straight_nearest_facility_id=straight_id,
            network_best_facility_id=recommended.poi_id,
            straight_nearest_is_network_best=(straight_id == recommended.poi_id),
        ),
        model_metadata=EmergencyModelMetadata(),
    )
