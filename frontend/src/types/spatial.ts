import type { FeatureCollection, Point } from 'geojson'
import type { PoiCategory } from '../config/poiCategories'
import type { PoiProperties } from './geojson'

export interface QueryCenter {
  lon: number
  lat: number
}

export interface NearbyPoiProperties extends PoiProperties {
  distance_m: number
}

export interface NearbyPoiCollection extends FeatureCollection<Point, NearbyPoiProperties> {
  meta: {
    center: [number, number]
    radius_m: number
    count: number
  }
}

export interface SpatialSummary {
  center: QueryCenter
  radius_m: number
  pois: {
    total: number
    by_category: Partial<Record<PoiCategory, number>>
  }
  buildings: {
    count: number
    footprint_area_m2: number
  }
}

export type SpatialQueryStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error'

export interface FocusPoint extends QueryCenter {
  requestId: number
}
