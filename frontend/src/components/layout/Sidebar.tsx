import type { PoiCategory } from '../../config/poiCategories'
import type {
  NearbyPoiCollection,
  QueryCenter,
  SpatialQueryStatus,
  SpatialSummary,
} from '../../types/spatial'
import SpatialQueryPanel from '../spatial/SpatialQueryPanel'
import RoutingPanel from '../routing/RoutingPanel'
import type {
  FacilityPreset,
  NearestFacilityResponse,
  RoutingMode,
  RoutingStatus,
  ShortestPathResponse,
} from '../../types/routing'

export type ModuleId = 'overview' | 'spatial' | 'routing' | 'emergency' | 'accessibility'
export interface LayerVisibility { pois: boolean; buildings: boolean; roads: boolean }

interface SidebarProps {
  activeModule: ModuleId
  onSelect: (moduleId: ModuleId) => void
  layers: LayerVisibility
  onToggleLayer: (layer: keyof LayerVisibility) => void
  databaseOnline: boolean
  layerCounts: { pois: number; buildings: number; roads: number }
  queryCenter: QueryCenter | null
  queryRadiusM: number
  queryCategory: PoiCategory | ''
  queryStatus: SpatialQueryStatus
  nearbyPois: NearbyPoiCollection | null
  spatialSummary: SpatialSummary | null
  onQueryRadiusChange: (radius: number) => void
  onQueryCategoryChange: (category: PoiCategory | '') => void
  onFocusPoi: (lon: number, lat: number) => void
  routingMode: RoutingMode
  routingStatus: RoutingStatus
  routeStart: QueryCenter | null
  routeEnd: QueryCenter | null
  facilityPreset: FacilityPreset
  shortestResult: ShortestPathResponse | null
  nearestResult: NearestFacilityResponse | null
  onRoutingModeChange: (mode: RoutingMode) => void
  onFacilityPresetChange: (preset: FacilityPreset) => void
  onClearRouting: () => void
  onClearRoutingResult: () => void
}

const MODULES: ReadonlyArray<{ id: ModuleId; label: string; description: string }> = [
  { id: 'overview', label: '城市总览', description: '浏览兰州市基础地图' },
  { id: 'spatial', label: '空间查询', description: '按点击位置执行 PostGIS 范围查询' },
  { id: 'routing', label: '路径规划', description: '计算最短时间路径与最快可达设施' },
  { id: 'emergency', label: '应急响应', description: '功能将在后续阶段开放' },
  { id: 'accessibility', label: '可达性分析', description: '功能将在后续阶段开放' },
]

export default function Sidebar({
  activeModule,
  onSelect,
  layers,
  onToggleLayer,
  databaseOnline,
  layerCounts,
  queryCenter,
  queryRadiusM,
  queryCategory,
  queryStatus,
  nearbyPois,
  spatialSummary,
  onQueryRadiusChange,
  onQueryCategoryChange,
  onFocusPoi,
  routingMode,
  routingStatus,
  routeStart,
  routeEnd,
  facilityPreset,
  shortestResult,
  nearestResult,
  onRoutingModeChange,
  onFacilityPresetChange,
  onClearRouting,
  onClearRoutingResult,
}: SidebarProps) {
  const activeItem = MODULES.find((item) => item.id === activeModule) ?? MODULES[0]

  return (
    <aside className="sidebar" aria-label="功能模块">
      <div className="sidebar-heading">
        <span>WORKSPACE</span>
        <h2>兰州市主城区</h2>
        <p>WGS84 · 基础城市地图</p>
      </div>
      <nav className="module-nav" aria-label="CityScope 模块">
        {MODULES.map((item, index) => (
          <button
            className={`module-item${activeModule === item.id ? ' is-active' : ''}`}
            key={item.id}
            onClick={() => onSelect(item.id)}
            type="button"
            aria-current={activeModule === item.id ? 'page' : undefined}
          >
            <span className="module-number">0{index + 1}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      {activeModule === 'overview' && <section className="layer-panel" aria-label="地图图层">
        <span className="section-kicker">MAP LAYERS</span>
        <label className="layer-toggle">
          <input type="checkbox" checked={layers.roads} onChange={() => onToggleLayer('roads')} />
          <span>有向道路网络</span>
          <b>{layerCounts.roads.toLocaleString()}</b>
        </label>
        <label className="layer-toggle">
          <input type="checkbox" checked={layers.pois} onChange={() => onToggleLayer('pois')} />
          <span>兴趣点 POI</span>
          <b>{layerCounts.pois.toLocaleString()}</b>
        </label>
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={layers.buildings}
            onChange={() => onToggleLayer('buildings')}
          />
          <span>建筑轮廓</span>
          <b>{layerCounts.buildings.toLocaleString()}</b>
        </label>
        <p className="layer-hint">路网在缩放级别 13、建筑在 14 以上按当前视窗加载</p>
      </section>}
      {activeModule === 'spatial' && (
        <SpatialQueryPanel
          center={queryCenter}
          radiusM={queryRadiusM}
          category={queryCategory}
          status={queryStatus}
          nearby={nearbyPois}
          summary={spatialSummary}
          onRadiusChange={onQueryRadiusChange}
          onCategoryChange={onQueryCategoryChange}
          onFocusPoi={onFocusPoi}
        />
      )}
      {activeModule === 'routing' && (
        <RoutingPanel
          mode={routingMode}
          status={routingStatus}
          start={routeStart}
          end={routeEnd}
          facilityPreset={facilityPreset}
          shortestResult={shortestResult}
          nearestResult={nearestResult}
          onModeChange={onRoutingModeChange}
          onFacilityPresetChange={onFacilityPresetChange}
          onClear={onClearRouting}
          onClearResult={onClearRoutingResult}
          onFocus={onFocusPoi}
        />
      )}
      <div className={`database-status${databaseOnline ? ' is-online' : ''}`} role="status">
        <span className="status-dot" aria-hidden="true" />
        PostGIS {databaseOnline ? 'Connected' : 'Unavailable'}
      </div>
      {activeModule !== 'spatial' && activeModule !== 'routing' && <div className="module-note" role="status" aria-live="polite">
        <strong>{activeItem.label}</strong>
        <span>{activeItem.description}</span>
      </div>}
      <div className="phase-label">PHASE 5 · ROUTING APPLICATION</div>
    </aside>
  )
}
