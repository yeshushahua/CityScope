import type { FeatureCollection, Geometry } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { PoiCollection, PoiProperties } from '../../../types/geojson'
import { POI_CATEGORY_CONFIG } from '../../../config/poiCategories'

export const POI_SOURCE_ID = 'cityscope-pois'
export const POI_LAYER_ID = 'cityscope-pois-symbols'

const EMPTY_DATA: FeatureCollection<Geometry, PoiProperties> = {
  type: 'FeatureCollection',
  features: [],
}

export function addPoiLayer(map: Map, visible: boolean): void {
  map.addSource(POI_SOURCE_ID, { type: 'geojson', data: EMPTY_DATA })
  map.addLayer({
    id: POI_LAYER_ID,
    type: 'circle',
    source: POI_SOURCE_ID,
    layout: { visibility: visible ? 'visible' : 'none' },
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 3.5, 14, 7],
      'circle-color': [
        'match',
        ['get', 'category'],
        'healthcare', POI_CATEGORY_CONFIG.healthcare.color,
        'emergency', POI_CATEGORY_CONFIG.emergency.color,
        'education', POI_CATEGORY_CONFIG.education.color,
        'public_safety', POI_CATEGORY_CONFIG.public_safety.color,
        'recreation', POI_CATEGORY_CONFIG.recreation.color,
        'transport', POI_CATEGORY_CONFIG.transport.color,
        POI_CATEGORY_CONFIG.commercial.color,
      ],
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.9,
    },
  })
}

export function setPoiData(map: Map, data: PoiCollection): void {
  ;(map.getSource(POI_SOURCE_ID) as GeoJSONSource | undefined)?.setData(data)
}

export function setPoiVisibility(map: Map, visible: boolean): void {
  if (map.getLayer(POI_LAYER_ID)) {
    map.setLayoutProperty(POI_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
  }
}
