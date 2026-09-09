# CityScope Final Validation

Validation date: 2026-09-09

## Automated checks

- Backend: `140 passed` in 8.79 seconds.
- Frontend: TypeScript validation and Vite production build passed; 115 modules transformed.
- Build note: MapLibre remains a large lazy-loaded vendor chunk and triggers Vite's non-blocking 500 kB warning.
- Database: Compose service `postgres` is healthy and `pg_isready` reports accepting connections.

## Browser smoke test

The local FastAPI and Vite services were started from the documented commands and tested against the real PostGIS dataset.

- Default map loaded with Backend and PostGIS Online.
- Spatial query returned real POI and building statistics.
- Directed point-to-point routing returned a route, distance and travel time.
- Motorized 5 / 10 / 15 minute Isochrone returned reachable nodes and polygon areas.
- Medical emergency analysis returned a recommended facility, response route and service areas.
- Fifteen-minute living-circle analysis returned 5 / 5 core categories and network-reachable POIs.
- 2D and 2.5D/3D building views both rendered.
- Browser console error count: 0.

During final smoke testing, inactive motorized/emergency Isochrone layers were found to remain visible after switching to the living-circle module. Isochrone ownership is now resolved from the current module in one effect; switching modules was rebuilt and visually retested successfully.

## Delivery checks

- Portfolio README: completed with architecture, algorithms, startup, initialization, attribution and limitations.
- Screenshots: optional and not included in the final repository; this does not affect core project completion.
- `.env` files, virtual environments, dependencies, build output, caches and logs are ignored and not tracked.
- Tracked-file secret signature scan: no private keys or common live-token signatures found.
- Git operations: no commit, push, rebase or reset performed.

## Known limitations

- Motorized travel time uses static road-class speeds and excludes live traffic.
- Walking time uses a static 4.8 km/h speed.
- Endpoints use vertex snapping rather than edge-position map matching.
- Isochrone boundaries approximate reachable nodes with concave hulls.
- Building height coverage depends on available OSM tags.
- Emergency output is a spatial decision demonstration, not an operational dispatch system.

## Completion status

- Phase 10: PASS
- CityScope Core Project: COMPLETED
