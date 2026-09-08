import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.geojson import GeoJSONFeature, GeoJSONFeatureCollection
from app.schemas.network import NetworkStats
from app.services.layers import BBox


def _geometry(value: dict[str, Any] | str) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


def query_network_edges(
    db: Session,
    *,
    bbox: BBox,
    highway: str | None,
    limit: int,
) -> GeoJSONFeatureCollection:
    params: dict[str, Any] = dict(
        zip(("west", "south", "east", "north"), bbox, strict=True)
    )
    params["limit"] = limit
    filters = [
        "geometry && ST_MakeEnvelope(:west, :south, :east, :north, 4326)",
        "ST_Intersects(geometry, ST_MakeEnvelope(:west, :south, :east, :north, 4326))",
    ]
    if highway:
        filters.append(":highway = ANY(regexp_split_to_array(highway, '\\s*;\\s*'))")
        params["highway"] = highway
    rows = db.execute(
        text(
            f"""
            SELECT id, road_edge_id, source, target, osm_id, edge_key, name,
                   highway, oneway, maxspeed, speed_kph, speed_source,
                   length_m, travel_time_s, cost, reverse_cost,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM routing_edges
            WHERE {' AND '.join(filters)}
            ORDER BY id
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return GeoJSONFeatureCollection(
        features=[
            GeoJSONFeature(
                geometry=_geometry(row["geometry"]),
                properties={
                    "id": row["id"],
                    "road_edge_id": row["road_edge_id"],
                    "source": row["source"],
                    "target": row["target"],
                    "osm_id": row["osm_id"],
                    "edge_key": row["edge_key"],
                    "name": row["name"],
                    "highway": row["highway"],
                    "oneway": row["oneway"],
                    "maxspeed": row["maxspeed"],
                    "speed_kph": round(float(row["speed_kph"]), 1),
                    "speed_source": row["speed_source"],
                    "length_m": round(float(row["length_m"]), 1),
                    "travel_time_s": round(float(row["travel_time_s"]), 1),
                    "cost": round(float(row["cost"]), 1),
                    "reverse_cost": round(float(row["reverse_cost"]), 1),
                    "source_dataset": "OpenStreetMap / OSMnx",
                },
            )
            for row in rows
        ]
    )


def network_stats(db: Session) -> NetworkStats:
    base = db.execute(
        text(
            """
            SELECT COUNT(*)::bigint AS edges,
                   COUNT(*) FILTER (WHERE oneway)::bigint AS oneway_edges,
                   COUNT(*) FILTER (WHERE NOT oneway)::bigint AS bidirectional_edges,
                   COALESCE(SUM(length_m), 0) / 1000.0 AS length_km,
                   COALESCE(AVG(speed_kph), 0) AS avg_speed_kph
            FROM routing_edges
            """
        )
    ).mappings().one()
    node_count = int(db.scalar(text("SELECT COUNT(*) FROM road_nodes")) or 0)
    component_rows = list(
        db.execute(
            text(
                """
                SELECT component, COUNT(*)::bigint AS node_count
                FROM pgr_connectedComponents(
                    'SELECT id, source, target, cost, reverse_cost FROM routing_edges'
                )
                GROUP BY component
                ORDER BY node_count DESC, component
                """
            )
        ).mappings()
    )
    strong_components = int(
        db.scalar(
            text(
                """
                SELECT COUNT(DISTINCT component)
                FROM pgr_strongComponents(
                    'SELECT id, source, target, cost, reverse_cost FROM routing_edges'
                )
                """
            )
        )
        or 0
    )
    isolated_nodes = int(
        db.scalar(
            text(
                """
                SELECT COUNT(*) FROM road_nodes n
                WHERE NOT EXISTS (
                    SELECT 1 FROM routing_edges e
                    WHERE e.source = n.osm_node_id OR e.target = n.osm_node_id
                )
                """
            )
        )
        or 0
    )
    degree_one_nodes = int(
        db.scalar(
            text(
                """
                WITH neighbors AS (
                    SELECT source AS node, target AS neighbor FROM routing_edges
                    UNION
                    SELECT target AS node, source AS neighbor FROM routing_edges
                ), degrees AS (
                    SELECT node, COUNT(*) AS degree FROM neighbors GROUP BY node
                )
                SELECT COUNT(*) FROM degrees WHERE degree = 1
                """
            )
        )
        or 0
    )
    highway_counts = {
        str(row["highway"] or "unknown"): int(row["count"])
        for row in db.execute(
            text(
                "SELECT highway, COUNT(*)::bigint AS count "
                "FROM routing_edges GROUP BY highway ORDER BY count DESC, highway"
            )
        ).mappings()
    }
    speed_sources = {
        str(row["speed_source"]): int(row["count"])
        for row in db.execute(
            text(
                "SELECT speed_source, COUNT(*)::bigint AS count "
                "FROM routing_edges GROUP BY speed_source ORDER BY speed_source"
            )
        ).mappings()
    }
    largest = int(component_rows[0]["node_count"]) if component_rows else 0
    return NetworkStats(
        nodes=node_count,
        edges=int(base["edges"]),
        oneway_edges=int(base["oneway_edges"]),
        bidirectional_edges=int(base["bidirectional_edges"]),
        length_km=round(float(base["length_km"]), 2),
        avg_speed_kph=round(float(base["avg_speed_kph"]), 2),
        weak_components=len(component_rows),
        strong_components=strong_components,
        largest_component_nodes=largest,
        largest_component_ratio=round(largest / node_count if node_count else 0, 6),
        isolated_nodes=isolated_nodes,
        degree_one_nodes=degree_one_nodes,
        highway_counts=highway_counts,
        speed_source_counts=speed_sources,
    )
