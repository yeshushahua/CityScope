import type { FeatureCollection, Geometry } from 'geojson'

export interface PoiProperties {
  id: number
  osm_type: string
  osm_id: string
  name: string | null
  category: string
  subcategory: string
  source: string
}

export interface BuildingProperties {
  id: number
  osm_type: string
  osm_id: string
  name: string | null
  building_type: string | null
  area_m2: number
  source: string
}

export interface RoadProperties {
  id: number
  road_edge_id: number
  source: number
  target: number
  osm_id: string
  edge_key: number
  name: string | null
  highway: string | null
  oneway: boolean
  maxspeed: string | null
  speed_kph: number
  speed_source: 'osm' | 'default'
  length_m: number
  travel_time_s: number
  cost: number
  reverse_cost: number
  source_dataset: string
}

export type PoiCollection = FeatureCollection<Geometry, PoiProperties>
export type BuildingCollection = FeatureCollection<Geometry, BuildingProperties>
export type RoadCollection = FeatureCollection<Geometry, RoadProperties>

export interface LayerCounts {
  pois: number
  buildings: number
  roads: number
}
