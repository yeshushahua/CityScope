import type { MapCoordinatesValue } from '../../types/map'

interface MapCoordinatesProps {
  coordinates: MapCoordinatesValue | null
}

export default function MapCoordinates({ coordinates }: MapCoordinatesProps) {
  return (
    <div className="map-coordinates" aria-live="off">
      <span className="coordinate-system">WGS84</span>
      <span>经度：{coordinates ? coordinates.longitude.toFixed(6) : '--'}</span>
      <span>纬度：{coordinates ? coordinates.latitude.toFixed(6) : '--'}</span>
    </div>
  )
}
