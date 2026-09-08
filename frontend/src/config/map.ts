import type { LngLatLike } from 'maplibre-gl'

export const DEFAULT_CENTER: LngLatLike = [103.8343, 36.0611]
export const DEFAULT_ZOOM = 11
export const DEFAULT_PITCH = 0
export const DEFAULT_BEARING = 0
export const MAP_STYLE_URL =
  import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty'
