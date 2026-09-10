from pathlib import Path
import sys

import geopandas as gpd
import pytest
from shapely.geometry import LineString

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.osm.preprocess_osm import (  # noqa: E402
    _default_speed,
    _is_motor_highway,
    _parse_maxspeed,
    build_routing_edges,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("50", 50.0),
        ("50 km/h", 50.0),
        ("30 mph", 48.28032),
        ("60; 40", 40.0),
        ("30 knots", None),
        ("30 kmh", None),
        ("signals", None),
    ],
)
def test_maxspeed_parser_accepts_only_supported_units(
    raw: str, expected: float | None
) -> None:
    parsed = _parse_maxspeed(raw)
    if expected is None:
        assert parsed is None
    else:
        assert parsed == pytest.approx(expected)


def test_highway_effective_speeds_use_lowest_class_and_fallback() -> None:
    assert _default_speed("motorway") == 65
    assert _default_speed("primary; residential") == 20
    assert _default_speed("unknown_motor_class") == 20
    assert _is_motor_highway("residential") is True
    assert _is_motor_highway("ladder") is False
    assert _is_motor_highway("residential; ladder") is False


def test_osm_maxspeed_is_capped_by_highway_effective_speed() -> None:
    edges = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3, 4],
            "u": [10, 20, 30, 40],
            "v": [11, 21, 31, 41],
            "osm_id": ["a", "b", "c", "d"],
            "edge_key": [0, 0, 0, 0],
            "name": [None, None, None, None],
            "highway": ["motorway", "primary", "secondary", "primary; residential"],
            "oneway": [True, True, False, False],
            "maxspeed": ["100", "20", None, "60"],
            "length_m": [650.0, 200.0, 300.0, 200.0],
            "geometry": [
                LineString([(103.0, 36.0), (103.01, 36.0)]),
                LineString([(103.0, 36.0), (103.01, 36.0)]),
                LineString([(103.0, 36.0), (103.01, 36.0)]),
                LineString([(103.0, 36.0), (103.01, 36.0)]),
            ],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )

    routing = build_routing_edges(edges)

    assert routing["speed_kph"].tolist() == [65.0, 20.0, 30.0, 20.0]
    assert routing["speed_source"].tolist() == ["osm", "osm", "default", "osm"]
    assert routing["reverse_cost"].tolist() == [-1.0, -1.0, -1.0, -1.0]
    for row in routing.itertuples():
        assert row.travel_time_s == pytest.approx(
            row.length_m / (row.speed_kph / 3.6)
        )
        assert row.cost == pytest.approx(row.travel_time_s)
