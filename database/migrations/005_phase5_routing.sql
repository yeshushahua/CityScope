-- Phase 5: indexed vertex snapping and deterministic POI network access.
CREATE INDEX IF NOT EXISTS idx_road_nodes_geography
ON road_nodes USING gist ((geometry::geography));

CREATE TABLE IF NOT EXISTS poi_routing_access (
    poi_id bigint PRIMARY KEY REFERENCES pois(id) ON DELETE CASCADE,
    node_id bigint NOT NULL REFERENCES road_nodes(osm_node_id),
    snap_distance_m double precision NOT NULL
        CHECK (snap_distance_m >= 0 AND snap_distance_m <= 500),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_poi_routing_access_node_id
ON poi_routing_access (node_id);
