from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "osm"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim" / "osm"
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"

# (west, south, east, north), EPSG:4326. This is the continuous urban demo area,
# not the complete administrative extent of Lanzhou.
DEMO_BBOX = (103.60, 35.98, 104.08, 36.16)
SOURCE_CRS = "EPSG:4326"
AREA_CRS = "EPSG:32648"

GRID_COLUMNS = 3
GRID_ROWS = 2
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.nchc.org.tw/api",
)
OVERPASS_TIMEOUT_SECONDS = 240
MAX_DOWNLOAD_ATTEMPTS = 3

POI_TAGS: dict[str, bool | str | list[str]] = {
    "amenity": [
        "hospital",
        "clinic",
        "doctors",
        "fire_station",
        "school",
        "college",
        "university",
        "kindergarten",
        "police",
        "marketplace",
    ],
    "leisure": "park",
    "highway": "bus_stop",
    "railway": ["station", "subway_entrance"],
    "public_transport": True,
    "shop": ["supermarket", "mall"],
}

SOURCE_TAG_COLUMNS = (
    "name",
    "name:zh",
    "amenity",
    "leisure",
    "highway",
    "railway",
    "public_transport",
    "shop",
    "building",
)
