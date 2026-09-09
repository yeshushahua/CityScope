export interface MapCoordinatesValue {
  longitude: number
  latitude: number
}

export type MapLoadStatus = 'loading' | 'ready' | 'error'
export type MapViewMode = '2d' | '3d'
