import type { EmergencyResponse, EmergencyStatus, IncidentType } from '../../types/emergency'
import type { QueryCenter } from '../../types/spatial'
import { formatArea, formatCoordinate, formatCount, formatDistance, formatDuration } from '../../utils/format'

interface EmergencyPanelProps {
  incidentType: IncidentType
  status: EmergencyStatus
  incident: QueryCenter | null
  result: EmergencyResponse | null
  onIncidentTypeChange: (value: IncidentType) => void
  onClear: () => void
  onReselect: () => void
  onFocus: (lon: number, lat: number) => void
}

const STATUS_TEXT: Record<EmergencyStatus, string> = {
  idle: '事件已清除。',
  selecting: '请点击地图设置事件位置。',
  loading: '正在计算应急设施响应方案…',
  success: '响应分析完成；再次点击地图可更新事件位置。',
  snap_failed: '500 米范围内未找到可吸附的道路节点。',
  no_facilities: '没有符合条件且可达的应急设施。',
  error: '应急分析服务暂时不可用，请重新选择。',
}

export default function EmergencyPanel({
  incidentType,
  status,
  incident,
  result,
  onIncidentTypeChange,
  onClear,
  onReselect,
  onFocus,
}: EmergencyPanelProps) {
  return (
    <section className="emergency-panel" aria-label="应急响应决策支持">
      <div className="emergency-type" role="group" aria-label="事件类型">
        <button className={incidentType === 'medical' ? 'is-active' : ''} type="button" onClick={() => onIncidentTypeChange('medical')}>医疗事件</button>
        <button className={incidentType === 'fire' ? 'is-active' : ''} type="button" onClick={() => onIncidentTypeChange('fire')}>消防事件</button>
      </div>

      <div className="emergency-instruction">
        <span className="section-kicker">EMERGENCY RESPONSE</span>
        <strong>点击地图设置事件位置</strong>
        <span>按设施 → 事件点的有向道路时间推荐响应设施</span>
      </div>

      <div className="incident-row">
        <span>事件位置</span>
        <b>{incident ? `${formatCoordinate(incident.lon)}, ${formatCoordinate(incident.lat)}` : '待选择'}</b>
      </div>
      <p className={`emergency-message is-${status}`} role="status" aria-live="polite">{STATUS_TEXT[status]}</p>

      {result && status === 'success' && (
        <>
          <div className="emergency-metrics">
            <div><span>事件吸附</span><strong>{formatDistance(result.incident_snap.snap_distance_m)}</strong></div>
            <div><span>预计响应</span><strong>{formatDuration(result.response_route.properties.response_time_s)}</strong></div>
            <div><span>道路距离</span><strong>{formatDistance(result.response_route.properties.network_distance_m)}</strong></div>
            <div><span>道路边数</span><strong>{formatCount(result.response_route.properties.edge_count)}</strong></div>
          </div>

          <div className="responder-best">
            <span>推荐响应设施</span>
            <strong>{result.recommended_facility.name || '未命名设施'}</strong>
            <small>{result.recommended_facility.category} / {result.recommended_facility.subcategory}</small>
            <small>设施 → 事件点 · {formatDuration(result.recommended_facility.response_time_s)}</small>
          </div>

          {!result.comparison.straight_nearest_is_network_best && (
            <p className="network-comparison">道路时间最优设施并非直线距离最近设施</p>
          )}

          <div className="responder-list">
            {result.candidate_facilities.map((candidate) => (
              <button key={candidate.poi_id} type="button" onClick={() => onFocus(candidate.lon, candidate.lat)}>
                <span><b>#{candidate.network_rank} {candidate.name || '未命名设施'}</b><small>直线 {formatDistance(candidate.straight_distance_m)}</small></span>
                <strong>{formatDuration(candidate.response_time_s)}</strong>
              </button>
            ))}
          </div>

          <div className="response-bands">
            {result.response_isochrones.features.map((feature) => (
              <div className={`response-band is-${feature.properties.minutes}`} key={feature.properties.minutes}>
                <strong>{feature.properties.minutes}分钟</strong>
                <span>{formatCount(feature.properties.reachable_node_count)} 节点</span>
                <b>{formatArea(feature.properties.area_m2)}</b>
              </div>
            ))}
          </div>
          <p className="facility-statistics">设施 {result.facility_statistics.total} · 已映射 {result.facility_statistics.mapped} · 可达 {result.facility_statistics.reachable} · 不可达 {result.facility_statistics.unreachable}</p>
          <p className="model-note"><strong>模型说明</strong>基于静态有向道路网络，用于空间决策演示，不代表真实出警时间。</p>
        </>
      )}

      <div className="emergency-actions">
        <button type="button" onClick={onReselect} disabled={!incident}>重新选择位置</button>
        <button type="button" onClick={onClear} disabled={!incident && !result}>清除事件</button>
      </div>
    </section>
  )
}
