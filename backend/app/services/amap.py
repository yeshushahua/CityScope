"""AMap coordinate conversion, driving estimate, and TMC parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from app.schemas.routing import (
    AmapNavigationEstimate,
    AmapTrafficBreakdown,
    RoutePoint,
)

COORDINATE_CONVERT_URL = "https://restapi.amap.com/v3/assistant/coordinate/convert"
DRIVING_URL = "https://restapi.amap.com/v5/direction/driving"
DEFAULT_TIMEOUT_S = 5.0


class AmapServiceError(RuntimeError):
    """Safe, user-visible failure without credentials or request URLs."""

    def __init__(self, reason: str, *, stage: str, code: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage
        self.code = code


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _integer(value: Any) -> int | None:
    parsed = _number(value)
    return int(parsed) if parsed is not None else None


def _api_success(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("status")) == "1" and str(payload.get("infocode")) == "10000"


def _get_json(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, Any],
    stage: str,
) -> Mapping[str, Any]:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise AmapServiceError(
            f"AMap {stage} request timed out", stage=stage
        ) from exc
    except httpx.HTTPError as exc:
        status = str(exc.response.status_code) if isinstance(exc, httpx.HTTPStatusError) else None
        raise AmapServiceError(
            f"AMap {stage} request failed", stage=stage, code=status
        ) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise AmapServiceError(
            f"AMap {stage} returned invalid data", stage=stage
        ) from exc
    if not isinstance(payload, Mapping):
        raise AmapServiceError(f"AMap {stage} returned invalid data", stage=stage)
    return payload


def convert_wgs84_points(
    client: httpx.Client,
    points: Sequence[RoutePoint],
    *,
    api_key: str,
) -> list[tuple[float, float]]:
    payload = _get_json(
        client,
        COORDINATE_CONVERT_URL,
        params={
            "key": api_key,
            "coordsys": "gps",
            "locations": "|".join(f"{point.lon:.6f},{point.lat:.6f}" for point in points),
        },
        stage="coordinate conversion",
    )
    if not _api_success(payload):
        raise AmapServiceError(
            "AMap coordinate conversion failed",
            stage="coordinate conversion",
            code=str(payload.get("infocode") or "unknown"),
        )
    raw_locations = payload.get("locations")
    if not isinstance(raw_locations, str):
        raise AmapServiceError(
            "AMap coordinate conversion returned invalid locations",
            stage="coordinate conversion",
        )
    # AMap accepts input coordinate pairs separated by "|" but separates
    # multiple converted output pairs with ";".
    parts = raw_locations.split(";")
    if len(parts) != len(points):
        raise AmapServiceError(
            "AMap coordinate conversion returned an unexpected location count",
            stage="coordinate conversion",
        )
    converted: list[tuple[float, float]] = []
    for raw in parts:
        pair = raw.split(",")
        if len(pair) != 2:
            raise AmapServiceError(
                "AMap coordinate conversion returned invalid locations",
                stage="coordinate conversion",
            )
        try:
            converted.append((float(pair[0]), float(pair[1])))
        except ValueError as exc:
            raise AmapServiceError(
                "AMap coordinate conversion returned invalid locations",
                stage="coordinate conversion",
            ) from exc
    return converted


def summarize_tmc(path: Mapping[str, Any]) -> AmapTrafficBreakdown:
    totals = {
        "smooth_m": 0.0,
        "slow_m": 0.0,
        "congested_m": 0.0,
        "severely_congested_m": 0.0,
        "unknown_m": 0.0,
    }
    status_fields = {
        "畅通": "smooth_m",
        "缓行": "slow_m",
        "拥堵": "congested_m",
        "严重拥堵": "severely_congested_m",
    }
    steps = path.get("steps")
    if not isinstance(steps, list):
        return AmapTrafficBreakdown(**totals)
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        tmcs = step.get("tmcs")
        if not isinstance(tmcs, list):
            continue
        for tmc in tmcs:
            if not isinstance(tmc, Mapping):
                continue
            distance = _number(tmc.get("tmc_distance", tmc.get("distance")))
            if distance is None:
                continue
            status = tmc.get("tmc_status", tmc.get("status"))
            field = status_fields.get(str(status or ""), "unknown_m")
            totals[field] += distance
    return AmapTrafficBreakdown(**{key: round(value, 1) for key, value in totals.items()})


def parse_driving_response(payload: Mapping[str, Any]) -> AmapNavigationEstimate:
    if not _api_success(payload):
        raise AmapServiceError(
            "AMap driving request failed",
            stage="driving",
            code=str(payload.get("infocode") or "unknown"),
        )
    route = payload.get("route")
    paths = route.get("paths") if isinstance(route, Mapping) else None
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], Mapping):
        raise AmapServiceError("AMap driving returned no route", stage="driving")
    path = paths[0]
    cost = path.get("cost") if isinstance(path.get("cost"), Mapping) else {}
    distance = _number(path.get("distance"))
    duration = _number(cost.get("duration"))
    average_speed = (
        round(distance / duration * 3.6, 2)
        if distance is not None and duration is not None and duration > 0
        else None
    )
    return AmapNavigationEstimate(
        available=True,
        distance_m=round(distance, 1) if distance is not None else None,
        duration_s=round(duration, 1) if duration is not None else None,
        duration_min=round(duration / 60, 2) if duration is not None else None,
        average_speed_kph=average_speed,
        traffic_light_count=_integer(cost.get("traffic_lights", path.get("traffic_lights"))),
        toll_yuan=_number(cost.get("tolls", path.get("tolls"))),
        alternative_count=len(paths),
        traffic=summarize_tmc(path),
    )


def get_current_navigation(
    start: RoutePoint,
    end: RoutePoint,
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> AmapNavigationEstimate:
    if not api_key.strip():
        raise AmapServiceError("AMap key is not configured", stage="configuration")

    def request(active_client: httpx.Client) -> AmapNavigationEstimate:
        converted = convert_wgs84_points(active_client, [start, end], api_key=api_key)
        origin, destination = converted
        payload = _get_json(
            active_client,
            DRIVING_URL,
            params={
                "key": api_key,
                "origin": f"{origin[0]:.6f},{origin[1]:.6f}",
                "destination": f"{destination[0]:.6f},{destination[1]:.6f}",
                "strategy": 32,
                "show_fields": "cost,tmcs",
            },
            stage="driving",
        )
        return parse_driving_response(payload)

    if client is not None:
        return request(client)
    timeout = httpx.Timeout(DEFAULT_TIMEOUT_S)
    with httpx.Client(timeout=timeout, headers={"User-Agent": "CityScope/1.0"}) as active_client:
        return request(active_client)
