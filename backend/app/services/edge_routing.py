import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.routing import RouteFeature, RouteProperties
from app.services.network_snapping import WithPointsRegistry


EDGES_SQL = "SELECT id, source, target, cost, reverse_cost FROM routing_edges"


class RouteNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class PathChoice:
    start_vid: int
    end_vid: int
    cost: float


WITH_POINTS_COST_SQL = """
SELECT start_pid, end_pid, agg_cost
FROM pgr_withPointsCost(
    :edges_sql,
    :points_sql,
    CAST(:start_vids AS bigint[]),
    CAST(:end_vids AS bigint[]),
    directed => true,
    driving_side => 'b'
)
WHERE agg_cost < 'Infinity'::double precision
ORDER BY agg_cost, start_pid, end_pid
"""

WITH_POINTS_PATH_SQL = """
SELECT path_seq, node, edge, cost, agg_cost
FROM pgr_withPoints(
    :edges_sql,
    :points_sql,
    CAST(:start_vid AS bigint),
    CAST(:end_vid AS bigint),
    directed => true,
    driving_side => 'b',
    details => true
)
ORDER BY path_seq
"""

MATERIALIZE_SEGMENTS_SQL = """
WITH steps AS (
    SELECT *
    FROM jsonb_to_recordset(CAST(:steps_json AS jsonb)) AS item(
        path_seq integer,
        edge_id bigint,
        from_fraction double precision,
        to_fraction double precision,
        cost double precision
    )
),
segments AS (
    SELECT s.path_seq,
           s.edge_id,
           e.source,
           e.target,
           s.cost,
           ST_LineSubstring(e.geometry, s.from_fraction, s.to_fraction) AS geometry
    FROM steps AS s
    JOIN routing_edges AS e ON e.id = s.edge_id
)
SELECT path_seq,
       edge_id AS edge,
       source,
       target,
       cost,
       ST_Length(geometry::geography) AS length_m,
       ST_AsGeoJSON(geometry, 15)::json AS geometry
FROM segments
ORDER BY path_seq
"""


def with_points_costs(
    db: Session,
    *,
    registry: WithPointsRegistry,
    start_vids: list[int],
    end_vids: list[int],
) -> list[PathChoice]:
    choices: dict[tuple[int, int], PathChoice] = {}
    for vid in sorted(set(start_vids).intersection(end_vids)):
        choices[(vid, vid)] = PathChoice(vid, vid, 0.0)
    rows = db.execute(
        text(WITH_POINTS_COST_SQL),
        {
            "edges_sql": EDGES_SQL,
            "points_sql": registry.points_sql,
            "start_vids": sorted(set(start_vids)),
            "end_vids": sorted(set(end_vids)),
        },
    ).mappings()
    for row in rows:
        choice = PathChoice(
            start_vid=int(row["start_pid"]),
            end_vid=int(row["end_pid"]),
            cost=float(row["agg_cost"]),
        )
        choices[(choice.start_vid, choice.end_vid)] = choice
    return sorted(
        choices.values(),
        key=lambda item: (item.cost, item.start_vid, item.end_vid),
    )


def best_path_choice(
    db: Session,
    *,
    registry: WithPointsRegistry,
    start_vids: list[int],
    end_vids: list[int],
) -> PathChoice:
    choices = with_points_costs(
        db,
        registry=registry,
        start_vids=start_vids,
        end_vids=end_vids,
    )
    if not choices:
        raise RouteNotFoundError("No routable path between snapped points")
    return choices[0]


def _node_fraction(
    *,
    vid: int,
    edge: dict[str, Any],
    registry: WithPointsRegistry,
) -> float:
    if vid < 0:
        candidate = registry.candidate_for_vid(vid)
        if candidate.edge_id != int(edge["id"]):
            raise RuntimeError("pgRouting point is attached to an unexpected edge")
        if candidate.fraction is None:
            raise RuntimeError("pgRouting point has no edge fraction")
        return candidate.fraction
    if vid == int(edge["source"]):
        return 0.0
    if vid == int(edge["target"]):
        return 1.0
    raise RuntimeError("pgRouting path node is not an endpoint of its directed edge")


def _path_steps(
    db: Session,
    *,
    registry: WithPointsRegistry,
    choice: PathChoice,
) -> list[dict[str, Any]]:
    if choice.start_vid == choice.end_vid:
        return []
    route_rows = [
        dict(row)
        for row in db.execute(
            text(WITH_POINTS_PATH_SQL),
            {
                "edges_sql": EDGES_SQL,
                "points_sql": registry.points_sql,
                "start_vid": choice.start_vid,
                "end_vid": choice.end_vid,
            },
        ).mappings()
    ]
    traversals = [row for row in route_rows if int(row["edge"]) != -1]
    if not traversals:
        raise RouteNotFoundError("No routable path between snapped points")
    edge_ids = sorted({int(row["edge"]) for row in traversals})
    edge_rows = db.execute(
        text(
            "SELECT id,source,target FROM routing_edges "
            "WHERE id=ANY(CAST(:edge_ids AS bigint[]))"
        ),
        {"edge_ids": edge_ids},
    ).mappings()
    edges = {int(row["id"]): dict(row) for row in edge_rows}

    steps: list[dict[str, Any]] = []
    for index, row in enumerate(route_rows[:-1]):
        edge_id = int(row["edge"])
        if edge_id == -1:
            continue
        edge = edges[edge_id]
        from_fraction = _node_fraction(
            vid=int(row["node"]), edge=edge, registry=registry
        )
        to_fraction = _node_fraction(
            vid=int(route_rows[index + 1]["node"]), edge=edge, registry=registry
        )
        if to_fraction + 1e-12 < from_fraction:
            raise RuntimeError("pgRouting traversed a directed edge against its geometry")
        if math.isclose(from_fraction, to_fraction, abs_tol=1e-12):
            if not math.isclose(float(row["cost"]), 0.0, abs_tol=1e-9):
                raise RuntimeError("Non-zero route cost was returned for a zero-length segment")
            continue
        steps.append(
            {
                "path_seq": len(steps) + 1,
                "edge_id": edge_id,
                "from_fraction": from_fraction,
                "to_fraction": to_fraction,
                "cost": float(row["cost"]),
            }
        )
    return steps


def _coordinates(rows: list[dict[str, Any]]) -> list[list[float]]:
    coordinates: list[list[float]] = []
    for row in rows:
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        segment = [[float(value) for value in pair] for pair in geometry["coordinates"]]
        if coordinates:
            if not (
                math.isclose(coordinates[-1][0], segment[0][0], abs_tol=1e-10)
                and math.isclose(coordinates[-1][1], segment[0][1], abs_tol=1e-10)
            ):
                raise RuntimeError("Route edge geometries are not endpoint-continuous")
            coordinates.extend(segment[1:])
        else:
            coordinates.extend(segment)
    return coordinates


def route_feature_for_choice(
    db: Session,
    *,
    registry: WithPointsRegistry,
    choice: PathChoice,
    zero_coordinate: tuple[float, float] | None = None,
) -> RouteFeature:
    steps = _path_steps(db, registry=registry, choice=choice)
    if not steps:
        if zero_coordinate is None:
            raise RouteNotFoundError("No routable path between snapped points")
        return RouteFeature(
            geometry={
                "type": "LineString",
                "coordinates": [list(zero_coordinate), list(zero_coordinate)],
            },
            properties=RouteProperties(
                routing_distance_m=0.0,
                travel_time_s=0.0,
                travel_time_min=0.0,
                edge_count=0,
                edge_ids=[],
            ),
        )
    rows = [
        dict(row)
        for row in db.execute(
            text(MATERIALIZE_SEGMENTS_SQL),
            {"steps_json": json.dumps(steps)},
        ).mappings()
    ]
    coordinates = _coordinates(rows)
    distance = sum(float(row["length_m"]) for row in rows)
    travel_time = sum(float(row["cost"]) for row in rows)
    if not math.isclose(travel_time, choice.cost, abs_tol=1e-6):
        raise RuntimeError("Detailed withPoints path cost does not match selected cost")
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
