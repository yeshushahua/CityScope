import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { QueryCenter } from '../../../types/spatial'
import type { IsochroneResponse, NearestFacilityResponse, RoutingMode, ShortestPathResponse } from '../../../types/routing'
import { MAP_COLORS } from '../../../config/visualization'

export const ROUTING_SOURCE_ID = 'cityscope-routing'
export const ROUTE_LINE_LAYER_ID = 'cityscope-route-line'
export const ROUTE_CONNECTOR_LAYER_ID = 'cityscope-route-connectors'
export const ROUTE_POINT_LAYER_ID = 'cityscope-route-points'
export const ROUTE_FACILITY_LAYER_ID = 'cityscope-route-facilities'

type RoutingProperties = {
  kind: string
  label?: string
  rank?: number
  travel_time_min?: number
  network_distance_m?: number
  straight_distance_m?: number
  edge_count?: number
  category?: string
  subcategory?: string
  osm_id?: string
  facility_snap_distance_m?: number
}

const EMPTY: FeatureCollection<LineString | Point, RoutingProperties> = {
  type: 'FeatureCollection',
  features: [],
}

function pointFeature(point: QueryCenter, properties: RoutingProperties): Feature<Point, RoutingProperties> {
  return { type: 'Feature', properties, geometry: { type: 'Point', coordinates: [point.lon, point.lat] } }
}

function connector(from: QueryCenter, to: QueryCenter): Feature<LineString, RoutingProperties> {
  return {
    type: 'Feature',
    properties: { kind: 'connector' },
    geometry: { type: 'LineString', coordinates: [[from.lon, from.lat], [to.lon, to.lat]] },
  }
}

function resultData(
  mode: RoutingMode,
  start: QueryCenter | null,
  end: QueryCenter | null,
  shortest: ShortestPathResponse | null,
  nearest: NearestFacilityResponse | null,
  isochrone: IsochroneResponse | null,
): FeatureCollection<LineString | Point, RoutingProperties> {
  const features: Feature<LineString | Point, RoutingProperties>[] = []
  if (start) features.push(pointFeature(start, { kind: 'start', label: mode === 'nearest' ? '当前位置' : '起点' }))
  if (mode === 'shortest' && end) features.push(pointFeature(end, { kind: 'end', label: '终点' }))
  if (mode === 'isochrone') {
    if (isochrone) {
      const snap = { lon: isochrone.snap.node_lon, lat: isochrone.snap.node_lat }
      features.push(connector(isochrone.origin, snap))
      features.push(pointFeature(snap, { kind: 'snap', label: '起点吸附节点' }))
    }
    return { type: 'FeatureCollection', features }
  }
  const result = mode === 'shortest' ? shortest : nearest
  if (!result) return { type: 'FeatureCollection', features }

  features.push({
    type: 'Feature',
    properties: {
      kind: 'route',
      label: '最短时间路径',
      travel_time_min: result.route.properties.travel_time_min,
      network_distance_m: result.route.properties.routing_distance_m,
      edge_count: result.route.properties.edge_count,
    },
    geometry: result.route.geometry,
  })

  if (mode === 'shortest' && shortest) {
    const startSnap = { lon: shortest.start_snap.node_lon, lat: shortest.start_snap.node_lat }
    const endSnap = { lon: shortest.end_snap.node_lon, lat: shortest.end_snap.node_lat }
    features.push(connector(shortest.start, startSnap), connector(shortest.end, endSnap))
    features.push(pointFeature(startSnap, { kind: 'snap', label: '起点吸附节点' }))
    features.push(pointFeature(endSnap, { kind: 'snap', label: '终点吸附节点' }))
  }

  if (mode === 'nearest' && nearest) {
    const originSnap = { lon: nearest.origin_snap.node_lon, lat: nearest.origin_snap.node_lat }
    features.push(connector(nearest.origin, originSnap))
    features.push(pointFeature(originSnap, { kind: 'snap', label: '起点吸附节点' }))
    for (const candidate of nearest.candidates) {
      features.push(pointFeature(candidate, {
        kind: candidate.rank === 1 ? 'best-facility' : 'facility',
        label: candidate.name || '未命名设施',
        rank: candidate.rank,
        travel_time_min: candidate.travel_time_min,
        network_distance_m: candidate.network_distance_m,
        straight_distance_m: candidate.straight_distance_m,
        category: candidate.category,
        subcategory: candidate.subcategory,
        osm_id: `${candidate.osm_type} ${candidate.osm_id}`,
        facility_snap_distance_m: candidate.facility_snap_distance_m,
      }))
    }
    const bestSnap = { lon: nearest.route.geometry.coordinates.at(-1)?.[0] ?? nearest.best.lon, lat: nearest.route.geometry.coordinates.at(-1)?.[1] ?? nearest.best.lat }
    features.push(connector(nearest.best, bestSnap))
  }
  return { type: 'FeatureCollection', features }
}

export function addRoutingLayers(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  map.addSource(ROUTING_SOURCE_ID, { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: ROUTE_CONNECTOR_LAYER_ID,
    type: 'line',
    source: ROUTING_SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'connector'],
    layout: { visibility },
    paint: { 'line-color': MAP_COLORS.connector, 'line-width': 2, 'line-dasharray': [2, 2] },
  })
  map.addLayer({
    id: ROUTE_LINE_LAYER_ID,
    type: 'line',
    source: ROUTING_SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'route'],
    layout: { visibility, 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': MAP_COLORS.route, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 3, 15, 7], 'line-opacity': 0.94 },
  })
  map.addLayer({
    id: ROUTE_POINT_LAYER_ID,
    type: 'circle',
    source: ROUTING_SOURCE_ID,
    filter: ['in', ['get', 'kind'], ['literal', ['start', 'end', 'snap']]],
    layout: { visibility },
    paint: {
      'circle-radius': ['match', ['get', 'kind'], 'snap', 4, 8],
      'circle-color': ['match', ['get', 'kind'], 'start', MAP_COLORS.origin, 'end', MAP_COLORS.destination, '#7b918b'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
    },
  })
  map.addLayer({
    id: ROUTE_FACILITY_LAYER_ID,
    type: 'circle',
    source: ROUTING_SOURCE_ID,
    filter: ['in', ['get', 'kind'], ['literal', ['facility', 'best-facility']]],
    layout: { visibility },
    paint: {
      'circle-radius': ['match', ['get', 'kind'], 'best-facility', 10, 7],
      'circle-color': ['match', ['get', 'kind'], 'best-facility', MAP_COLORS.destination, MAP_COLORS.candidate],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2.5,
    },
  })
}

export function setRoutingData(
  map: Map,
  mode: RoutingMode,
  start: QueryCenter | null,
  end: QueryCenter | null,
  shortest: ShortestPathResponse | null,
  nearest: NearestFacilityResponse | null,
  isochrone: IsochroneResponse | null,
): void {
  ;(map.getSource(ROUTING_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
    resultData(mode, start, end, shortest, nearest, isochrone),
  )
}

export function setRoutingVisibility(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  for (const id of [ROUTE_CONNECTOR_LAYER_ID, ROUTE_LINE_LAYER_ID, ROUTE_POINT_LAYER_ID, ROUTE_FACILITY_LAYER_ID]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visibility)
  }
}
