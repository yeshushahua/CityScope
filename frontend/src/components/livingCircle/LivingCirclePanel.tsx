import type {
  LivingCircleCategory,
  LivingCircleResponse,
  LivingCircleStatus,
} from '../../types/livingCircle'
import type { QueryCenter } from '../../types/spatial'
import DataBars from '../ui/DataBars'
import { LIVING_CATEGORY_COLORS } from '../../config/visualization'
import { formatArea, formatCoordinate, formatCount, formatDistance, formatDuration } from '../../utils/format'

interface Props {
  origin: QueryCenter | null
  status: LivingCircleStatus
  result: LivingCircleResponse | null
  selectedCategories: LivingCircleCategory[]
  onToggleCategory: (category: LivingCircleCategory) => void
  onClear: () => void
  onReselect: () => void
}

const CATEGORY_LABELS: Record<LivingCircleCategory, string> = {
  commercial: '商业服务',
  healthcare: '医疗服务',
  education: '教育服务',
  recreation: '休闲娱乐',
  transport: '公共交通',
}

const STATUS_TEXT: Record<LivingCircleStatus, string> = {
  selecting: '请点击地图设置生活圈中心。',
  loading: '正在沿真实步行网络计算 5 / 10 / 15 分钟生活圈…',
  success: '分析完成；再次点击地图可更换中心。',
  snap_failed: '300 米范围内没有可用的步行网络节点。',
  no_data: '步行网络或 POI 步行映射尚未准备。',
  error: '生活圈分析暂时不可用，请重新选择。',
}

export const LIVING_CIRCLE_CATEGORIES = Object.keys(CATEGORY_LABELS) as LivingCircleCategory[]

export default function LivingCirclePanel({
  origin,
  status,
  result,
  selectedCategories,
  onToggleCategory,
  onClear,
  onReselect,
}: Props) {
  return (
    <section className="living-circle-panel" aria-label="步行十五分钟生活圈分析">
      <div className="living-circle-instruction">
        <span className="section-kicker">15-MINUTE LIVING CIRCLE</span>
        <strong>点击地图设置生活圈中心</strong>
        <span>独立 OSM 步行网络 · 4.8 km/h · 接驳时间计入总时长</span>
      </div>

      <div className="living-origin-row">
        <span>分析中心</span>
        <b>{origin ? `${formatCoordinate(origin.lon)}, ${formatCoordinate(origin.lat)}` : '待选择'}</b>
      </div>
      <p className={`living-message is-${status}`} role="status" aria-live="polite">{STATUS_TEXT[status]}</p>

      <fieldset className="living-category-filter">
        <legend>显示核心服务类别</legend>
        <div>
          {LIVING_CIRCLE_CATEGORIES.map((category) => (
            <label key={category}>
              <input
                type="checkbox"
                checked={selectedCategories.includes(category)}
                onChange={() => onToggleCategory(category)}
              />
              <span>{CATEGORY_LABELS[category]}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {result && status === 'success' && (
        <>
          <div className="living-coverage">
            <span>核心类别覆盖</span>
            <strong>{result.coverage.present_categories} / {result.coverage.total_categories}</strong>
            <small>存在比例 {(result.coverage.presence_ratio * 100).toFixed(0)}%，仅表示类别是否可达</small>
          </div>

          <div className="living-model">
            <span>静态步行速度</span><strong>{result.walking_model.walk_speed_kph.toFixed(1)} km/h</strong>
            <span>起点吸附</span><strong>{formatDistance(result.origin_snap.snap_distance_m)}</strong>
            <span>15分钟可达 POI</span><strong>{formatCount(result.summary.reachable_poi_count)}</strong>
          </div>

          <div className="living-bands">
            {result.isochrones.features.map((feature) => (
              <div className={`living-band is-${feature.properties.minutes}`} key={feature.properties.minutes}>
                <strong>{feature.properties.minutes}分钟</strong>
                <span>{formatCount(feature.properties.reachable_node_count)} 节点</span>
                <b>{formatArea(feature.properties.area_m2)}</b>
              </div>
            ))}
          </div>

          <div className="living-category-stats">
            {result.categories.map((item) => (
              <div key={item.category} className={!selectedCategories.includes(item.category) ? 'is-muted' : ''}>
                <strong>{CATEGORY_LABELS[item.category]}</strong>
                <span>5 / 10 / 15 分钟</span>
                <b>{item.reachable_5min} / {item.reachable_10min} / {item.reachable_poi_count}</b>
                <small>{item.unique_subcategory_count} 子类 · 最近 {item.nearest_poi?.name || '—'} {item.nearest_walk_time_s === null ? '' : formatDuration(item.nearest_walk_time_s)}</small>
              </div>
            ))}
          </div>

          <DataBars
            title="15分钟可达设施类别分布"
            data={result.categories.map((item) => ({
              key: item.category,
              label: CATEGORY_LABELS[item.category],
              value: item.reachable_poi_count,
              color: LIVING_CATEGORY_COLORS[item.category],
            }))}
          />

          <p className="living-quality">
            POI {result.data_quality.total_pois} · 步行映射 {result.data_quality.mapped_pois}
            {' '}({(result.data_quality.mapped_ratio * 100).toFixed(1)}%) · 15分钟可达核心 POI {result.data_quality.reachable_core_pois_15min}
            {' '}· 地图显示 {result.data_quality.displayed_pois}
          </p>
          <p className="model-note"><strong>模型说明</strong>按 4.8 km/h 静态步行速度估算；覆盖率只表示类别存在，不代表主观评价或实时路况。</p>
        </>
      )}

      <div className="living-actions">
        <button type="button" onClick={onReselect} disabled={!origin}>重新选择位置</button>
        <button type="button" onClick={onClear} disabled={!origin && !result}>清除分析</button>
      </div>
    </section>
  )
}
