import type { QueryCenter } from '../../types/spatial'
import type {
  FacilityPreset,
  IsochroneResponse,
  NearestFacilityResponse,
  RoutingMode,
  RoutingStatus,
  ShortestPathResponse,
} from '../../types/routing'
import { formatArea, formatCoordinate, formatCount, formatDistance, formatDuration } from '../../utils/format'

interface RoutingPanelProps {
  mode: RoutingMode
  status: RoutingStatus
  start: QueryCenter | null
  end: QueryCenter | null
  facilityPreset: FacilityPreset
  shortestResult: ShortestPathResponse | null
  nearestResult: NearestFacilityResponse | null
  isochroneResult: IsochroneResponse | null
  onModeChange: (mode: RoutingMode) => void
  onFacilityPresetChange: (preset: FacilityPreset) => void
  onClear: () => void
  onClearResult: () => void
  onFocus: (lon: number, lat: number) => void
}

const MESSAGE: Record<RoutingStatus, string> = {
  idle: '路线已清除；点击地图可选择新起点。',
  selecting_start: '请在地图上选择起点。',
  selecting_end: '起点已选择，请在地图上选择终点。',
  loading: '正在吸附路网并计算最短时间路径…',
  success: '计算完成。可点击候选设施或地图结果查看详情。',
  no_route: '两个吸附节点之间不存在可通行路径。',
  snap_failed: '500 米范围内未找到可吸附的路网节点。',
  empty_facilities: '没有找到符合条件且可达的设施。',
  error: '路径服务暂时不可用，请重新选择。',
}

function PointValue({ label, point }: { label: string; point: QueryCenter | null }) {
  return (
    <div className="route-point-row">
      <span>{label}</span>
      <b>{point ? `${formatCoordinate(point.lon)}, ${formatCoordinate(point.lat)}` : '待选择'}</b>
    </div>
  )
}

export default function RoutingPanel({
  mode,
  status,
  start,
  end,
  facilityPreset,
  shortestResult,
  nearestResult,
  isochroneResult,
  onModeChange,
  onFacilityPresetChange,
  onClear,
  onClearResult,
  onFocus,
}: RoutingPanelProps) {
  const route = mode === 'shortest' ? shortestResult?.route : nearestResult?.route
  const statusMessage = mode === 'isochrone'
    ? status === 'loading'
      ? '正在吸附路网并计算 5 / 10 / 15 分钟可达圈…'
      : status === 'success'
        ? '可达圈计算完成；再次点击地图可更新起点。'
        : status === 'idle'
          ? '结果已清除；点击地图可选择新起点。'
          : status === 'error'
            ? '可达圈服务暂时不可用，请重新选择。'
            : MESSAGE[status]
    : MESSAGE[status]
  return (
    <section className="routing-panel" aria-label="路径规划">
      <div className="routing-mode" role="group" aria-label="规划模式">
        <button className={mode === 'shortest' ? 'is-active' : ''} onClick={() => onModeChange('shortest')} type="button">点到点</button>
        <button className={mode === 'nearest' ? 'is-active' : ''} onClick={() => onModeChange('nearest')} type="button">最近设施</button>
        <button className={mode === 'isochrone' ? 'is-active' : ''} onClick={() => onModeChange('isochrone')} type="button">可达圈</button>
      </div>

      {mode === 'nearest' && (
        <label className="facility-selector">
          <span>设施类型</span>
          <select value={facilityPreset} onChange={(event) => onFacilityPresetChange(event.target.value as FacilityPreset)}>
            <option value="hospital">医院</option>
            <option value="healthcare">全部医疗设施</option>
            <option value="fire_station">消防站</option>
          </select>
        </label>
      )}

      <div className="routing-instruction">
        <span className="section-kicker">NETWORK ROUTING</span>
        <strong>{mode === 'shortest' ? '依次点击起点和终点' : mode === 'nearest' ? '点击位置查找最快可达设施' : '点击位置计算道路时间可达圈'}</strong>
        <span>{mode === 'isochrone' ? '5 / 10 / 15 分钟 · 最大吸附距离 500 m' : '按道路通行时间排序 · 最大吸附距离 500 m'}</span>
      </div>

      <PointValue label={mode === 'nearest' ? '当前位置' : '起点'} point={start} />
      {mode === 'shortest' && <PointValue label="终点" point={end} />}
      <p className={`route-message is-${status}`} role="status" aria-live="polite">{statusMessage}</p>

      {route && status === 'success' && (
        <div className="route-metrics">
          <div><span>路网距离</span><strong>{formatDistance(route.properties.routing_distance_m)}</strong></div>
          <div><span>预计时间</span><strong>{formatDuration(route.properties.travel_time_s)}</strong></div>
          <div><span>道路边数</span><strong>{formatCount(route.properties.edge_count)}</strong></div>
          {mode === 'shortest' && shortestResult && (
            <div><span>吸附距离</span><strong>{formatDistance(shortestResult.start_snap.snap_distance_m)} / {formatDistance(shortestResult.end_snap.snap_distance_m)}</strong></div>
          )}
        </div>
      )}

      {mode === 'nearest' && nearestResult && status === 'success' && (
        <div className="facility-results">
          <div className="facility-best">
            <span>最快可达</span>
            <strong>{nearestResult.best.name || '未命名设施'}</strong>
            <small>{nearestResult.best.category} / {nearestResult.best.subcategory}</small>
            <small>路网 {formatDistance(nearestResult.best.network_distance_m)} · 直线 {formatDistance(nearestResult.best.straight_distance_m)}</small>
            <small>预计 {formatDuration(nearestResult.best.travel_time_s)} · 设施吸附 {formatDistance(nearestResult.best.facility_snap_distance_m)}</small>
          </div>
          <div className="candidate-list">
            {nearestResult.candidates.map((candidate) => (
              <button key={candidate.poi_id} type="button" onClick={() => onFocus(candidate.lon, candidate.lat)}>
                <span><b>#{candidate.rank} {candidate.name || '未命名设施'}</b><small>路网 {formatDistance(candidate.network_distance_m)} · 直线 {formatDistance(candidate.straight_distance_m)}</small></span>
                <strong>{formatDuration(candidate.travel_time_s)}</strong>
              </button>
            ))}
          </div>
          <p className="facility-meta">已映射 {nearestResult.meta.mapped_count} · 可达 {nearestResult.meta.reachable_count} · 不可达 {nearestResult.meta.unreachable_count}</p>
        </div>
      )}

      {mode === 'isochrone' && isochroneResult && status === 'success' && (
        <div className="isochrone-results">
          <div className="isochrone-snap">
            <span>起点吸附距离</span>
            <strong>{formatDistance(isochroneResult.snap.snap_distance_m)}</strong>
          </div>
          <div className="isochrone-band-list">
            {isochroneResult.isochrones.features.map((feature) => (
              <div className={`isochrone-band is-${feature.properties.minutes}`} key={feature.properties.minutes}>
                <strong>{feature.properties.minutes} 分钟</strong>
                <span>{formatCount(feature.properties.reachable_node_count)} 个节点</span>
                <b>{formatArea(feature.properties.area_m2)}</b>
              </div>
            ))}
          </div>
          <p className="model-note"><strong>模型说明</strong>基于静态道路等级速度估算，不含实时交通；边界为可达顶点近似范围。</p>
        </div>
      )}

      <div className="route-actions">
        <button className="route-clear" type="button" onClick={onClear} disabled={!start && status === 'selecting_start'}>重新选择</button>
        <button className="route-clear" type="button" onClick={onClearResult} disabled={!shortestResult && !nearestResult && !isochroneResult}>清除结果</button>
      </div>
    </section>
  )
}
