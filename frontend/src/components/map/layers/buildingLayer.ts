import type { FeatureCollection, Geometry } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { BuildingCollection, BuildingProperties } from '../../../types/geojson'

export const BUILDING_SOURCE_ID = 'cityscope-buildings'
export const BUILDING_FILL_LAYER_ID = 'cityscope-buildings-fill'
export const BUILDING_LINE_LAYER_ID = 'cityscope-buildings-outline'
export const BUILDING_EXTRUSION_LAYER_ID = 'cityscope-buildings-extrusion'

const EMPTY_DATA: FeatureCollection<Geometry, BuildingProperties> = {
  type: 'FeatureCollection',
  features: [],
}

export function addBuildingLayer(map: Map, visible: boolean): void {
  map.addSource(BUILDING_SOURCE_ID, { type: 'geojson', data: EMPTY_DATA })
  const visibility = visible ? 'visible' : 'none'
  map.addLayer({
    id: BUILDING_FILL_LAYER_ID,
    type: 'fill',
    source: BUILDING_SOURCE_ID,
    layout: { visibility },
    paint: {
      'fill-color': [
        'match', ['get', 'height_source'],
        'osm_height', '#4e7b78',
        'levels_estimate', '#b68a55',
        '#8e9b98',
      ],
      'fill-opacity': 0.3,
    },
  })
  map.addLayer({
    id: BUILDING_LINE_LAYER_ID,
    type: 'line',
    source: BUILDING_SOURCE_ID,
    layout: { visibility },
    paint: { 'line-color': '#5f706c', 'line-width': 0.8, 'line-opacity': 0.72 },
  })
  map.addLayer({
    id: BUILDING_EXTRUSION_LAYER_ID,
    type: 'fill-extrusion',
    source: BUILDING_SOURCE_ID,
    filter: ['>', ['coalesce', ['get', 'display_height_m'], 0], 0],
    minzoom: 14,
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': [
        'match', ['get', 'height_source'],
        'osm_height', '#3f716e',
        'levels_estimate', '#bd8c52',
        '#8e9b98',
      ],
      'fill-extrusion-height': ['coalesce', ['get', 'display_height_m'], 0],
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.78,
      'fill-extrusion-vertical-gradient': true,
    },
  })
}

export function setBuildingData(map: Map, data: BuildingCollection): void {
  ;(map.getSource(BUILDING_SOURCE_ID) as GeoJSONSource | undefined)?.setData(data)
}

export function setBuildingVisibility(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  for (const layerId of [BUILDING_FILL_LAYER_ID, BUILDING_LINE_LAYER_ID]) {
    if (map.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', visibility)
  }
  if (!visible && map.getLayer(BUILDING_EXTRUSION_LAYER_ID)) {
    map.setLayoutProperty(BUILDING_EXTRUSION_LAYER_ID, 'visibility', 'none')
  }
}

export function setBuildingMode(map: Map, visible: boolean, use3d: boolean): void {
  if (!map.getLayer(BUILDING_FILL_LAYER_ID)) return
  map.setLayoutProperty(BUILDING_FILL_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
  map.setFilter(
    BUILDING_FILL_LAYER_ID,
    use3d ? ['==', ['get', 'height_source'], 'unknown'] : null,
  )
  map.setLayoutProperty(BUILDING_LINE_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
  map.setLayoutProperty(
    BUILDING_EXTRUSION_LAYER_ID,
    'visibility',
    visible && use3d ? 'visible' : 'none',
  )
}
