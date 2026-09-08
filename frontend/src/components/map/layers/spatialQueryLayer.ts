import type { Feature, FeatureCollection, Point, Polygon } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import { POI_CATEGORY_CONFIG } from '../../../config/poiCategories'
import type { NearbyPoiCollection, QueryCenter } from '../../../types/spatial'

export const SPATIAL_AREA_SOURCE_ID = 'cityscope-query-area'
export const SPATIAL_AREA_FILL_LAYER_ID = 'cityscope-query-area-fill'
export const SPATIAL_AREA_LINE_LAYER_ID = 'cityscope-query-area-line'
export const SPATIAL_CENTER_LAYER_ID = 'cityscope-query-center'
export const SPATIAL_RESULTS_SOURCE_ID = 'cityscope-query-results'
export const SPATIAL_RESULTS_LAYER_ID = 'cityscope-query-results-points'

const EMPTY_AREA: FeatureCollection<Polygon | Point> = { type: 'FeatureCollection', features: [] }
const EMPTY_RESULTS: FeatureCollection<Point> = { type: 'FeatureCollection', features: [] }

function circleFeature(center: QueryCenter, radiusM: number): Feature<Polygon> {
  const earthRadiusM = 6_371_008.8
  const angularDistance = radiusM / earthRadiusM
  const latitude = center.lat * Math.PI / 180
  const longitude = center.lon * Math.PI / 180
  const coordinates: [number, number][] = []
  for (let index = 0; index <= 64; index += 1) {
    const bearing = index / 64 * Math.PI * 2
    const targetLatitude = Math.asin(
      Math.sin(latitude) * Math.cos(angularDistance)
      + Math.cos(latitude) * Math.sin(angularDistance) * Math.cos(bearing),
    )
    const targetLongitude = longitude + Math.atan2(
      Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latitude),
      Math.cos(angularDistance) - Math.sin(latitude) * Math.sin(targetLatitude),
    )
    coordinates.push([targetLongitude * 180 / Math.PI, targetLatitude * 180 / Math.PI])
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [coordinates] } }
}

function queryAreaData(center: QueryCenter | null, radiusM: number): FeatureCollection<Polygon | Point> {
  if (!center) return EMPTY_AREA
  return {
    type: 'FeatureCollection',
    features: [
      circleFeature(center, radiusM),
      { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [center.lon, center.lat] } },
    ],
  }
}

export function addSpatialQueryLayers(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  map.addSource(SPATIAL_AREA_SOURCE_ID, { type: 'geojson', data: EMPTY_AREA })
  map.addLayer({
    id: SPATIAL_AREA_FILL_LAYER_ID,
    type: 'fill',
    source: SPATIAL_AREA_SOURCE_ID,
    filter: ['==', ['geometry-type'], 'Polygon'],
    layout: { visibility },
    paint: { 'fill-color': '#176b5d', 'fill-opacity': 0.12 },
  })
  map.addLayer({
    id: SPATIAL_AREA_LINE_LAYER_ID,
    type: 'line',
    source: SPATIAL_AREA_SOURCE_ID,
    filter: ['==', ['geometry-type'], 'Polygon'],
    layout: { visibility },
    paint: { 'line-color': '#176b5d', 'line-width': 2, 'line-dasharray': [3, 2] },
  })
  map.addLayer({
    id: SPATIAL_CENTER_LAYER_ID,
    type: 'circle',
    source: SPATIAL_AREA_SOURCE_ID,
    filter: ['==', ['geometry-type'], 'Point'],
    layout: { visibility },
    paint: {
      'circle-radius': 7,
      'circle-color': '#102f2a',
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 3,
    },
  })
  map.addSource(SPATIAL_RESULTS_SOURCE_ID, { type: 'geojson', data: EMPTY_RESULTS })
  map.addLayer({
    id: SPATIAL_RESULTS_LAYER_ID,
    type: 'circle',
    source: SPATIAL_RESULTS_SOURCE_ID,
    layout: { visibility },
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 15, 8],
      'circle-color': [
        'match', ['get', 'category'],
        'healthcare', POI_CATEGORY_CONFIG.healthcare.color,
        'emergency', POI_CATEGORY_CONFIG.emergency.color,
        'education', POI_CATEGORY_CONFIG.education.color,
        'public_safety', POI_CATEGORY_CONFIG.public_safety.color,
        'recreation', POI_CATEGORY_CONFIG.recreation.color,
        'transport', POI_CATEGORY_CONFIG.transport.color,
        POI_CATEGORY_CONFIG.commercial.color,
      ],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
      'circle-opacity': 0.96,
    },
  })
}

export function setSpatialQueryData(
  map: Map,
  center: QueryCenter | null,
  radiusM: number,
  results: NearbyPoiCollection | null,
): void {
  ;(map.getSource(SPATIAL_AREA_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
    queryAreaData(center, radiusM),
  )
  ;(map.getSource(SPATIAL_RESULTS_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
    results ?? EMPTY_RESULTS,
  )
}

export function setSpatialQueryVisibility(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  for (const layerId of [
    SPATIAL_AREA_FILL_LAYER_ID,
    SPATIAL_AREA_LINE_LAYER_ID,
    SPATIAL_CENTER_LAYER_ID,
    SPATIAL_RESULTS_LAYER_ID,
  ]) {
    if (map.getLayer(layerId)) map.setLayoutProperty(layerId, 'visibility', visibility)
  }
}
