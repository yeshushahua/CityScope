from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.routing import (
    AmapNavigationEstimate,
    CityScopeRouteEstimate,
    FacilityCategory,
    FacilitySubcategory,
    IsochroneResponse,
    NearestFacilityResponse,
    RouteComparisonMetrics,
    RoutePoint,
    ShortestPathRequest,
    ShortestPathResponse,
    TrafficComparisonResponse,
)
from app.services.amap import AmapServiceError, get_current_navigation
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


def _difference(current: float | None, baseline: float) -> tuple[float | None, float | None]:
    if current is None:
        return None, None
    difference = round(current - baseline, 1)
    percentage = round(difference / baseline * 100, 2) if baseline else None
    return difference, percentage


def _comparison_response(
    cityscope_route: ShortestPathResponse,
    amap: AmapNavigationEstimate,
) -> TrafficComparisonResponse:
    properties = cityscope_route.route.properties
    cityscope_speed = (
        round(properties.routing_distance_m / properties.travel_time_s * 3.6, 2)
        if properties.travel_time_s > 0
        else None
    )
    cityscope = CityScopeRouteEstimate(
        distance_m=properties.routing_distance_m,
        duration_s=properties.travel_time_s,
        duration_min=properties.travel_time_min,
        average_speed_kph=cityscope_speed,
        route=cityscope_route,
    )
    distance_difference, distance_pct = _difference(amap.distance_m, cityscope.distance_m)
    duration_difference, duration_pct = _difference(amap.duration_s, cityscope.duration_s)
    speed_difference = (
        round(amap.average_speed_kph - cityscope_speed, 2)
        if amap.average_speed_kph is not None and cityscope_speed is not None
        else None
    )
    return TrafficComparisonResponse(
        cityscope=cityscope,
        amap=amap,
        comparison=RouteComparisonMetrics(
            distance_difference_m=distance_difference,
            distance_difference_pct=distance_pct,
            duration_difference_s=duration_difference,
            duration_difference_pct=duration_pct,
            speed_difference_kph=speed_difference,
        ),
    )


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


@router.post("/traffic-comparison", response_model=TrafficComparisonResponse)
def get_traffic_comparison(
    request: ShortestPathRequest, db: Session = Depends(get_db)
) -> TrafficComparisonResponse:
    try:
        cityscope_route = shortest_path(
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

    try:
        amap = get_current_navigation(
            request.start,
            request.end,
            api_key=settings.amap_web_service_key,
        )
    except AmapServiceError as exc:
        amap = AmapNavigationEstimate(available=False, reason=exc.reason)
    return _comparison_response(cityscope_route, amap)


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
