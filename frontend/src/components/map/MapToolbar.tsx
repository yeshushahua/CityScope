import type { LayerCounts } from '../../types/geojson'
import type { MapViewMode } from '../../types/map'
import Icon from '../ui/Icons'
import type { LayerVisibility } from '../layout/Sidebar'

interface Props {
  layers: LayerVisibility
  counts: LayerCounts
  viewMode: MapViewMode
  onToggleLayer: (layer: keyof LayerVisibility) => void
  onViewModeChange: (mode: MapViewMode) => void
  onResetView: () => void
}

export default function MapToolbar({ layers, counts, viewMode, onToggleLayer, onViewModeChange, onResetView }: Props) {
  return (
    <div className="map-tools" aria-label="地图工具">
      <div className="view-switch" role="group" aria-label="地图视图">
        <button type="button" className={viewMode === '2d' ? 'is-active' : ''} aria-pressed={viewMode === '2d'} onClick={() => onViewModeChange('2d')}>2D</button>
        <button type="button" className={viewMode === '3d' ? 'is-active' : ''} aria-pressed={viewMode === '3d'} onClick={() => onViewModeChange('3d')}><Icon name="cube" size={14}/>3D</button>
      </div>
      <details className="layer-manager">
        <summary><Icon name="layers" size={15}/>图层</summary>
        <div className="layer-manager__body">
          <label><input aria-label="显示基础 POI" type="checkbox" checked={layers.pois} onChange={() => onToggleLayer('pois')} /><span>基础 POI</span><b>{counts.pois.toLocaleString()}</b></label>
          <label><input aria-label="显示建筑" type="checkbox" checked={layers.buildings} onChange={() => onToggleLayer('buildings')} /><span>建筑</span><b>{counts.buildings.toLocaleString()}</b></label>
          <label><input aria-label="显示道路网络" type="checkbox" checked={layers.roads} onChange={() => onToggleLayer('roads')} /><span>道路网络</span><b>{counts.roads.toLocaleString()}</b></label>
          <label><input aria-label="显示当前分析结果" type="checkbox" checked={layers.analysis} onChange={() => onToggleLayer('analysis')} /><span>当前分析结果</span><b>LIVE</b></label>
          <label className={viewMode === '2d' ? 'is-disabled' : ''}><input aria-label="启用 3D 建筑拉伸" type="checkbox" checked={layers.buildings3d} disabled={viewMode === '2d'} onChange={() => onToggleLayer('buildings3d')} /><span>3D 建筑拉伸</span><b>OSM</b></label>
          <p>道路 zoom 13+ · 建筑 zoom 14+ · 当前视窗按需加载</p>
        </div>
      </details>
      <button className="north-button" type="button" aria-label="恢复北向并返回兰州" title="恢复北向并返回兰州" onClick={onResetView}><Icon name="north" size={15}/></button>
    </div>
  )
}
