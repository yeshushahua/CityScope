import type { Feature, FeatureCollection, MultiPolygon, Point, Polygon } from 'geojson'
import type { QueryCenter } from './spatial'

export type LivingCircleCategory =
  | 'commercial'
  | 'healthcare'
  | 'education'
  | 'recreation'
  | 'transport'

export type LivingCircleStatus =
  | 'selecting'
  | 'loading'
  | 'success'
  | 'snap_failed'
  | 'no_data'
  | 'error'

export interface LivingCircleBandProperties {
  minutes: 5 | 10 | 15
  threshold_s: 300 | 600 | 900
  network_budget_s: number
  reachable_node_count: number
  area_m2: number
  area_km2: number
}

export interface LivingCirclePoiProperties {
  poi_id: number
  osm_type: string
  osm_id: string
  name: string | null
  category: LivingCircleCategory
  subcategory: string
  lon: number
  lat: number
  total_walk_time_s: number
  total_walk_time_min: number
  network_time_s: number
  origin_connector_time_s: number
  poi_connector_time_s: number
  poi_snap_distance_m: number
}

export interface LivingCircleResponse {
  origin: QueryCenter
  origin_snap: {
    node_id: number
    node_lon: number
    node_lat: number
    snap_distance_m: number
    connector_time_s: number
  }
  isochrones: FeatureCollection<Polygon | MultiPolygon, LivingCircleBandProperties>
  coverage: {
    present_categories: number
    total_categories: 5
    presence_ratio: number
    definition: 'reachable_core_category_presence'
  }
  summary: {
    reachable_poi_count: number
    displayed_poi_count: number
    covered_categories: number
    primary_categories: 5
    category_coverage_ratio: number
    area_15min_m2: number
    area_15min_km2: number
    reachable_nodes_15min: number
  }
  categories: Array<{
    category: LivingCircleCategory
    reachable_poi_count: number
    unique_subcategory_count: number
    reachable_5min: number
    reachable_10min: number
    reachable_15min: number
    nearest_walk_time_min: number | null
    nearest_walk_time_s: number | null
    nearest_poi: { poi_id: number; name: string | null; subcategory: string } | null
  }>
  reachable_pois: FeatureCollection<Point, LivingCirclePoiProperties>
  data_quality: {
    total_pois: number
    mapped_pois: number
    unmapped_pois: number
    mapped_ratio: number
    reachable_core_pois_15min: number
    displayed_pois: number
    display_limit_per_category: 30
  }
  walking_model: {
    network_type: 'walk'
    cost_model: 'static_walking_time'
    walk_speed_kph: 4.8
    directed: true
    origin_connector_included: true
    poi_connector_included: true
    poi_eligibility: 'network_cost'
    service_area_method: 'reachable_pedestrian_vertex_concave_hull'
  }
}

export type LivingCirclePoiFeature = Feature<Point, LivingCirclePoiProperties>
