import type { FeatureCollection, Geometry } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { RoadCollection, RoadProperties } from '../../../types/geojson'

export const ROAD_SOURCE_ID = 'cityscope-routing-edges'
export const ROAD_LAYER_ID = 'cityscope-routing-edges-line'

const EMPTY_DATA: FeatureCollection<Geometry, RoadProperties> = {
  type: 'FeatureCollection',
  features: [],
}

export function addRoadLayer(map: Map, visible: boolean): void {
  map.addSource(ROAD_SOURCE_ID, { type: 'geojson', data: EMPTY_DATA })
  map.addLayer({
    id: ROAD_LAYER_ID,
    type: 'line',
    source: ROAD_SOURCE_ID,
    minzoom: 13,
    layout: {
      visibility: visible ? 'visible' : 'none',
      'line-cap': 'round',
      'line-join': 'round',
    },
    paint: {
      'line-color': [
        'match', ['get', 'highway'],
        'motorway', '#d15b47',
        'trunk', '#d98246',
        'primary', '#d7a246',
        'secondary', '#63938a',
        'tertiary', '#5c827b',
        '#78918c',
      ],
      'line-width': [
        'interpolate', ['linear'], ['zoom'],
        13, ['match', ['get', 'highway'], 'motorway', 2.8, 'trunk', 2.4, 'primary', 2, 1],
        17, ['match', ['get', 'highway'], 'motorway', 7, 'trunk', 6, 'primary', 5, 3],
      ],
      'line-opacity': 0.82,
    },
  })
}

export function setRoadData(map: Map, data: RoadCollection): void {
  ;(map.getSource(ROAD_SOURCE_ID) as GeoJSONSource | undefined)?.setData(data)
}

export function setRoadVisibility(map: Map, visible: boolean): void {
  if (map.getLayer(ROAD_LAYER_ID)) {
    map.setLayoutProperty(ROAD_LAYER_ID, 'visibility', visible ? 'visible' : 'none')
  }
}
