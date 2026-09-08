import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { EmergencyResponse } from '../../../types/emergency'
import type { QueryCenter } from '../../../types/spatial'

export const EMERGENCY_SOURCE_ID = 'cityscope-emergency-result'
export const EMERGENCY_ROUTE_LAYER_ID = 'cityscope-emergency-route'
export const EMERGENCY_FACILITY_LAYER_ID = 'cityscope-emergency-facilities'

export interface EmergencyMapProperties {
  kind: string
  label?: string
  network_rank?: number
  response_time_min?: number
  network_distance_m?: number
  straight_distance_m?: number
  category?: string
  subcategory?: string
}

const EMPTY: FeatureCollection<LineString | Point, EmergencyMapProperties> = {
  type: 'FeatureCollection',
  features: [],
}

function point(pointValue: QueryCenter, properties: EmergencyMapProperties): Feature<Point, EmergencyMapProperties> {
  return { type: 'Feature', properties, geometry: { type: 'Point', coordinates: [pointValue.lon, pointValue.lat] } }
}

function connector(from: QueryCenter, to: QueryCenter): Feature<LineString, EmergencyMapProperties> {
  return { type: 'Feature', properties: { kind: 'connector' }, geometry: { type: 'LineString', coordinates: [[from.lon, from.lat], [to.lon, to.lat]] } }
}

function resultData(incident: QueryCenter | null, result: EmergencyResponse | null): FeatureCollection<LineString | Point, EmergencyMapProperties> {
  const features: Feature<LineString | Point, EmergencyMapProperties>[] = []
  if (incident) features.push(point(incident, { kind: 'incident', label: '事件位置' }))
  if (!result) return { type: 'FeatureCollection', features }

  const properties = result.response_route.properties
  features.push({
    type: 'Feature',
    properties: {
      kind: 'response-route',
      label: '响应路线：设施 → 事件点',
      response_time_min: properties.response_time_min,
      network_distance_m: properties.network_distance_m,
    },
    geometry: result.response_route.geometry,
  })
  const incidentSnap = { lon: result.incident_snap.node_lon, lat: result.incident_snap.node_lat }
  features.push(connector(result.incident, incidentSnap))
  features.push(point(incidentSnap, { kind: 'incident-snap', label: '事件吸附节点' }))

  for (const candidate of result.candidate_facilities) {
    features.push(point(candidate, {
      kind: candidate.network_rank === 1 ? 'recommended' : 'candidate',
      label: candidate.name || '未命名设施',
      network_rank: candidate.network_rank,
      response_time_min: candidate.response_time_min,
      straight_distance_m: candidate.straight_distance_m,
      category: candidate.category,
      subcategory: candidate.subcategory,
    }))
  }
  const start = result.response_route.geometry.coordinates[0]
  if (start) {
    features.push(connector(result.recommended_facility, { lon: start[0], lat: start[1] }))
  }
  return { type: 'FeatureCollection', features }
}

export function addEmergencyLayers(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  map.addSource(EMERGENCY_SOURCE_ID, { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: 'cityscope-emergency-connectors', type: 'line', source: EMERGENCY_SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'connector'], layout: { visibility },
    paint: { 'line-color': '#6d7e79', 'line-width': 2, 'line-dasharray': [2, 2] },
  })
  map.addLayer({
    id: EMERGENCY_ROUTE_LAYER_ID, type: 'line', source: EMERGENCY_SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'response-route'],
    layout: { visibility, 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#c94235', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 4, 15, 8], 'line-opacity': 0.96 },
  })
  map.addLayer({
    id: 'cityscope-emergency-route-arrows', type: 'symbol', source: EMERGENCY_SOURCE_ID,
    filter: ['==', ['get', 'kind'], 'response-route'],
    layout: {
      visibility, 'symbol-placement': 'line', 'symbol-spacing': 85,
      'text-field': '▶', 'text-size': 12, 'text-rotation-alignment': 'map',
      'text-keep-upright': false, 'text-allow-overlap': true,
    },
    paint: { 'text-color': '#ffffff', 'text-halo-color': '#c94235', 'text-halo-width': 1 },
  })
  map.addLayer({
    id: 'cityscope-emergency-points', type: 'circle', source: EMERGENCY_SOURCE_ID,
    filter: ['in', ['get', 'kind'], ['literal', ['incident', 'incident-snap']]], layout: { visibility },
    paint: {
      'circle-radius': ['match', ['get', 'kind'], 'incident', 10, 4],
      'circle-color': ['match', ['get', 'kind'], 'incident', '#c94235', '#708680'],
      'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5,
    },
  })
  map.addLayer({
    id: EMERGENCY_FACILITY_LAYER_ID, type: 'circle', source: EMERGENCY_SOURCE_ID,
    filter: ['in', ['get', 'kind'], ['literal', ['recommended', 'candidate']]], layout: { visibility },
    paint: {
      'circle-radius': ['match', ['get', 'kind'], 'recommended', 11, 7],
      'circle-color': ['match', ['get', 'kind'], 'recommended', '#176b5d', '#d19a39'],
      'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5,
    },
  })
}

export function setEmergencyData(map: Map, incident: QueryCenter | null, result: EmergencyResponse | null): void {
  ;(map.getSource(EMERGENCY_SOURCE_ID) as GeoJSONSource | undefined)?.setData(resultData(incident, result))
}

export function setEmergencyVisibility(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  for (const id of ['cityscope-emergency-connectors', EMERGENCY_ROUTE_LAYER_ID, 'cityscope-emergency-route-arrows', 'cityscope-emergency-points', EMERGENCY_FACILITY_LAYER_ID]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visibility)
  }
}
