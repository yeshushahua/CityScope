import type { MapLoadStatus } from '../../types/map'

interface MapStatusProps {
  status: MapLoadStatus
}

export default function MapStatus({ status }: MapStatusProps) {
  if (status === 'ready') return null

  return (
    <div className={`map-state map-state--${status}`} role="status" aria-live="polite">
      {status === 'loading' && <span className="loading-spinner" aria-hidden="true" />}
      <strong>{status === 'loading' ? '地图加载中...' : '地图加载失败'}</strong>
      {status === 'error' && <span>请检查网络连接或底图配置</span>}
    </div>
  )
}
