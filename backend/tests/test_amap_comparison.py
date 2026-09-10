from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import routing as routing_api
from app.main import app
from app.schemas.routing import (
    AmapNavigationEstimate,
    AmapTrafficBreakdown,
    NetworkSnap,
    RouteFeature,
    RoutePoint,
    RouteProperties,
    ShortestPathResponse,
)
from app.services.amap import (
    AmapServiceError,
    COORDINATE_CONVERT_URL,
    DRIVING_URL,
    get_current_navigation,
    parse_driving_response,
    summarize_tmc,
)

client = TestClient(app)
START = RoutePoint(lon=103.8343, lat=36.0611)
END = RoutePoint(lon=103.85, lat=36.07)


def coordinate_payload(*, status: str = "1", infocode: str = "10000") -> dict[str, Any]:
    return {
        "status": status,
        "infocode": infocode,
        "locations": "103.836720,36.060790;103.852410,36.069690",
    }


def driving_payload(
    *,
    status: str = "1",
    infocode: str = "10000",
    duration: str | None = "600",
) -> dict[str, Any]:
    cost: dict[str, Any] = {"traffic_lights": "4", "tolls": "0"}
    if duration is not None:
        cost["duration"] = duration
    return {
        "status": status,
        "infocode": infocode,
        "route": {
            "paths": [
                {
                    "distance": "3070",
                    "cost": cost,
                    "steps": [
                        {
                            "tmcs": [
                                {"tmc_status": "畅通", "tmc_distance": "2100"},
                                {"tmc_status": "缓行", "tmc_distance": "300"},
                                {"tmc_status": "拥堵", "tmc_distance": "200"},
                                {"tmc_status": "严重拥堵", "tmc_distance": "0"},
                                {"tmc_status": "未采集", "tmc_distance": "470"},
                            ]
                        }
                    ],
                },
                {
                    "distance": "2500",
                    "cost": {"duration": "300", "traffic_lights": "2"},
                    "steps": [],
                },
            ]
        },
    }


def mock_client(
    *,
    coordinate: dict[str, Any] | None = None,
    driving: dict[str, Any] | None = None,
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(COORDINATE_CONVERT_URL):
            return httpx.Response(200, json=coordinate or coordinate_payload())
        if str(request.url).startswith(DRIVING_URL):
            return httpx.Response(200, json=driving or driving_payload())
        raise AssertionError(f"Unexpected test URL: {request.url.host}{request.url.path}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def shortest_response() -> ShortestPathResponse:
    snap = NetworkSnap(node_id=1, node_lon=103.834, node_lat=36.061, snap_distance_m=20)
    return ShortestPathResponse(
        start=START,
        end=END,
        start_snap=snap,
        end_snap=NetworkSnap(node_id=2, node_lon=103.85, node_lat=36.07, snap_distance_m=18),
        route=RouteFeature(
            geometry={
                "type": "LineString",
                "coordinates": [[START.lon, START.lat], [END.lon, END.lat]],
            },
            properties=RouteProperties(
                routing_distance_m=2800,
                travel_time_s=420,
                travel_time_min=7,
                edge_count=2,
                edge_ids=[1, 2],
            ),
        ),
    )


def test_amap_normal_response_converts_coordinates_and_parses_current_route() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/coordinate/convert"):
            assert request.url.params["coordsys"] == "gps"
            assert request.url.params["locations"].count("|") == 1
            return httpx.Response(200, json=coordinate_payload())
        assert request.url.path.endswith("/direction/driving")
        assert request.url.params["origin"] == "103.836720,36.060790"
        assert request.url.params["destination"] == "103.852410,36.069690"
        assert request.url.params["strategy"] == "32"
        assert request.url.params["show_fields"] == "cost,tmcs"
        return httpx.Response(200, json=driving_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport_client:
        result = get_current_navigation(START, END, api_key="test-key", client=transport_client)

    assert len(requests) == 2
    assert result.available is True
    assert result.distance_m == 3070
    assert result.duration_s == 600
    assert result.duration_min == 10
    assert result.average_speed_kph == 18.42
    assert result.traffic_light_count == 4
    assert result.toll_yuan == 0


def test_coordinate_conversion_failure_stops_before_driving() -> None:
    with mock_client(coordinate=coordinate_payload(status="0", infocode="10003")) as transport_client:
        with pytest.raises(AmapServiceError) as error:
            get_current_navigation(START, END, api_key="test-key", client=transport_client)
    assert error.value.stage == "coordinate conversion"
    assert error.value.code == "10003"
    assert "test-key" not in str(error.value)


def test_coordinate_conversion_requires_two_locations() -> None:
    payload = coordinate_payload()
    payload["locations"] = "103.836720,36.060790"
    with mock_client(coordinate=payload) as transport_client:
        with pytest.raises(AmapServiceError, match="unexpected location count"):
            get_current_navigation(START, END, api_key="test-key", client=transport_client)


def test_driving_api_failure_is_sanitized() -> None:
    with mock_client(driving=driving_payload(status="0", infocode="10021")) as transport_client:
        with pytest.raises(AmapServiceError) as error:
            get_current_navigation(START, END, api_key="test-key", client=transport_client)
    assert error.value.stage == "driving"
    assert error.value.code == "10021"
    assert "test-key" not in str(error.value)


def test_timeout_is_converted_without_request_url_or_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport_client:
        with pytest.raises(AmapServiceError) as error:
            get_current_navigation(START, END, api_key="test-key", client=transport_client)
    assert error.value.stage == "coordinate conversion"
    assert str(error.value) == "AMap coordinate conversion request timed out"


def test_missing_key_fails_before_http() -> None:
    with pytest.raises(AmapServiceError, match="key is not configured") as error:
        get_current_navigation(START, END, api_key="")
    assert error.value.stage == "configuration"


@pytest.mark.parametrize("duration", ["0", None])
def test_zero_or_missing_duration_has_no_derived_speed(duration: str | None) -> None:
    result = parse_driving_response(driving_payload(duration=duration))
    assert result.available is True
    assert result.average_speed_kph is None
    assert result.duration_s == (0 if duration == "0" else None)


def test_tmc_summary_includes_known_and_unknown_statuses() -> None:
    result = summarize_tmc(driving_payload()["route"]["paths"][0])
    assert result == AmapTrafficBreakdown(
        smooth_m=2100,
        slow_m=300,
        congested_m=200,
        severely_congested_m=0,
        unknown_m=470,
    )


def test_multiple_paths_preserve_amap_first_choice() -> None:
    result = parse_driving_response(driving_payload())
    assert result.alternative_count == 2
    assert result.distance_m == 3070
    assert result.duration_s == 600


def test_amap_failure_keeps_cityscope_route_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing_api, "shortest_path", lambda *args, **kwargs: shortest_response())

    def fail_amap(*args: Any, **kwargs: Any) -> AmapNavigationEstimate:
        raise AmapServiceError("AMap driving request failed", stage="driving", code="10021")

    monkeypatch.setattr(routing_api, "get_current_navigation", fail_amap)
    response = client.post(
        "/api/v1/routing/traffic-comparison",
        json={"start": START.model_dump(), "end": END.model_dump()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cityscope"]["route"]["route_found"] is True
    assert body["cityscope"]["distance_m"] == 2800
    assert body["amap"] == {
        "available": False,
        "reason": "AMap driving request failed",
        "distance_m": None,
        "duration_s": None,
        "duration_min": None,
        "average_speed_kph": None,
        "traffic_light_count": None,
        "toll_yuan": None,
        "alternative_count": None,
        "traffic": None,
    }
    assert body["comparison"]["duration_difference_s"] is None


def test_comparison_differences_use_amap_minus_cityscope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routing_api, "shortest_path", lambda *args, **kwargs: shortest_response())
    monkeypatch.setattr(
        routing_api,
        "get_current_navigation",
        lambda *args, **kwargs: AmapNavigationEstimate(
            available=True,
            distance_m=3070,
            duration_s=600,
            duration_min=10,
            average_speed_kph=18.42,
            traffic_light_count=4,
            toll_yuan=0,
            alternative_count=2,
            traffic=AmapTrafficBreakdown(smooth_m=3070),
        ),
    )
    body = client.post(
        "/api/v1/routing/traffic-comparison",
        json={"start": START.model_dump(), "end": END.model_dump()},
    ).json()
    assert body["comparison"] == {
        "distance_difference_m": 270,
        "distance_difference_pct": 9.64,
        "duration_difference_s": 180,
        "duration_difference_pct": 42.86,
        "speed_difference_kph": -5.58,
    }
