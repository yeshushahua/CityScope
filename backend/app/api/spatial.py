from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.spatial import (
    NearbyPoiCollection,
    PoiCategory,
    PoiSubcategory,
    SpatialSummary,
)
from app.services.spatial import nearby_pois, spatial_summary

router = APIRouter(prefix="/api/v1/spatial", tags=["spatial"])

SUBCATEGORY_CATEGORY: dict[str, str] = {
    "hospital": "healthcare",
    "clinic": "healthcare",
    "doctors": "healthcare",
    "fire_station": "emergency",
    "school": "education",
    "college": "education",
    "university": "education",
    "kindergarten": "education",
    "police": "public_safety",
    "park": "recreation",
    "bus_stop": "transport",
    "station": "transport",
    "subway_entrance": "transport",
    "platform": "transport",
    "stop_position": "transport",
    "supermarket": "commercial",
    "mall": "commercial",
    "marketplace": "commercial",
}


def _validate_filter_pair(category: str | None, subcategory: str | None) -> None:
    if category and subcategory and SUBCATEGORY_CATEGORY[subcategory] != category:
        raise HTTPException(
            status_code=422,
            detail="subcategory does not belong to the requested category",
        )


@router.get("/nearby-pois", response_model=NearbyPoiCollection)
def get_nearby_pois(
    lon: float = Query(..., ge=103, le=105),
    lat: float = Query(..., ge=35, le=37),
    radius_m: int = Query(default=1000, ge=100, le=10000),
    category: PoiCategory | None = Query(default=None),
    subcategory: PoiSubcategory | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> NearbyPoiCollection:
    _validate_filter_pair(category, subcategory)
    try:
        return nearby_pois(
            db,
            lon=lon,
            lat=lat,
            radius_m=radius_m,
            category=category,
            subcategory=subcategory,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="PostGIS query failed") from exc


@router.get("/summary", response_model=SpatialSummary)
def get_spatial_summary(
    lon: float = Query(..., ge=103, le=105),
    lat: float = Query(..., ge=35, le=37),
    radius_m: int = Query(default=1000, ge=100, le=10000),
    db: Session = Depends(get_db),
) -> SpatialSummary:
    try:
        return spatial_summary(db, lon=lon, lat=lat, radius_m=radius_m)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="PostGIS query failed") from exc
