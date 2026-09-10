import type { PoiCategory } from '../../config/poiCategories'
import type {
  NearbyPoiCollection,
  QueryCenter,
  SpatialQueryStatus,
  SpatialSummary,
} from '../../types/spatial'
import SpatialQueryPanel from '../spatial/SpatialQueryPanel'
import RoutingPanel from '../routing/RoutingPanel'
import EmergencyPanel from '../emergency/EmergencyPanel'
import type { EmergencyResponse, EmergencyStatus, IncidentType } from '../../types/emergency'
import LivingCirclePanel from '../livingCircle/LivingCirclePanel'
import type {
  LivingCircleCategory,
  LivingCircleResponse,
  LivingCircleStatus,
} from '../../types/livingCircle'
import type {
  FacilityPreset,
  IsochroneResponse,
  NearestFacilityResponse,
  RoutingMode,
  RoutingStatus,
  ShortestPathResponse,
  TrafficComparisonResponse,
} from '../../types/routing'
import Icon, { type IconName } from '../ui/Icons'

export type ModuleId = 'overview' | 'spatial' | 'routing' | 'emergency' | 'living-circle'
export interface LayerVisibility {
  pois: boolean
  buildings: boolean
  roads: boolean
  analysis: boolean
  buildings3d: boolean
}

interface SidebarProps {
  activeModule: ModuleId
  onSelect: (moduleId: ModuleId) => void
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
  trafficComparison: TrafficComparisonResponse | null
  nearestResult: NearestFacilityResponse | null
  isochroneResult: IsochroneResponse | null
  onRoutingModeChange: (mode: RoutingMode) => void
  onFacilityPresetChange: (preset: FacilityPreset) => void
  onClearRouting: () => void
  onClearRoutingResult: () => void
  incidentType: IncidentType
  incident: QueryCenter | null
  emergencyStatus: EmergencyStatus
  emergencyResult: EmergencyResponse | null
  onIncidentTypeChange: (value: IncidentType) => void
  onClearEmergency: () => void
  onReselectIncident: () => void
  livingCircleOrigin: QueryCenter | null
  livingCircleStatus: LivingCircleStatus
  livingCircleResult: LivingCircleResponse | null
  livingCircleCategories: LivingCircleCategory[]
  onToggleLivingCircleCategory: (category: LivingCircleCategory) => void
  onClearLivingCircle: () => void
  onReselectLivingCircle: () => void
}

const MODULE_GROUPS: ReadonlyArray<{
  label: string
  items: ReadonlyArray<{ id: ModuleId; label: string; description: string; icon: IconName }>
}> = [
  { label: '地图展示', items: [{ id: 'overview', label: '城市总览', description: '基础数据与 2.5D 建筑', icon: 'map' }] },
  { label: '基础分析', items: [{ id: 'spatial', label: '空间查询', description: '查询真实 POI 与建筑', icon: 'search' }] },
  { label: '出行分析', items: [{ id: 'routing', label: '路径与可达圈', description: '路径、设施与机动车可达圈', icon: 'route' }] },
  { label: '城市业务', items: [
    { id: 'emergency', label: '应急响应', description: '医疗与消防决策支持', icon: 'alert' },
    { id: 'living-circle', label: '15分钟生活圈', description: '步行网络服务可达性', icon: 'walk' },
  ] },
]
const MODULES = MODULE_GROUPS.flatMap((group) => group.items)

export default function Sidebar({
  activeModule,
  onSelect,
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
  trafficComparison,
  nearestResult,
  isochroneResult,
  onRoutingModeChange,
  onFacilityPresetChange,
  onClearRouting,
  onClearRoutingResult,
  incidentType,
  incident,
  emergencyStatus,
  emergencyResult,
  onIncidentTypeChange,
  onClearEmergency,
  onReselectIncident,
  livingCircleOrigin,
  livingCircleStatus,
  livingCircleResult,
  livingCircleCategories,
  onToggleLivingCircleCategory,
  onClearLivingCircle,
  onReselectLivingCircle,
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
        {MODULE_GROUPS.map((group) => <div className="module-group" key={group.label}>
          <span className="module-group__label">{group.label}</span>
          {group.items.map((item) => (
            <button
              className={`module-item${activeModule === item.id ? ' is-active' : ''}`}
              key={item.id}
              onClick={() => onSelect(item.id)}
              type="button"
              aria-current={activeModule === item.id ? 'page' : undefined}
              title={item.description}
            >
              <Icon name={item.icon} />
              <span><strong>{item.label}</strong><small>{item.description}</small></span>
            </button>
          ))}
        </div>)}
      </nav>
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
          trafficComparison={trafficComparison}
          nearestResult={nearestResult}
          isochroneResult={isochroneResult}
          onModeChange={onRoutingModeChange}
          onFacilityPresetChange={onFacilityPresetChange}
          onClear={onClearRouting}
          onClearResult={onClearRoutingResult}
          onFocus={onFocusPoi}
        />
      )}
      {activeModule === 'emergency' && (
        <EmergencyPanel
          incidentType={incidentType}
          status={emergencyStatus}
          incident={incident}
          result={emergencyResult}
          onIncidentTypeChange={onIncidentTypeChange}
          onClear={onClearEmergency}
          onReselect={onReselectIncident}
          onFocus={onFocusPoi}
        />
      )}
      {activeModule === 'living-circle' && (
        <LivingCirclePanel
          origin={livingCircleOrigin}
          status={livingCircleStatus}
          result={livingCircleResult}
          selectedCategories={livingCircleCategories}
          onToggleCategory={onToggleLivingCircleCategory}
          onClear={onClearLivingCircle}
          onReselect={onReselectLivingCircle}
        />
      )}
      <div className="module-note" role="status" aria-live="polite">
        <strong>{activeItem.label}</strong>
        <span>{activeItem.description}</span>
      </div>
      <div className="phase-label">PHASE 9 · THEMATIC VISUALIZATION</div>
    </aside>
  )
}
