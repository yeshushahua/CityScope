from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.layers import BBox, query_buildings, query_pois

router = APIRouter(prefix="/api/v1/layers", tags=["layers"])
MAX_BUILDING_BBOX_AREA = 0.01


def parse_bbox(value: str) -> BBox:
    try:
        coordinates = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bbox must contain four numbers") from exc
    if len(coordinates) != 4:
        raise HTTPException(status_code=422, detail="bbox must be west,south,east,north")
    west, south, east, north = coordinates
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(status_code=422, detail="bbox coordinates or ordering are invalid")
    return west, south, east, north


@router.get("/pois", response_model=GeoJSONFeatureCollection)
def pois(
    bbox: str | None = Query(default=None),
    category: str | None = Query(default=None, max_length=40),
    subcategory: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=1500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> GeoJSONFeatureCollection:
    return query_pois(
        db,
        bbox=parse_bbox(bbox) if bbox else None,
        category=category,
        subcategory=subcategory,
        limit=limit,
    )


@router.get("/buildings", response_model=GeoJSONFeatureCollection)
def buildings(
    bbox: str = Query(...),
    limit: int = Query(default=3000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> GeoJSONFeatureCollection:
    parsed_bbox = parse_bbox(bbox)
    west, south, east, north = parsed_bbox
    if (east - west) * (north - south) > MAX_BUILDING_BBOX_AREA:
        raise HTTPException(
            status_code=422,
            detail="bbox is too large for building retrieval; zoom in and try again",
        )
    return query_buildings(db, bbox=parsed_bbox, limit=limit)
