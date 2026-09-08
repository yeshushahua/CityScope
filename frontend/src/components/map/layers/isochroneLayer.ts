import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson'
import type { GeoJSONSource, Map } from 'maplibre-gl'
import type { IsochroneProperties, IsochroneResponse } from '../../../types/routing'

export const ISOCHRONE_SOURCE_ID = 'cityscope-isochrones'
export const ISOCHRONE_FILL_15_ID = 'cityscope-isochrone-fill-15'
export const ISOCHRONE_FILL_10_ID = 'cityscope-isochrone-fill-10'
export const ISOCHRONE_FILL_5_ID = 'cityscope-isochrone-fill-5'

const EMPTY: FeatureCollection<Polygon | MultiPolygon, IsochroneProperties> = {
  type: 'FeatureCollection',
  features: [],
}

const BANDS = [
  { minutes: 15, fill: '#4b76c5', opacity: 0.19 },
  { minutes: 10, fill: '#2a9d8f', opacity: 0.24 },
  { minutes: 5, fill: '#f2a93b', opacity: 0.32 },
] as const

export function addIsochroneLayers(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  map.addSource(ISOCHRONE_SOURCE_ID, { type: 'geojson', data: EMPTY })
  for (const band of BANDS) {
    map.addLayer({
      id: `cityscope-isochrone-fill-${band.minutes}`,
      type: 'fill',
      source: ISOCHRONE_SOURCE_ID,
      filter: ['==', ['get', 'minutes'], band.minutes],
      layout: { visibility },
      paint: { 'fill-color': band.fill, 'fill-opacity': band.opacity },
    })
    map.addLayer({
      id: `cityscope-isochrone-outline-${band.minutes}`,
      type: 'line',
      source: ISOCHRONE_SOURCE_ID,
      filter: ['==', ['get', 'minutes'], band.minutes],
      layout: { visibility },
      paint: { 'line-color': band.fill, 'line-width': 2, 'line-opacity': 0.9 },
    })
  }
}

export function setIsochroneData(map: Map, result: IsochroneResponse | null): void {
  ;(map.getSource(ISOCHRONE_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
    result?.isochrones ?? EMPTY,
  )
}

export function setIsochroneVisibility(map: Map, visible: boolean): void {
  const visibility = visible ? 'visible' : 'none'
  for (const band of BANDS) {
    for (const kind of ['fill', 'outline']) {
      const id = `cityscope-isochrone-${kind}-${band.minutes}`
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visibility)
    }
  }
}
