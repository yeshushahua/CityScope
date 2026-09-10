# Urban Emergency Response Analysis in Lanzhou

English | [中文版](scenario-emergency-response.md)

This case study uses real results from the current CityScope database and APIs. It demonstrates edge snapping for an arbitrary incident point, candidate healthcare-facility ranking by network travel time, `facility → incident` routing, 5 / 10 / 15-minute response coverage, and a comparison with AMap current navigation. The results were captured at **2026-09-10 16:21 (Asia/Shanghai)**. Because AMap reflects current navigation conditions, its values may change when the request is repeated.

## 1. Scenario Background

A medical emergency is assumed at a selected location in the CityScope study area in Lanzhou. The closest hospital in geographic space may not be able to reach the incident fastest through the directed road network. Facility selection must therefore use network travel time rather than straight-line distance alone.

## 2. Analysis Objective

The scenario addresses three questions:

1. Which healthcare facility can reach the incident fastest over the road network?
2. What are the route, distance, and static ETA from the selected facility to the incident?
3. How does the CityScope static routing baseline differ from the AMap current-navigation estimate?

## 3. Data and Network

The analysis uses real OpenStreetMap roads, buildings, and POIs from the current Lanzhou demonstration dataset. The motor-vehicle network is stored in PostGIS and routed by pgRouting with `directed = true`. All 18,439 routable edges retain `reverse_cost = -1`; a bidirectional road is represented by two real directed edges.

Travel-time costs use static effective speeds calibrated by `highway` class. A parseable OSM `maxspeed` value acts only as an upper bound. The baseline does not include real-time congestion, fixed traffic-signal delay, turn penalties, or dynamic speeds.

## 4. Incident Location

The incident selected in the browser map is:

| Item | Value |
| --- | ---: |
| Incident longitude | 103.783489 |
| Incident latitude | 36.058598 |
| Incident type | medical |
| Candidate limit | 5 |

The point lies inside the study extent and has several mapped hospitals nearby. The shortest-path, nearest-facility, isochrone, emergency-response, and traffic-comparison endpoints all returned HTTP 200 for the scenario checks.

## 5. Edge Snapping

CityScope does not force the incident point onto the nearest road-network vertex. It projects the point onto the nearest routable edge and starts routing from the actual position within that edge:

```text
Raw incident point
        ↓
Nearest routable edge
        ↓
Projected point + fraction
        ↓
pgr_withPoints routing
```

The actual incident snapping result was:

| Item | Value |
| --- | ---: |
| Edge ID | 8,884 |
| Source | 4,185,030,235 |
| Target | 11,293,237,382 |
| Edge fraction | 0.133452809576 |
| Projected longitude | 103.783552783611 |
| Projected latitude | 36.058617400766 |
| Snap distance | 6.1 m |

The recommended facility was also projected onto an edge: edge 3,681 at fraction 0.279652868552, with a facility snap distance of 28.0 m. The off-network connector between each submitted coordinate and its snapped point is returned as metadata and is not included in route distance or ETA.

## 6. Network-Based Facility Selection

The emergency-response endpoint evaluated 58 mapped hospitals. Of these, 57 could reach the incident over the directed road network, and the five lowest network-travel-time candidates were returned. The routing direction remained `facility → incident`.

| Network rank | Facility | Straight-line distance | Response ETA |
| ---: | --- | ---: | ---: |
| 1 | Qilihe District Traditional Chinese Medicine Hospital* (`七里河区中药医院`) | 1,521.4 m | 218.3 s / 3.64 min |
| 2 | Gansu Provincial Cancer Hospital (`甘肃省肿瘤医院`) | 1,029.9 m | 296.0 s / 4.93 min |
| 3 | Gansu Provincial Maternal and Child Health Hospital* (`甘肃省妇幼保健院`) | 1,549.0 m | 299.7 s / 4.99 min |
| 4 | Unnamed hospital (POI 626) | 2,168.6 m | 317.9 s / 5.30 min |
| 5 | No. 940 Hospital* (`第九四〇医院`) | 1,207.2 m | 321.8 s / 5.36 min |

\* English facility names marked with an asterisk are descriptive translations of the Chinese OSM names. They are not presented as official English institution names.

| Selection criterion | Facility |
| --- | --- |
| Nearest by straight-line distance | Gansu Provincial Cancer Hospital (`甘肃省肿瘤医院`, POI 1052) |
| Fastest by facility-to-incident network travel time | Qilihe District Traditional Chinese Medicine Hospital* (`七里河区中药医院`, POI 1022) |

The real result shows that minimum straight-line distance does not guarantee minimum response time under road direction and travel-time constraints. The standalone `nearest-facility` endpoint calculates from the incident toward facilities, `incident → facility`, and returned Gansu Provincial Cancer Hospital in this check. That query is not equivalent to the reverse operational direction used for emergency response.

## 7. Emergency Response Route

The recommended facility was `七里河区中药医院`, referred to here by the descriptive translation **Qilihe District Traditional Chinese Medicine Hospital**. Its source coordinate was `(103.799750850710, 36.054905750000)`. The response route retained the `facility → incident` direction.

| Metric | Result |
| --- | ---: |
| Routing distance | 2,003.0 m |
| Static response time | 218.3 s / 3.64 min |
| Average speed derived from returned distance and time | 33.03 km/h |
| Traversed directed edges | 13 |

A separate shortest-path request with the same origin and destination returned the same 2,003.0 m distance, 218.3 s travel time, and 13 directed edges. This confirms consistency between the emergency route and the general routing service.

## 8. 5 / 10 / 15-Minute Response Coverage

The response coverage starts at the recommended facility's edge-snapped position. `pgr_withPointsDD` calculates reachable nodes, and PostGIS builds a Concave Hull for map visualization.

| Time band | Reachable nodes | Approximate area |
| ---: | ---: | ---: |
| 5 min | 191 | 4.060 km² |
| 10 min | 1,286 | 32.002 km² |
| 15 min | 2,820 | 111.626 km² |

Reachable-node counts and approximate areas increase monotonically with the time threshold. The polygons approximate the spatial extent of reachable road-network nodes; they are neither administrative boundaries nor real-time emergency-service commitments.

## 9. CityScope Static Baseline vs AMap Current Navigation

The comparison uses the same direction and source coordinates: `七里河区中药医院 → incident`.

| Metric | CityScope Static Baseline | AMap Current Navigation |
| --- | ---: | ---: |
| Distance | 2,003.0 m | 2,027.0 m |
| ETA | 218.3 s / 3.64 min | 563.0 s / 9.38 min |
| Average speed | 33.03 km/h | 12.96 km/h |

AMap also returned 2 traffic lights, 1 alternative route, and a toll of CNY 0. Its TMC composition was 1,452 m smooth, 330 m congested, and 245 m unknown, with 0 m slow and 0 m severely congested.

CityScope provides a static routing baseline based on the OSM road network, pgRouting, and calibrated effective road speeds, while AMap provides a navigation estimate under current road conditions. The ETA difference was 344.7 s, but this difference must not be interpreted solely as congestion delay. Traffic conditions, traffic signals, intersections, route selection, coordinate conversion, and differences between navigation models may all contribute to the observed result.

## 10. Findings

- Network travel-time ranking changed the facility choice: the closest hospital by straight-line distance was not the fastest facility under `facility → incident` routing.
- The 6.1 m incident edge snap allowed the route to begin at the projected point within the road, preserving the partial cost of the endpoint edge.
- The 5 / 10 / 15-minute bands provide graduated response-coverage views under the same static cost model.
- CityScope and AMap results support comparison under different traffic assumptions; they do not constitute a formal navigation-accuracy benchmark.

## 11. Reproduction

After starting the database, backend, and frontend, open the Emergency Response module, select a medical incident, and click near `(103.783489, 36.058598)`. The scenario can also be reproduced through the API:

```bash
curl -X POST http://localhost:8000/api/v1/emergency/response \
  -H "Content-Type: application/json" \
  -d '{"incident":{"lon":103.783489,"lat":36.058598},"incident_type":"medical","candidate_limit":5}'
```

```bash
curl -X POST http://localhost:8000/api/v1/routing/traffic-comparison \
  -H "Content-Type: application/json" \
  -d '{"start":{"lon":103.79975085070964,"lat":36.05490575},"end":{"lon":103.783489,"lat":36.058598}}'
```

The AMap response requires a valid `AMAP_WEB_SERVICE_KEY`, network access, and service availability. A repeated request should be documented with its new capture time and returned values.

## 12. Technical Notes

- Data coordinates: EPSG:4326. Metric projection or PostGIS geography is used where distance calculations require metres.
- Routing functions: `pgr_withPoints`, `pgr_withPointsCost`, and `pgr_withPointsDD`.
- Direction constraints: `directed = true` and `reverse_cost = -1`.
- The 39 source-graph edges with `source = target` remain in the network but are excluded from edge-snapping candidates.
- This scenario demonstrates spatial decision support. It is not an operational medical-dispatch recommendation.
