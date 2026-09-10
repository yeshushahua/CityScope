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

export interface AmapTrafficBreakdown {
  smooth_m: number
  slow_m: number
  congested_m: number
  severely_congested_m: number
  unknown_m: number
}

export interface AmapNavigationEstimate {
  available: boolean
  reason: string | null
  distance_m: number | null
  duration_s: number | null
  duration_min: number | null
  average_speed_kph: number | null
  traffic_light_count: number | null
  toll_yuan: number | null
  alternative_count: number | null
  traffic: AmapTrafficBreakdown | null
}

export interface TrafficComparisonResponse {
  cityscope: {
    distance_m: number
    duration_s: number
    duration_min: number
    average_speed_kph: number | null
    route: ShortestPathResponse
  }
  amap: AmapNavigationEstimate
  comparison: {
    distance_difference_m: number | null
    distance_difference_pct: number | null
    duration_difference_s: number | null
    duration_difference_pct: number | null
    speed_difference_kph: number | null
  }
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
