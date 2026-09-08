CREATE INDEX IF NOT EXISTS idx_pois_geography
ON pois
USING GIST ((geometry::geography));

ANALYZE pois;
