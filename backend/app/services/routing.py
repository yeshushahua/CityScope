import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.types import BigInteger

from app.schemas.routing import (
    FacilityCandidate,
    NearestFacilityMeta,
    NearestFacilityResponse,
    NetworkSnap,
    RouteFeature,
    RoutePoint,
    RouteProperties,
    ShortestPathResponse,
)

EDGES_SQL = "SELECT id, source, target, cost, reverse_cost FROM routing_edges"


class SnapNotFoundError(ValueError):
    pass


class RouteNotFoundError(ValueError):
    pass


class FacilityNotFoundError(ValueError):
    pass


class ReachableFacilityNotFoundError(ValueError):
    pass


def snap_point_to_network(
    db: Session, *, lon: float, lat: float, max_snap_m: int
) -> NetworkSnap:
    row = db.execute(
        text(
            """
            WITH query_point AS (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geometry
            )
            SELECT n.osm_node_id AS node_id,
                   ST_X(n.geometry) AS node_lon,
                   ST_Y(n.geometry) AS node_lat,
                   ST_Distance(n.geometry::geography, q.geometry) AS snap_distance_m
            FROM road_nodes AS n
            CROSS JOIN query_point AS q
            WHERE ST_DWithin(n.geometry::geography, q.geometry, :max_snap_m)
            ORDER BY n.geometry::geography <-> q.geometry, n.osm_node_id
            LIMIT 1
            """
        ),
        {"lon": lon, "lat": lat, "max_snap_m": max_snap_m},
    ).mappings().one_or_none()
    if row is None:
        raise SnapNotFoundError(
            f"No road network node found within {max_snap_m} meters"
        )
    return NetworkSnap(
        node_id=int(row["node_id"]),
        node_lon=float(row["node_lon"]),
        node_lat=float(row["node_lat"]),
        snap_distance_m=round(float(row["snap_distance_m"]), 1),
    )


def _path_rows(db: Session, start_node: int, end_node: int) -> list[dict[str, Any]]:
    if start_node == end_node:
        return []
    rows = db.execute(
        text(
            """
            SELECT route.path_seq, route.node, route.edge,
                   edge.source, edge.target, edge.length_m, edge.cost,
                   ST_AsGeoJSON(edge.geometry)::json AS geometry
            FROM pgr_dijkstra(
                :edges_sql,
                CAST(:start_node AS bigint),
                CAST(:end_node AS bigint),
                directed => true
            ) AS route
            JOIN routing_edges AS edge ON edge.id = route.edge
            WHERE route.edge <> -1
            ORDER BY route.path_seq
            """
        ),
        {
            "edges_sql": EDGES_SQL,
            "start_node": start_node,
            "end_node": end_node,
        },
    ).mappings()
    return [dict(row) for row in rows]


def _geometry_coordinates(rows: Iterable[dict[str, Any]]) -> list[list[float]]:
    coordinates: list[list[float]] = []
    previous_target: int | None = None
    for row in rows:
        if previous_target is not None and previous_target != int(row["source"]):
            raise RuntimeError("pgRouting returned a discontinuous directed path")
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        segment = [[float(value) for value in pair] for pair in geometry["coordinates"]]
        if coordinates and coordinates[-1] != segment[0]:
            raise RuntimeError("Route edge geometries are not endpoint-continuous")
        coordinates.extend(segment if not coordinates else segment[1:])
        previous_target = int(row["target"])
    return coordinates


def _route_feature(
    rows: list[dict[str, Any]], *, zero_coordinate: tuple[float, float] | None = None
) -> RouteFeature:
    if rows:
        coordinates = _geometry_coordinates(rows)
    elif zero_coordinate is not None:
        coordinates = [list(zero_coordinate), list(zero_coordinate)]
    else:
        raise RouteNotFoundError("No routable path between snapped nodes")
    distance = sum(float(row["length_m"]) for row in rows)
    travel_time = sum(float(row["cost"]) for row in rows)
    return RouteFeature(
        geometry={"type": "LineString", "coordinates": coordinates},
        properties=RouteProperties(
            routing_distance_m=round(distance, 1),
            travel_time_s=round(travel_time, 1),
            travel_time_min=round(travel_time / 60, 2),
            edge_count=len(rows),
            edge_ids=[int(row["edge"]) for row in rows],
        ),
    )


def shortest_path(
    db: Session,
    *,
    start: RoutePoint,
    end: RoutePoint,
    max_snap_m: int,
) -> ShortestPathResponse:
    start_snap = snap_point_to_network(
        db, lon=start.lon, lat=start.lat, max_snap_m=max_snap_m
    )
    end_snap = snap_point_to_network(
        db, lon=end.lon, lat=end.lat, max_snap_m=max_snap_m
    )
    rows = _path_rows(db, start_snap.node_id, end_snap.node_id)
    zero_coordinate = (
        (start_snap.node_lon, start_snap.node_lat)
        if start_snap.node_id == end_snap.node_id
        else None
    )
    route = _route_feature(rows, zero_coordinate=zero_coordinate)
    return ShortestPathResponse(
        start=start,
        end=end,
        start_snap=start_snap,
        end_snap=end_snap,
        route=route,
    )


def _facility_rows(
    db: Session,
    *,
    origin: RoutePoint,
    category: str,
    subcategory: str | None,
) -> tuple[int, list[dict[str, Any]]]:
    filters = ["p.category = :category"]
    params: dict[str, Any] = {
        "lon": origin.lon,
        "lat": origin.lat,
        "category": category,
    }
    if subcategory:
        filters.append("p.subcategory = :subcategory")
        params["subcategory"] = subcategory
    facility_count = int(
        db.scalar(
            text(f"SELECT COUNT(*) FROM pois p WHERE {' AND '.join(filters)}"),
            params,
        )
        or 0
    )
    if facility_count == 0:
        raise FacilityNotFoundError("No facilities match the requested type")
    rows = db.execute(
        text(
            f"""
            WITH origin AS (
                SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS geometry
            )
            SELECT p.id AS poi_id, p.osm_type, p.osm_id, p.name,
                   p.category, p.subcategory,
                   ST_X(p.geometry) AS lon, ST_Y(p.geometry) AS lat,
                   access.node_id, access.snap_distance_m,
                   ST_X(node.geometry) AS node_lon,
                   ST_Y(node.geometry) AS node_lat,
                   ST_Distance(p.geometry::geography, origin.geometry)
                       AS straight_distance_m
            FROM pois AS p
            JOIN poi_routing_access AS access ON access.poi_id = p.id
            JOIN road_nodes AS node ON node.osm_node_id = access.node_id
            CROSS JOIN origin
            WHERE {' AND '.join(filters)}
            ORDER BY p.id
            """
        ),
        params,
    ).mappings()
    return facility_count, [dict(row) for row in rows]


def _costs_to_targets(
    db: Session, start_node: int, target_nodes: list[int]
) -> dict[int, float]:
    statement = text(
        """
        SELECT end_vid, agg_cost
        FROM pgr_dijkstraCost(
            :edges_sql,
            CAST(:start_node AS bigint),
            :target_nodes,
            directed => true
        )
        """
    ).bindparams(bindparam("target_nodes", type_=ARRAY(BigInteger)))
    rows = db.execute(
        statement,
        {
            "edges_sql": EDGES_SQL,
            "start_node": start_node,
            "target_nodes": target_nodes,
        },
    ).mappings()
    costs = {int(row["end_vid"]): float(row["agg_cost"]) for row in rows}
    if start_node in target_nodes:
        costs[start_node] = 0.0
    return costs


def _paths_to_targets(
    db: Session, start_node: int, target_nodes: list[int]
) -> dict[int, list[dict[str, Any]]]:
    paths: dict[int, list[dict[str, Any]]] = {node: [] for node in target_nodes if node == start_node}
    remaining = [node for node in target_nodes if node != start_node]
    if not remaining:
        return paths
    statement = text(
        """
        SELECT route.end_vid, route.path_seq, route.node, route.edge,
               edge.source, edge.target, edge.length_m, edge.cost,
               ST_AsGeoJSON(edge.geometry)::json AS geometry
        FROM pgr_dijkstra(
            :edges_sql,
            CAST(:start_node AS bigint),
            :target_nodes,
            directed => true
        ) AS route
        JOIN routing_edges AS edge ON edge.id = route.edge
        WHERE route.edge <> -1
        ORDER BY route.end_vid, route.path_seq
        """
    ).bindparams(bindparam("target_nodes", type_=ARRAY(BigInteger)))
    for row in db.execute(
        statement,
        {
            "edges_sql": EDGES_SQL,
            "start_node": start_node,
            "target_nodes": remaining,
        },
    ).mappings():
        paths.setdefault(int(row["end_vid"]), []).append(dict(row))
    return paths


def nearest_facility(
    db: Session,
    *,
    origin: RoutePoint,
    category: str,
    subcategory: str | None,
    max_snap_m: int,
    limit: int,
) -> NearestFacilityResponse:
    origin_snap = snap_point_to_network(
        db, lon=origin.lon, lat=origin.lat, max_snap_m=max_snap_m
    )
    facility_count, facilities = _facility_rows(
        db, origin=origin, category=category, subcategory=subcategory
    )
    if not facilities:
        raise FacilityNotFoundError("Matching facilities are not mapped to the road network")
    target_nodes = sorted({int(row["node_id"]) for row in facilities})
    costs = _costs_to_targets(db, origin_snap.node_id, target_nodes)
    reachable = [row for row in facilities if int(row["node_id"]) in costs]
    if not reachable:
        raise ReachableFacilityNotFoundError(
            "No requested facility is reachable from the snapped origin"
        )
    reachable.sort(
        key=lambda row: (
            costs[int(row["node_id"])],
            float(row["snap_distance_m"]),
            float(row["straight_distance_m"]),
            int(row["poi_id"]),
        )
    )
    selected = reachable[:limit]
    selected_nodes = sorted({int(row["node_id"]) for row in selected})
    paths = _paths_to_targets(db, origin_snap.node_id, selected_nodes)
    candidates: list[FacilityCandidate] = []
    for rank, row in enumerate(selected, start=1):
        node_id = int(row["node_id"])
        path_rows = paths.get(node_id, [])
        distance = sum(float(edge["length_m"]) for edge in path_rows)
        travel_time = costs[node_id]
        candidates.append(
            FacilityCandidate(
                rank=rank,
                poi_id=int(row["poi_id"]),
                osm_type=str(row["osm_type"]),
                osm_id=str(row["osm_id"]),
                name=row["name"],
                category=row["category"],
                subcategory=row["subcategory"],
                lon=float(row["lon"]),
                lat=float(row["lat"]),
                node_id=node_id,
                straight_distance_m=round(float(row["straight_distance_m"]), 1),
                network_distance_m=round(distance, 1),
                travel_time_s=round(travel_time, 1),
                travel_time_min=round(travel_time / 60, 2),
                facility_snap_distance_m=round(float(row["snap_distance_m"]), 1),
            )
        )
    best_row = selected[0]
    best_node = int(best_row["node_id"])
    best_route = _route_feature(
        paths.get(best_node, []),
        zero_coordinate=(origin_snap.node_lon, origin_snap.node_lat)
        if best_node == origin_snap.node_id
        else None,
    )
    return NearestFacilityResponse(
        origin=origin,
        origin_snap=origin_snap,
        best=candidates[0],
        candidates=candidates,
        route=best_route,
        meta=NearestFacilityMeta(
            facility_count=facility_count,
            mapped_count=len(facilities),
            reachable_count=len(reachable),
            unreachable_count=len(facilities) - len(reachable),
            returned_count=len(candidates),
        ),
    )
