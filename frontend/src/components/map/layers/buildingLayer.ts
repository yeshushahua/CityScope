import type { FeatureCollection, Geometry } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { BuildingCollection, BuildingProperties } from '../../../types/geojson'

export const BUILDING_SOURCE_ID = 'cityscope-buildings'
export const BUILDING_FILL_LAYER_ID = 'cityscope-buildings-fill'
export const BUILDING_LINE_LAYER_ID = 'cityscope-buildings-outline'

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
    paint: { 'fill-color': '#d7a765', 'fill-opacity': 0.36 },
  })
  map.addLayer({
    id: BUILDING_LINE_LAYER_ID,
    type: 'line',
    source: BUILDING_SOURCE_ID,
    layout: { visibility },
    paint: { 'line-color': '#9b6d36', 'line-width': 0.8, 'line-opacity': 0.7 },
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
}
