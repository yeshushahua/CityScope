import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


EDGE_SNAP_SQL = """
WITH input_points AS (
    SELECT item.point_key,
           item.lon,
           item.lat,
           ST_SetSRID(ST_MakePoint(item.lon, item.lat), 4326) AS geometry,
           ST_Transform(
               ST_SetSRID(ST_MakePoint(item.lon, item.lat), 4326),
               32648
           ) AS geometry_utm
    FROM jsonb_to_recordset(CAST(:points_json AS jsonb))
         AS item(point_key text, lon double precision, lat double precision)
),
nearest AS (
    SELECT q.point_key,
           q.lon,
           q.lat,
           q.geometry AS query_geometry,
           q.geometry_utm AS query_geometry_utm,
           edge.id AS edge_id,
           edge.source,
           edge.target,
           edge.osm_id,
           edge.geometry AS edge_geometry,
           edge.length_m,
           edge.cost
    FROM input_points AS q
    JOIN LATERAL (
        SELECT e.*
        FROM routing_edges AS e
        WHERE e.source <> e.target
          AND e.geometry && ST_Transform(
              ST_Envelope(ST_Buffer(q.geometry_utm, :max_snap_m)),
              4326
          )
          AND ST_DWithin(
              e.geometry::geography,
              q.geometry::geography,
              :max_snap_m
          )
        ORDER BY ST_Distance(e.geometry::geography, q.geometry::geography), e.id
        LIMIT 1
    ) AS edge ON true
),
candidate_edges AS (
    SELECT n.*, 0 AS candidate_rank
    FROM nearest AS n
    UNION ALL
    SELECT n.point_key,
           n.lon,
           n.lat,
           n.query_geometry,
           n.query_geometry_utm,
           reverse_edge.id,
           reverse_edge.source,
           reverse_edge.target,
           reverse_edge.osm_id,
           reverse_edge.geometry,
           reverse_edge.length_m,
           reverse_edge.cost,
           1 AS candidate_rank
    FROM nearest AS n
    JOIN LATERAL (
        SELECT r.*
        FROM routing_edges AS r
        WHERE r.id <> n.edge_id
          AND r.source = n.target
          AND r.target = n.source
          AND r.osm_id = n.osm_id
          AND r.source <> r.target
          AND ST_HausdorffDistance(
              ST_Transform(r.geometry, 32648),
              ST_Transform(n.edge_geometry, 32648)
          ) <= :reverse_geometry_tolerance_m
        ORDER BY ST_HausdorffDistance(
                     ST_Transform(r.geometry, 32648),
                     ST_Transform(n.edge_geometry, 32648)
                 ),
                 r.id
        LIMIT 1
    ) AS reverse_edge ON true
),
metric_edges AS (
    SELECT c.*,
           ST_Transform(
               ST_Segmentize(c.edge_geometry::geography, 20)::geometry,
               32648
           ) AS edge_geometry_utm
    FROM candidate_edges AS c
),
metric_projected AS (
    SELECT m.*,
           ST_Transform(
               ST_LineInterpolatePoint(
                   m.edge_geometry_utm,
                   ST_LineLocatePoint(m.edge_geometry_utm, m.query_geometry_utm)
               ),
               4326
           ) AS metric_snapped_geometry
    FROM metric_edges AS m
),
located AS (
    SELECT m.*,
           ST_LineLocatePoint(m.edge_geometry, m.metric_snapped_geometry)
               AS raw_fraction
    FROM metric_projected AS m
),
projected AS (
    SELECT l.*,
           ST_LineInterpolatePoint(l.edge_geometry, l.raw_fraction)
               AS snapped_geometry,
           l.length_m * l.raw_fraction AS distance_to_source_m,
           l.length_m * (1 - l.raw_fraction) AS distance_to_target_m
    FROM located AS l
)
SELECT point_key,
       edge_id,
       source,
       target,
       CASE
           WHEN distance_to_source_m <= :vertex_tolerance_m THEN 0.0
           WHEN distance_to_target_m <= :vertex_tolerance_m THEN 1.0
           ELSE raw_fraction
       END AS fraction,
       CASE
           WHEN distance_to_source_m <= :vertex_tolerance_m THEN source
           WHEN distance_to_target_m <= :vertex_tolerance_m THEN target
           ELSE NULL
       END AS node_id,
       CASE
           WHEN distance_to_source_m <= :vertex_tolerance_m
               THEN ST_X(ST_StartPoint(edge_geometry))
           WHEN distance_to_target_m <= :vertex_tolerance_m
               THEN ST_X(ST_EndPoint(edge_geometry))
           ELSE ST_X(snapped_geometry)
       END AS snapped_lon,
       CASE
           WHEN distance_to_source_m <= :vertex_tolerance_m
               THEN ST_Y(ST_StartPoint(edge_geometry))
           WHEN distance_to_target_m <= :vertex_tolerance_m
               THEN ST_Y(ST_EndPoint(edge_geometry))
           ELSE ST_Y(snapped_geometry)
       END AS snapped_lat,
       ST_Distance(query_geometry::geography, snapped_geometry::geography)
           AS snap_distance_m,
       candidate_rank
FROM projected
ORDER BY point_key, candidate_rank, edge_id
"""

VERTEX_TOLERANCE_M = 1.0
REVERSE_GEOMETRY_TOLERANCE_M = 1.0


class SnapNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class EdgeSnapCandidate:
    edge_id: int | None
    source: int | None
    target: int | None
    fraction: float | None
    snapped_lon: float
    snapped_lat: float
    snap_distance_m: float
    node_id: int | None = None


@dataclass(frozen=True)
class EdgeSnapLocation:
    point_key: str
    lon: float
    lat: float
    candidates: tuple[EdgeSnapCandidate, ...]

    @property
    def primary(self) -> EdgeSnapCandidate:
        return self.candidates[0]


@dataclass(frozen=True)
class RegisteredLocation:
    snap: EdgeSnapLocation
    candidates_by_vid: tuple[tuple[int, EdgeSnapCandidate], ...]

    @property
    def vids(self) -> list[int]:
        return [vid for vid, _ in self.candidates_by_vid]

    def candidate_for_vid(self, vid: int) -> EdgeSnapCandidate:
        for candidate_vid, candidate in self.candidates_by_vid:
            if candidate_vid == vid:
                return candidate
        raise KeyError(f"Vertex {vid} does not belong to {self.snap.point_key}")


class WithPointsRegistry:
    """Assign deterministic request-local pgRouting point identifiers."""

    def __init__(self) -> None:
        self._next_pid = 1
        self._point_by_key: dict[tuple[int, int], tuple[int, EdgeSnapCandidate]] = {}
        self._point_by_pid: dict[int, EdgeSnapCandidate] = {}

    def register(self, snap: EdgeSnapLocation) -> RegisteredLocation:
        registered: list[tuple[int, EdgeSnapCandidate]] = []
        seen_vids: set[int] = set()
        for candidate in snap.candidates:
            if candidate.node_id is not None:
                vid = candidate.node_id
            else:
                if candidate.edge_id is None or candidate.fraction is None:
                    raise ValueError("Virtual edge candidate is incomplete")
                key = (candidate.edge_id, round(candidate.fraction * 10**12))
                existing = self._point_by_key.get(key)
                if existing is None:
                    pid = self._next_pid
                    self._next_pid += 1
                    existing = (pid, candidate)
                    self._point_by_key[key] = existing
                    self._point_by_pid[pid] = candidate
                vid = -existing[0]
            if vid not in seen_vids:
                registered.append((vid, candidate))
                seen_vids.add(vid)
        return RegisteredLocation(snap=snap, candidates_by_vid=tuple(registered))

    def candidate_for_vid(self, vid: int) -> EdgeSnapCandidate:
        if vid >= 0:
            raise KeyError(f"{vid} is a real graph vertex, not a withPoints PID")
        return self._point_by_pid[-vid]

    @property
    def points_sql(self) -> str:
        if not self._point_by_pid:
            return (
                "SELECT NULL::bigint AS pid, NULL::bigint AS edge_id, "
                "NULL::float8 AS fraction, NULL::char AS side WHERE false"
            )
        values = ",".join(
            f"({pid}::bigint,{candidate.edge_id}::bigint,"
            f"{candidate.fraction:.17g}::float8,'b'::char)"
            for pid, candidate in sorted(self._point_by_pid.items())
        )
        return (
            f"SELECT * FROM (VALUES {values}) "
            "AS points(pid,edge_id,fraction,side)"
        )


def snap_points_to_edges(
    db: Session,
    *,
    points: list[tuple[str, float, float]],
    max_snap_m: int,
    require_all: bool = True,
) -> dict[str, EdgeSnapLocation]:
    if not points:
        return {}
    point_payload = [
        {"point_key": point_key, "lon": lon, "lat": lat}
        for point_key, lon, lat in points
    ]
    rows = db.execute(
        text(EDGE_SNAP_SQL),
        {
            "points_json": json.dumps(point_payload),
            "max_snap_m": max_snap_m,
            "vertex_tolerance_m": VERTEX_TOLERANCE_M,
            "reverse_geometry_tolerance_m": REVERSE_GEOMETRY_TOLERANCE_M,
        },
    ).mappings()
    grouped: dict[str, list[EdgeSnapCandidate]] = {}
    for row in rows:
        grouped.setdefault(str(row["point_key"]), []).append(
            EdgeSnapCandidate(
                edge_id=int(row["edge_id"]),
                source=int(row["source"]),
                target=int(row["target"]),
                fraction=float(row["fraction"]),
                node_id=int(row["node_id"]) if row["node_id"] is not None else None,
                snapped_lon=float(row["snapped_lon"]),
                snapped_lat=float(row["snapped_lat"]),
                snap_distance_m=float(row["snap_distance_m"]),
            )
        )

    if require_all:
        missing = next((key for key, _, _ in points if key not in grouped), None)
        if missing is not None:
            raise SnapNotFoundError(
                f"No road network edge found within {max_snap_m} meters"
            )

    coordinates = {key: (lon, lat) for key, lon, lat in points}
    return {
        key: EdgeSnapLocation(
            point_key=key,
            lon=coordinates[key][0],
            lat=coordinates[key][1],
            candidates=tuple(candidates),
        )
        for key, candidates in grouped.items()
    }


def snap_point_to_edge(
    db: Session,
    *,
    lon: float,
    lat: float,
    max_snap_m: int,
    point_key: str = "point",
) -> EdgeSnapLocation:
    return snap_points_to_edges(
        db,
        points=[(point_key, lon, lat)],
        max_snap_m=max_snap_m,
    )[point_key]


def vertex_location(
    *,
    point_key: str,
    lon: float,
    lat: float,
    node_id: int,
    snapped_lon: float,
    snapped_lat: float,
    snap_distance_m: float,
) -> EdgeSnapLocation:
    return EdgeSnapLocation(
        point_key=point_key,
        lon=lon,
        lat=lat,
        candidates=(
            EdgeSnapCandidate(
                edge_id=None,
                source=None,
                target=None,
                fraction=None,
                node_id=node_id,
                snapped_lon=snapped_lon,
                snapped_lat=snapped_lat,
                snap_distance_m=snap_distance_m,
            ),
        ),
    )
