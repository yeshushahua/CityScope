-- Phase 4: reproducible pgRouting-ready schema. The OSM ETL populates this
-- table deterministically and uses --replace to prevent duplicate rows.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

ALTER TABLE road_edges ADD COLUMN IF NOT EXISTS maxspeed text;

CREATE TABLE IF NOT EXISTS routing_edges (
    id bigint PRIMARY KEY,
    road_edge_id bigint NOT NULL UNIQUE REFERENCES road_edges(id) ON DELETE CASCADE,
    source bigint NOT NULL REFERENCES road_nodes(osm_node_id),
    target bigint NOT NULL REFERENCES road_nodes(osm_node_id),
    osm_id text NOT NULL,
    edge_key integer NOT NULL,
    name text,
    highway text,
    oneway boolean NOT NULL,
    maxspeed text,
    speed_kph double precision NOT NULL CHECK (speed_kph > 0),
    speed_source varchar(16) NOT NULL CHECK (speed_source IN ('osm', 'default')),
    length_m double precision NOT NULL CHECK (length_m > 0),
    travel_time_s double precision NOT NULL CHECK (travel_time_s > 0),
    cost double precision NOT NULL CHECK (cost > 0),
    reverse_cost double precision NOT NULL,
    geometry geometry(LineString, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_routing_edges_source ON routing_edges (source);
CREATE INDEX IF NOT EXISTS ix_routing_edges_target ON routing_edges (target);
CREATE INDEX IF NOT EXISTS ix_routing_edges_highway ON routing_edges (highway);
CREATE INDEX IF NOT EXISTS idx_routing_edges_geometry ON routing_edges USING gist (geometry);
