"""Safely rebuild only the calibrated CityScope motor routing edge table."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from geoalchemy2 import Geometry
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import engine  # noqa: E402
from scripts.osm.config import RAW_DIR  # noqa: E402
from scripts.osm.preprocess_osm import build_routing_edges, clean_roads  # noqa: E402

RAW_GRAPH = RAW_DIR / "lanzhou_roads.graphml"


def _assert_source_edges_unchanged(connection, edges) -> None:
    actual = [
        tuple(row)
        for row in connection.execute(
            text(
                """
                SELECT id, u, v, edge_key, osm_id
                FROM road_edges
                ORDER BY id
                """
            )
        )
    ]
    expected = [
        (
            int(row.id),
            int(row.u),
            int(row.v),
            int(row.edge_key),
            str(row.osm_id),
        )
        for row in edges.sort_values("id").itertuples()
    ]
    if actual != expected:
        raise RuntimeError(
            "Cached motor graph does not match road_edges; run the reviewed full import workflow"
        )


def rebuild() -> dict[str, float | int]:
    if not RAW_GRAPH.exists():
        raise FileNotFoundError(f"Cached motor graph is missing: {RAW_GRAPH}")
    _, road_edges, _ = clean_roads(RAW_GRAPH)
    routing_edges = build_routing_edges(road_edges)

    with engine.begin() as connection:
        _assert_source_edges_unchanged(connection, road_edges)
        connection.execute(text("TRUNCATE TABLE routing_edges"))
        routing_edges.to_postgis(
            "routing_edges",
            connection,
            if_exists="append",
            index=False,
            chunksize=3000,
            dtype={"geometry": Geometry("LINESTRING", srid=4326)},
        )
        connection.execute(text("ANALYZE routing_edges"))
        result = dict(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS routing_edges,
                           COUNT(*) FILTER (WHERE highway = 'ladder')::int AS ladder_edges,
                           MIN(speed_kph)::float AS min_speed_kph,
                           percentile_cont(0.5) WITHIN GROUP (
                             ORDER BY speed_kph
                           )::float AS median_speed_kph,
                           AVG(speed_kph)::float AS mean_speed_kph,
                           percentile_cont(0.9) WITHIN GROUP (
                             ORDER BY speed_kph
                           )::float AS p90_speed_kph,
                           MAX(speed_kph)::float AS max_speed_kph,
                           COUNT(*) FILTER (
                             WHERE abs(travel_time_s - length_m / (speed_kph / 3.6)) > 1e-8
                                OR abs(cost - travel_time_s) > 1e-9
                                OR reverse_cost <> -1
                           )::int AS invalid_cost_edges
                    FROM routing_edges
                    """
                )
            ).mappings().one()
        )
    return result


if __name__ == "__main__":
    print(json.dumps(rebuild(), ensure_ascii=False, indent=2))
