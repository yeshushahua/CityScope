import type { QueryCenter } from './spatial'

export type RoutingMode = 'shortest' | 'nearest' | 'isochrone'
export type RoutingStatus =
  | 'idle'
  | 'selecting_start'
  | 'selecting_end'
  | 'loading'
  | 'success'
  | 'no_route'
  | 'snap_failed'
  | 'empty_facilities'
  | 'error'

export type FacilityPreset = 'hospital' | 'healthcare' | 'fire_station'

export interface NetworkSnap {
  node_id: number
  node_lon: number
  node_lat: number
  snap_distance_m: number
}

export interface RouteProperties {
  routing_distance_m: number
  travel_time_s: number
  travel_time_min: number
  edge_count: number
  edge_ids: number[]
}

export interface RouteFeature {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: number[][] }
  properties: RouteProperties
}

export interface ShortestPathResponse {
  route_found: true
  start: QueryCenter
  end: QueryCenter
  start_snap: NetworkSnap
  end_snap: NetworkSnap
  route: RouteFeature
}

export interface FacilityCandidate {
  rank: number
  poi_id: number
  osm_type: string
  osm_id: string
  name: string | null
  category: 'healthcare' | 'emergency'
  subcategory: 'hospital' | 'clinic' | 'doctors' | 'fire_station'
  lon: number
  lat: number
  node_id: number
  straight_distance_m: number
  network_distance_m: number
  travel_time_s: number
  travel_time_min: number
  facility_snap_distance_m: number
}

export interface NearestFacilityResponse {
  origin: QueryCenter
  origin_snap: NetworkSnap
  best: FacilityCandidate
  candidates: FacilityCandidate[]
  route: RouteFeature
  meta: {
    facility_count: number
    mapped_count: number
    reachable_count: number
    unreachable_count: number
    returned_count: number
  }
}

export interface IsochroneProperties {
  minutes: 5 | 10 | 15
  threshold_s: 300 | 600 | 900
  reachable_node_count: number
  area_m2: number
  area_km2: number
}

export interface IsochroneFeature {
  type: 'Feature'
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon
  properties: IsochroneProperties
}

export interface IsochroneResponse {
  origin: QueryCenter
  snap: NetworkSnap
  cost_model: 'static_travel_time'
  directed: true
  max_analysis_time_s: 900
  isochrones: {
    type: 'FeatureCollection'
    features: IsochroneFeature[]
  }
}
