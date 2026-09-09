-- Phase 9: OSM-derived building height metadata for MapLibre 2.5D display.
ALTER TABLE buildings
    ADD COLUMN IF NOT EXISTS osm_height_m double precision,
    ADD COLUMN IF NOT EXISTS building_levels double precision,
    ADD COLUMN IF NOT EXISTS display_height_m double precision,
    ADD COLUMN IF NOT EXISTS height_source varchar(24) NOT NULL DEFAULT 'unknown';

ALTER TABLE buildings DROP CONSTRAINT IF EXISTS ck_buildings_osm_height_positive;
ALTER TABLE buildings ADD CONSTRAINT ck_buildings_osm_height_positive
    CHECK (osm_height_m IS NULL OR osm_height_m > 0);

ALTER TABLE buildings DROP CONSTRAINT IF EXISTS ck_buildings_levels_positive;
ALTER TABLE buildings ADD CONSTRAINT ck_buildings_levels_positive
    CHECK (building_levels IS NULL OR building_levels > 0);

ALTER TABLE buildings DROP CONSTRAINT IF EXISTS ck_buildings_display_height_positive;
ALTER TABLE buildings ADD CONSTRAINT ck_buildings_display_height_positive
    CHECK (display_height_m IS NULL OR display_height_m > 0);

ALTER TABLE buildings DROP CONSTRAINT IF EXISTS ck_buildings_height_source;
ALTER TABLE buildings ADD CONSTRAINT ck_buildings_height_source
    CHECK (height_source IN ('osm_height', 'levels_estimate', 'unknown'));

CREATE INDEX IF NOT EXISTS ix_buildings_height_source ON buildings (height_source);
