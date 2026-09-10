import type { QueryCenter } from './spatial'
import type { IsochroneResponse, NetworkSnap } from './routing'

export type IncidentType = 'medical' | 'fire'
export type EmergencyStatus =
  | 'idle'
  | 'selecting'
  | 'loading'
  | 'success'
  | 'snap_failed'
  | 'no_facilities'
  | 'error'

export interface EmergencyFacilityCandidate {
  network_rank: number
  poi_id: number
  osm_type: string
  osm_id: string
  name: string | null
  category: 'healthcare' | 'emergency'
  subcategory: 'hospital' | 'fire_station'
  lon: number
  lat: number
  node_id: number | null
  edge_id: number | null
  fraction: number | null
  snapped_lon: number | null
  snapped_lat: number | null
  facility_snap_distance_m: number
  straight_distance_m: number
  response_time_s: number
  response_time_min: number
}

export interface EmergencyResponse {
  incident_type: IncidentType
  incident: QueryCenter
  incident_snap: NetworkSnap
  facility_statistics: {
    total: number
    mapped: number
    unmapped: number
    reachable: number
    unreachable: number
    returned: number
  }
  recommended_facility: EmergencyFacilityCandidate
  candidate_facilities: EmergencyFacilityCandidate[]
  response_route: {
    type: 'Feature'
    geometry: { type: 'LineString'; coordinates: number[][] }
    properties: {
      network_distance_m: number
      response_time_s: number
      response_time_min: number
      edge_count: number
      edge_ids: number[]
      routing_direction: 'facility_to_incident'
    }
  }
  response_isochrones: IsochroneResponse['isochrones']
  comparison: {
    straight_nearest_facility_id: number
    network_best_facility_id: number
    straight_nearest_is_network_best: boolean
  }
  model_metadata: {
    cost_model: 'static_travel_time'
    directed: true
    routing_direction: 'facility_to_incident'
    service_area_method: 'reachable_vertex_concave_hull'
  }
}
