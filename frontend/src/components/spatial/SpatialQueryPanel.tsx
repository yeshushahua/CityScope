import {
  POI_CATEGORIES,
  POI_CATEGORY_CONFIG,
  categoryLabel,
  type PoiCategory,
} from '../../config/poiCategories'
import type {
  NearbyPoiCollection,
  QueryCenter,
  SpatialQueryStatus,
  SpatialSummary,
} from '../../types/spatial'

const RADII = [500, 1000, 2000, 3000] as const

interface SpatialQueryPanelProps {
  center: QueryCenter | null
  radiusM: number
  category: PoiCategory | ''
  status: SpatialQueryStatus
  nearby: NearbyPoiCollection | null
  summary: SpatialSummary | null
  onRadiusChange: (radius: number) => void
  onCategoryChange: (category: PoiCategory | '') => void
  onFocusPoi: (lon: number, lat: number) => void
}

export default function SpatialQueryPanel({
  center,
  radiusM,
  category,
  status,
  nearby,
  summary,
  onRadiusChange,
  onCategoryChange,
  onFocusPoi,
}: SpatialQueryPanelProps) {
  return (
    <section className="spatial-panel" aria-label="空间查询控制">
      <div className="spatial-instruction">
        <span className="section-kicker">SPATIAL QUERY</span>
        <strong>{center ? '查询中心已选择' : '点击地图选择查询中心'}</strong>
        <span>
          {center
            ? `${center.lon.toFixed(6)}, ${center.lat.toFixed(6)}`
            : '距离与范围统计由 PostGIS 实时计算'}
        </span>
      </div>

      <fieldset className="radius-selector">
        <legend>查询半径</legend>
        <div>
          {RADII.map((radius) => (
            <button
              className={radiusM === radius ? 'is-active' : ''}
              key={radius}
              type="button"
              onClick={() => onRadiusChange(radius)}
            >
              {radius >= 1000 ? `${radius / 1000} km` : `${radius} m`}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="category-filter">
        <span>设施分类</span>
        <select
          value={category}
          onChange={(event) => onCategoryChange(event.target.value as PoiCategory | '')}
        >
          <option value="">全部类别</option>
          {POI_CATEGORIES.map((item) => (
            <option value={item} key={item}>{POI_CATEGORY_CONFIG[item].label}</option>
          ))}
        </select>
      </label>

      {status === 'idle' && <p className="query-message">在地图中点击任意位置开始查询。</p>}
      {status === 'loading' && <p className="query-message is-loading">正在查询 PostGIS…</p>}
      {status === 'error' && <p className="query-message is-error">空间查询失败，请重试。</p>}

      {summary && (status === 'success' || status === 'empty') && (
        <>
          <div className="summary-grid" aria-label="范围统计">
            <div><span>附近 POI</span><strong>{summary.pois.total.toLocaleString()}</strong></div>
            <div><span>相交建筑</span><strong>{summary.buildings.count.toLocaleString()}</strong></div>
            <div className="summary-wide">
              <span>范围内建筑占地</span>
              <strong>{Math.round(summary.buildings.footprint_area_m2).toLocaleString()} m²</strong>
            </div>
          </div>
          <div className="category-summary" aria-label="POI 分类统计">
            {Object.entries(summary.pois.by_category).map(([item, count]) => (
              <div key={item}>
                <i style={{ background: POI_CATEGORY_CONFIG[item as PoiCategory]?.color }} />
                <span>{categoryLabel(item)}</span>
                <b>{count}</b>
              </div>
            ))}
          </div>
        </>
      )}

      {status === 'empty' && <p className="query-message">当前筛选范围内没有 POI。</p>}
      {nearby && nearby.features.length > 0 && (
        <div className="nearby-list" aria-label="附近设施列表">
          <div className="nearby-list-heading">
            <strong>附近设施</strong>
            <span>{nearby.meta.count} 个结果</span>
          </div>
          {nearby.features.slice(0, 8).map((feature) => {
            const [lon, lat] = feature.geometry.coordinates
            return (
              <button
                key={feature.properties.id}
                type="button"
                onClick={() => onFocusPoi(lon, lat)}
              >
                <span>
                  <strong>{feature.properties.name || '未命名设施'}</strong>
                  <small>{categoryLabel(feature.properties.category)}</small>
                </span>
                <b>{Math.round(feature.properties.distance_m)} m</b>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
