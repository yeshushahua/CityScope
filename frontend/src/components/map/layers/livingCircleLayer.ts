import type { Feature, FeatureCollection, LineString, MultiPolygon, Point, Polygon } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { LivingCircleCategory, LivingCirclePoiProperties, LivingCircleResponse } from '../../../types/livingCircle'
import type { QueryCenter } from '../../../types/spatial'

export const LIVING_AREA_SOURCE_ID = 'cityscope-living-circle-areas'
export const LIVING_RESULT_SOURCE_ID = 'cityscope-living-circle-results'
export const LIVING_POI_LAYER_ID = 'cityscope-living-circle-pois'
export const LIVING_ORIGIN_LAYER_ID = 'cityscope-living-circle-origin'

const EMPTY_AREAS: FeatureCollection<Polygon | MultiPolygon> = { type: 'FeatureCollection', features: [] }
const EMPTY_RESULTS: FeatureCollection<Point | LineString> = { type: 'FeatureCollection', features: [] }
const BANDS = [
  { minutes: 15, color: '#5b78c7', opacity: 0.18 },
  { minutes: 10, color: '#35a493', opacity: 0.23 },
  { minutes: 5, color: '#f0ad43', opacity: 0.31 },
] as const
const CATEGORY_COLORS: Record<LivingCircleCategory, string> = {
  commercial: '#e48a3a', healthcare: '#cf5348', education: '#6477c9',
  recreation: '#369c69', transport: '#568b9f',
}

function resultFeatures(origin: QueryCenter | null, result: LivingCircleResponse | null): FeatureCollection<Point | LineString> {
  const features: Feature<Point | LineString>[] = []
  if (origin) {
    features.push({ type: 'Feature', properties: { kind: 'origin', label: '生活圈中心' }, geometry: { type: 'Point', coordinates: [origin.lon, origin.lat] } })
  }
  if (!result) return { type: 'FeatureCollection', features }
  const snap = result.origin_snap
  features.push({ type: 'Feature', properties: { kind: 'connector' }, geometry: { type: 'LineString', coordinates: [[result.origin.lon, result.origin.lat], [snap.node_lon, snap.node_lat]] } })
  features.push({ type: 'Feature', properties: { kind: 'snap', label: '步行网络吸附节点' }, geometry: { type: 'Point', coordinates: [snap.node_lon, snap.node_lat] } })
  features.push(...result.reachable_pois.features.map((feature) => ({
    ...feature,
    properties: { ...feature.properties, kind: 'poi' },
  })))
  return { type: 'FeatureCollection', features }
}

export function addLivingCircleLayers(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  map.addSource(LIVING_AREA_SOURCE_ID, { type: 'geojson', data: EMPTY_AREAS })
  for (const band of BANDS) {
    map.addLayer({ id: `cityscope-living-circle-fill-${band.minutes}`, type: 'fill', source: LIVING_AREA_SOURCE_ID, filter: ['==', ['get', 'minutes'], band.minutes], layout: { visibility }, paint: { 'fill-color': band.color, 'fill-opacity': band.opacity } })
    map.addLayer({ id: `cityscope-living-circle-line-${band.minutes}`, type: 'line', source: LIVING_AREA_SOURCE_ID, filter: ['==', ['get', 'minutes'], band.minutes], layout: { visibility }, paint: { 'line-color': band.color, 'line-width': 2, 'line-opacity': 0.92 } })
  }
  map.addSource(LIVING_RESULT_SOURCE_ID, { type: 'geojson', data: EMPTY_RESULTS })
  map.addLayer({ id: 'cityscope-living-circle-connector', type: 'line', source: LIVING_RESULT_SOURCE_ID, filter: ['==', ['get', 'kind'], 'connector'], layout: { visibility }, paint: { 'line-color': '#536d67', 'line-width': 2, 'line-dasharray': [2, 2] } })
  map.addLayer({ id: LIVING_POI_LAYER_ID, type: 'circle', source: LIVING_RESULT_SOURCE_ID, filter: ['==', ['get', 'kind'], 'poi'], layout: { visibility }, paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 4, 15, 7],
    'circle-color': [
      'match', ['get', 'category'],
      'commercial', CATEGORY_COLORS.commercial,
      'healthcare', CATEGORY_COLORS.healthcare,
      'education', CATEGORY_COLORS.education,
      'recreation', CATEGORY_COLORS.recreation,
      'transport', CATEGORY_COLORS.transport,
      '#667772',
    ],
    'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.8, 'circle-opacity': 0.96,
  } })
  map.addLayer({ id: LIVING_ORIGIN_LAYER_ID, type: 'circle', source: LIVING_RESULT_SOURCE_ID, filter: ['in', ['get', 'kind'], ['literal', ['origin', 'snap']]], layout: { visibility }, paint: {
    'circle-radius': ['match', ['get', 'kind'], 'origin', 9, 4],
    'circle-color': ['match', ['get', 'kind'], 'origin', '#173f37', '#6f827c'],
    'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5,
  } })
}

export function setLivingCircleData(map: Map, origin: QueryCenter | null, result: LivingCircleResponse | null): void {
  ;(map.getSource(LIVING_AREA_SOURCE_ID) as GeoJSONSource | undefined)?.setData(result?.isochrones ?? EMPTY_AREAS)
  ;(map.getSource(LIVING_RESULT_SOURCE_ID) as GeoJSONSource | undefined)?.setData(resultFeatures(origin, result))
}

export function setLivingCircleVisibility(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  const ids = [
    ...BANDS.flatMap((band) => [`cityscope-living-circle-fill-${band.minutes}`, `cityscope-living-circle-line-${band.minutes}`]),
    'cityscope-living-circle-connector', LIVING_POI_LAYER_ID, LIVING_ORIGIN_LAYER_ID,
  ]
  ids.forEach((id) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visibility) })
}

export function setLivingCircleCategoryFilter(map: Map, categories: LivingCircleCategory[]): void {
  if (!map.getLayer(LIVING_POI_LAYER_ID)) return
  map.setFilter(LIVING_POI_LAYER_ID, [
    'all', ['==', ['get', 'kind'], 'poi'], ['in', ['get', 'category'], ['literal', categories]],
  ])
}

export type LivingCircleMapProperties = LivingCirclePoiProperties & { kind: string; label?: string }
