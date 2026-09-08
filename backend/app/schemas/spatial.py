from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.geojson import GeoJSONFeature

PoiCategory = Literal[
    "healthcare",
    "emergency",
    "education",
    "public_safety",
    "recreation",
    "transport",
    "commercial",
]
PoiSubcategory = Literal[
    "hospital",
    "clinic",
    "doctors",
    "fire_station",
    "school",
    "college",
    "university",
    "kindergarten",
    "police",
    "park",
    "bus_stop",
    "station",
    "subway_entrance",
    "platform",
    "stop_position",
    "supermarket",
    "mall",
    "marketplace",
]


class NearbyMeta(BaseModel):
    center: tuple[float, float]
    radius_m: int
    count: int


class NearbyPoiCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature] = Field(default_factory=list)
    meta: NearbyMeta


class QueryCenter(BaseModel):
    lon: float
    lat: float


class PoiSummary(BaseModel):
    total: int
    by_category: dict[str, int]


class BuildingSummary(BaseModel):
    count: int
    footprint_area_m2: float


class SpatialSummary(BaseModel):
    center: QueryCenter
    radius_m: int
    pois: PoiSummary
    buildings: BuildingSummary
