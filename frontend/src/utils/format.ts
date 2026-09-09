const countFormatter = new Intl.NumberFormat('zh-CN')

export function formatCount(value: number): string {
  return countFormatter.format(value)
}

export function formatCoordinate(value: number): string {
  return value.toFixed(5)
}

export function formatDistance(valueM: number): string {
  return valueM >= 1000 ? `${(valueM / 1000).toFixed(2)} km` : `${Math.round(valueM)} m`
}

export function formatDuration(valueS: number): string {
  return valueS >= 60 ? `${(valueS / 60).toFixed(1)} min` : `${Math.round(valueS)} s`
}

export function formatArea(valueM2: number): string {
  return valueM2 >= 1_000_000
    ? `${(valueM2 / 1_000_000).toFixed(2)} km²`
    : `${formatCount(Math.round(valueM2))} m²`
}
