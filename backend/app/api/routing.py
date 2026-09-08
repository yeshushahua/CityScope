from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.routing import (
    FacilityCategory,
    FacilitySubcategory,
    IsochroneResponse,
    NearestFacilityResponse,
    RoutePoint,
    ShortestPathRequest,
    ShortestPathResponse,
)
from app.services.routing import (
    FacilityNotFoundError,
    ReachableFacilityNotFoundError,
    RouteNotFoundError,
    SnapNotFoundError,
    IsochroneGeometryError,
    isochrone,
    nearest_facility,
    shortest_path,
)

router = APIRouter(prefix="/api/v1/routing", tags=["routing"])
SUBCATEGORY_CATEGORY = {
    "hospital": "healthcare",
    "clinic": "healthcare",
    "doctors": "healthcare",
    "fire_station": "emergency",
}


@router.post("/shortest-path", response_model=ShortestPathResponse)
def get_shortest_path(
    request: ShortestPathRequest, db: Session = Depends(get_db)
) -> ShortestPathResponse:
    try:
        return shortest_path(
            db,
            start=request.start,
            end=request.end,
            max_snap_m=request.max_snap_m,
        )
    except SnapNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RouteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Routing query failed") from exc


@router.get("/nearest-facility", response_model=NearestFacilityResponse)
def get_nearest_facility(
    lon: float = Query(..., ge=103, le=105),
    lat: float = Query(..., ge=35, le=37),
    category: FacilityCategory = Query(...),
    subcategory: FacilitySubcategory | None = Query(default=None),
    max_snap_m: int = Query(default=500, ge=100, le=1000),
    limit: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db),
) -> NearestFacilityResponse:
    if subcategory and SUBCATEGORY_CATEGORY[subcategory] != category:
        raise HTTPException(
            status_code=422,
            detail="subcategory does not belong to the requested category",
        )
    try:
        return nearest_facility(
            db,
            origin=RoutePoint(lon=lon, lat=lat),
            category=category,
            subcategory=subcategory,
            max_snap_m=max_snap_m,
            limit=limit,
        )
    except SnapNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FacilityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReachableFacilityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SQLAlchemyError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Nearest facility query failed") from exc


@router.get("/isochrone", response_model=IsochroneResponse)
def get_isochrone(
    lon: float = Query(..., ge=103, le=105),
    lat: float = Query(..., ge=35, le=37),
    max_snap_m: int = Query(default=500, ge=100, le=1000),
    db: Session = Depends(get_db),
) -> IsochroneResponse:
    try:
        return isochrone(
            db,
            origin=RoutePoint(lon=lon, lat=lat),
            max_snap_m=max_snap_m,
        )
    except SnapNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SQLAlchemyError, IsochroneGeometryError) as exc:
        raise HTTPException(status_code=503, detail="Isochrone query failed") from exc
