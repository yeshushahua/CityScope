from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.layers import parse_bbox
from app.db.session import get_db
from app.schemas.geojson import GeoJSONFeatureCollection
from app.schemas.network import NetworkStats
from app.services.network import network_stats, query_network_edges

router = APIRouter(prefix="/api/v1/network", tags=["network"])
MAX_NETWORK_BBOX_AREA = 0.01


@router.get("/edges", response_model=GeoJSONFeatureCollection)
def edges(
    bbox: str = Query(...),
    highway: str | None = Query(default=None, min_length=1, max_length=40),
    limit: int = Query(default=2000, ge=1, le=3000),
    db: Session = Depends(get_db),
) -> GeoJSONFeatureCollection:
    parsed_bbox = parse_bbox(bbox)
    west, south, east, north = parsed_bbox
    if (east - west) * (north - south) > MAX_NETWORK_BBOX_AREA:
        raise HTTPException(
            status_code=422,
            detail="bbox is too large for road network retrieval; zoom in and try again",
        )
    try:
        return query_network_edges(db, bbox=parsed_bbox, highway=highway, limit=limit)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Road network query failed") from exc


@router.get("/stats", response_model=NetworkStats)
def stats(db: Session = Depends(get_db)) -> NetworkStats:
    try:
        return network_stats(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Road network statistics query failed") from exc
