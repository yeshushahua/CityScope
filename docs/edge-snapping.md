# Edge Snapping

CityScope motor routing projects dynamic coordinates onto `routing_edges` and
routes from request-local pgRouting points. The implementation uses
`pgr_withPoints`, `pgr_withPointsCost`, and `pgr_withPointsDD`; it does not add
nodes or edges to the stored routing graph.

The nearest-edge query uses the geometry GiST index for a metric bounding-box
prefilter and geography distance for the final limit and ordering. Projection
is calculated in EPSG:32648 after densifying long geographic segments, then
normalized to a fraction on the original WGS84 edge geometry. Points within
one metre of an endpoint are represented by the real graph vertex.

Two-way streets are stored as two independent directed edges. A snapped
location is attached to both directions only when a real reverse edge has
swapped endpoints, the same OSM identifier, and matching geometry. Routing
continues to use `directed=true` and `reverse_cost=-1`.

The route distance and ETA cover only the travelled road geometry. The
off-network distance from the submitted coordinate to its projected point is
returned as `snap_distance_m` and is not converted to driving time.

## Known limits

- The nearest geometry wins deterministically when parallel roads are close.
- Heading, lane, bridge level, tunnel level, and GPS history are not used.
- Grade-separated roads remain topologically separate, but a coordinate can
  still snap to the wrong level when their geometries overlap.
- Self-loop edges remain in the routing graph but are excluded from snapping
  candidates. They are never used to create virtual points.
- Fixed facilities are projected in one set-based query. Their existing
  `poi_routing_access` node mapping remains available as a fallback when no
  edge is found within 500 metres.
