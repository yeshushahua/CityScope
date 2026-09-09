-- Phase 8: independent OSM pedestrian graph and POI walking access.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

CREATE TABLE IF NOT EXISTS pedestrian_nodes (
    osm_node_id bigint PRIMARY KEY,
    geometry geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pedestrian_nodes_geometry
ON pedestrian_nodes USING gist (geometry);

CREATE INDEX IF NOT EXISTS idx_pedestrian_nodes_geography
ON pedestrian_nodes USING gist ((geometry::geography));

CREATE TABLE IF NOT EXISTS pedestrian_edges (
    id bigint PRIMARY KEY,
    osm_id text NOT NULL,
    source bigint NOT NULL REFERENCES pedestrian_nodes(osm_node_id),
    target bigint NOT NULL REFERENCES pedestrian_nodes(osm_node_id),
    u bigint NOT NULL,
    v bigint NOT NULL,
    edge_key integer NOT NULL,
    highway text,
    name text,
    length_m double precision NOT NULL CHECK (length_m > 0),
    walk_speed_kph double precision NOT NULL CHECK (walk_speed_kph > 0),
    travel_time_s double precision NOT NULL CHECK (travel_time_s > 0),
    cost double precision NOT NULL CHECK (cost > 0),
    reverse_cost double precision NOT NULL DEFAULT -1 CHECK (reverse_cost = -1),
    geometry geometry(LineString, 4326) NOT NULL,
    CONSTRAINT uq_pedestrian_edges_uvkey UNIQUE (u, v, edge_key),
    CONSTRAINT ck_pedestrian_edges_source_u CHECK (source = u),
    CONSTRAINT ck_pedestrian_edges_target_v CHECK (target = v)
);

CREATE INDEX IF NOT EXISTS ix_pedestrian_edges_source ON pedestrian_edges (source);
CREATE INDEX IF NOT EXISTS ix_pedestrian_edges_target ON pedestrian_edges (target);
CREATE INDEX IF NOT EXISTS ix_pedestrian_edges_highway ON pedestrian_edges (highway);
CREATE INDEX IF NOT EXISTS idx_pedestrian_edges_geometry
ON pedestrian_edges USING gist (geometry);

CREATE TABLE IF NOT EXISTS poi_walk_access (
    poi_id bigint PRIMARY KEY REFERENCES pois(id) ON DELETE CASCADE,
    node_id bigint NOT NULL REFERENCES pedestrian_nodes(osm_node_id),
    snap_distance_m double precision NOT NULL
        CHECK (snap_distance_m >= 0 AND snap_distance_m <= 300),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_poi_walk_access_node_id ON poi_walk_access (node_id);
CREATE INDEX IF NOT EXISTS ix_poi_walk_access_snap_distance ON poi_walk_access (snap_distance_m);
