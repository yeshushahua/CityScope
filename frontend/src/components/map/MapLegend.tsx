import { POI_CATEGORY_CONFIG } from '../../config/poiCategories'
import { ISOCHRONE_COLORS, LIVING_CATEGORY_COLORS, MAP_COLORS } from '../../config/visualization'
import type { LivingCircleCategory } from '../../types/livingCircle'
import type { CSSProperties } from 'react'
import type { RoutingMode } from '../../types/routing'
import type { ModuleId } from '../layout/Sidebar'

interface LegendItem { label: string; color: string; shape?: 'line' | 'dash' | 'area' | 'point' }

const bands: LegendItem[] = ([5, 10, 15] as const).map((minutes) => ({
  label: `${minutes} min`, color: ISOCHRONE_COLORS[minutes], shape: 'area',
}))

function itemsFor(module: ModuleId, routingMode: RoutingMode, livingCategories: LivingCircleCategory[]): LegendItem[] {
  if (module === 'spatial') return [
    { label: '查询中心', color: MAP_COLORS.origin, shape: 'point' },
    { label: '查询范围', color: ISOCHRONE_COLORS[10], shape: 'area' },
    { label: '范围内 POI', color: '#256f85', shape: 'point' },
  ]
  if (module === 'routing') {
    if (routingMode === 'isochrone') return [
      { label: '起点', color: MAP_COLORS.origin, shape: 'point' }, ...bands,
    ]
    return [
      { label: '起点', color: MAP_COLORS.origin, shape: 'point' },
      { label: routingMode === 'nearest' ? '可达设施' : '终点', color: MAP_COLORS.destination, shape: 'point' },
      { label: '规划路线', color: MAP_COLORS.route, shape: 'line' },
      { label: '吸附连接', color: MAP_COLORS.connector, shape: 'dash' },
    ]
  }
  if (module === 'emergency') return [
    { label: '事件点', color: MAP_COLORS.destination, shape: 'point' },
    { label: '推荐设施', color: MAP_COLORS.responder, shape: 'point' },
    { label: '候选设施', color: MAP_COLORS.candidate, shape: 'point' },
    { label: '响应路线', color: MAP_COLORS.emergencyRoute, shape: 'line' },
    ...bands,
  ]
  if (module === 'living-circle') return [
    { label: '居住点', color: MAP_COLORS.origin, shape: 'point' },
    ...bands,
    ...Object.entries(LIVING_CATEGORY_COLORS).filter(([key]) => livingCategories.includes(key as LivingCircleCategory)).map(([key, color]) => ({
      label: ({ commercial: '商业', healthcare: '医疗', education: '教育', recreation: '休闲', transport: '交通' } as Record<LivingCircleCategory, string>)[key as LivingCircleCategory],
      color, shape: 'point' as const,
    })),
  ]
  return Object.values(POI_CATEGORY_CONFIG).map((item) => ({ label: item.label, color: item.color, shape: 'point' }))
}

export default function MapLegend({ module, routingMode, building3d, livingCategories }: { module: ModuleId; routingMode: RoutingMode; building3d: boolean; livingCategories: LivingCircleCategory[] }) {
  const items = itemsFor(module, routingMode, livingCategories)
  return (
    <section className="map-legend" aria-label="动态图例">
      <div className="map-overlay-title"><span>图例</span><small>{module === 'overview' ? '基础数据' : '当前分析'}</small></div>
      <div className="legend-grid">
        {items.map((item) => <div className="legend-item" key={item.label}>
          <i className={`is-${item.shape ?? 'point'}`} style={{ '--legend-color': item.color } as CSSProperties} />
          <span>{item.label}</span>
        </div>)}
      </div>
      {building3d && <div className="height-legend">
        <span><i className="is-osm" />OSM 高度</span>
        <span><i className="is-levels" />楼层估算</span>
        <span><i className="is-unknown" />未知高度（平面）</span>
      </div>}
    </section>
  )
}
