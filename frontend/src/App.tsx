import { useCallback, useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import CityMap from './components/map/CityMap'
import Header from './components/layout/Header'
import Sidebar, { type LayerVisibility, type ModuleId } from './components/layout/Sidebar'
import {
  checkDatabase,
  checkHealth,
  fetchNearbyPois,
  fetchIsochrone,
  fetchNearestFacility,
  fetchShortestPath,
  fetchSpatialSummary,
} from './services/api'
import type { LayerCounts } from './types/geojson'
import type { PoiCategory } from './config/poiCategories'
import type {
  FocusPoint,
  NearbyPoiCollection,
  QueryCenter,
  SpatialQueryStatus,
  SpatialSummary,
} from './types/spatial'
import type {
  FacilityPreset,
  IsochroneResponse,
  NearestFacilityResponse,
  RoutingMode,
  RoutingStatus,
  ShortestPathResponse,
} from './types/routing'

export type ApiStatus = 'checking' | 'online' | 'offline'

export default function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [activeModule, setActiveModule] = useState<ModuleId>('overview')
  const [databaseOnline, setDatabaseOnline] = useState(false)
  const [layers, setLayers] = useState<LayerVisibility>({ pois: true, buildings: false, roads: false })
  const [layerCounts, setLayerCounts] = useState<LayerCounts>({ pois: 0, buildings: 0, roads: 0 })
  const [queryCenter, setQueryCenter] = useState<QueryCenter | null>(null)
  const [queryRadiusM, setQueryRadiusM] = useState(1000)
  const [queryCategory, setQueryCategory] = useState<PoiCategory | ''>('')
  const [queryStatus, setQueryStatus] = useState<SpatialQueryStatus>('idle')
  const [nearbyPois, setNearbyPois] = useState<NearbyPoiCollection | null>(null)
  const [spatialSummary, setSpatialSummary] = useState<SpatialSummary | null>(null)
  const [focusPoint, setFocusPoint] = useState<FocusPoint | null>(null)
  const [routingMode, setRoutingMode] = useState<RoutingMode>('shortest')
  const [routingStatus, setRoutingStatus] = useState<RoutingStatus>('idle')
  const [routeStart, setRouteStart] = useState<QueryCenter | null>(null)
  const [routeEnd, setRouteEnd] = useState<QueryCenter | null>(null)
  const [facilityPreset, setFacilityPreset] = useState<FacilityPreset>('hospital')
  const [shortestResult, setShortestResult] = useState<ShortestPathResponse | null>(null)
  const [nearestResult, setNearestResult] = useState<NearestFacilityResponse | null>(null)
  const [isochroneResult, setIsochroneResult] = useState<IsochroneResponse | null>(null)

  useEffect(() => {
    let active = true
    checkHealth()
      .then((online) => {
        if (active) setApiStatus(online ? 'online' : 'offline')
      })
      .catch(() => {
        if (active) setApiStatus('offline')
      })
    checkDatabase()
      .then((online) => { if (active) setDatabaseOnline(online) })
      .catch(() => { if (active) setDatabaseOnline(false) })

    return () => { active = false }
  }, [])

  useEffect(() => {
    if (activeModule !== 'spatial' || !queryCenter) {
      setQueryStatus('idle')
      return
    }
    const controller = new AbortController()
    setQueryStatus('loading')
    setNearbyPois(null)
    setSpatialSummary(null)
    Promise.all([
      fetchNearbyPois(queryCenter, queryRadiusM, queryCategory, controller.signal),
      fetchSpatialSummary(queryCenter, queryRadiusM, controller.signal),
    ])
      .then(([nearby, summary]) => {
        if (controller.signal.aborted) return
        setNearbyPois(nearby)
        setSpatialSummary(summary)
        setQueryStatus(nearby.features.length ? 'success' : 'empty')
      })
      .catch(() => {
        if (!controller.signal.aborted) setQueryStatus('error')
      })
    return () => controller.abort()
  }, [activeModule, queryCenter, queryRadiusM, queryCategory])

  useEffect(() => {
    if (activeModule !== 'routing') return
    if (!routeStart) {
      setRoutingStatus('selecting_start')
      return
    }
    if (routingMode === 'shortest' && !routeEnd) {
      setRoutingStatus('selecting_end')
      return
    }
    const controller = new AbortController()
    setRoutingStatus('loading')
    setShortestResult(null)
    setNearestResult(null)
    setIsochroneResult(null)
    const request = routingMode === 'shortest'
      ? fetchShortestPath(routeStart, routeEnd!, controller.signal)
      : routingMode === 'nearest'
        ? fetchNearestFacility(routeStart, facilityPreset, controller.signal)
        : fetchIsochrone(routeStart, controller.signal)
    request
      .then((result) => {
        if (controller.signal.aborted) return
        if (routingMode === 'shortest') setShortestResult(result as ShortestPathResponse)
        else if (routingMode === 'nearest') setNearestResult(result as NearestFacilityResponse)
        else setIsochroneResult(result as IsochroneResponse)
        setRoutingStatus('success')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const status = isAxiosError(error) ? error.response?.status : undefined
        const detail = isAxiosError(error) ? String(error.response?.data?.detail ?? '') : ''
        if (status === 422 && detail.includes('road network node')) setRoutingStatus('snap_failed')
        else if (status === 404 && routingMode === 'nearest') setRoutingStatus('empty_facilities')
        else if (status === 404) setRoutingStatus('no_route')
        else setRoutingStatus('error')
      })
    return () => controller.abort()
  }, [activeModule, routeStart, routeEnd, routingMode, facilityPreset])

  const selectModule = useCallback((moduleId: ModuleId) => setActiveModule(moduleId), [])
  const toggleLayer = useCallback((layer: keyof LayerVisibility) => {
    setLayers((current) => ({ ...current, [layer]: !current[layer] }))
  }, [])
  const focusPoi = useCallback((lon: number, lat: number) => {
    setFocusPoint({ lon, lat, requestId: Date.now() })
  }, [])
  const clearRouting = useCallback(() => {
    setRouteStart(null)
    setRouteEnd(null)
    setShortestResult(null)
    setNearestResult(null)
    setIsochroneResult(null)
    setRoutingStatus('selecting_start')
  }, [])
  const clearRoutingResult = useCallback(() => {
    setShortestResult(null)
    setNearestResult(null)
    setIsochroneResult(null)
    setRoutingStatus('idle')
  }, [])
  const changeRoutingMode = useCallback((mode: RoutingMode) => {
    setRoutingMode(mode)
    setRouteStart(null)
    setRouteEnd(null)
    setShortestResult(null)
    setNearestResult(null)
    setIsochroneResult(null)
    setRoutingStatus('selecting_start')
  }, [])
  const selectRoutingPoint = useCallback((point: QueryCenter) => {
    if (routingMode === 'nearest' || routingMode === 'isochrone') {
      setRouteStart(point)
      setRouteEnd(null)
      return
    }
    if (!routeStart || routeEnd) {
      setRouteStart(point)
      setRouteEnd(null)
      setShortestResult(null)
      setRoutingStatus('selecting_end')
    } else {
      setRouteEnd(point)
    }
  }, [routingMode, routeStart, routeEnd])

  return (
    <div className="app-shell">
      <Header apiStatus={apiStatus} />
      <div className="app-body">
        <Sidebar
          activeModule={activeModule}
          onSelect={selectModule}
          layers={layers}
          onToggleLayer={toggleLayer}
          databaseOnline={databaseOnline}
          layerCounts={layerCounts}
          queryCenter={queryCenter}
          queryRadiusM={queryRadiusM}
          queryCategory={queryCategory}
          queryStatus={queryStatus}
          nearbyPois={nearbyPois}
          spatialSummary={spatialSummary}
          onQueryRadiusChange={setQueryRadiusM}
          onQueryCategoryChange={setQueryCategory}
          onFocusPoi={focusPoi}
          routingMode={routingMode}
          routingStatus={routingStatus}
          routeStart={routeStart}
          routeEnd={routeEnd}
          facilityPreset={facilityPreset}
          shortestResult={shortestResult}
          nearestResult={nearestResult}
          isochroneResult={isochroneResult}
          onRoutingModeChange={changeRoutingMode}
          onFacilityPresetChange={setFacilityPreset}
          onClearRouting={clearRouting}
          onClearRoutingResult={clearRoutingResult}
        />
        <main className="map-main" aria-label="兰州市地图工作区">
          <CityMap
            layers={layers}
            onLayerCountsChange={setLayerCounts}
            spatialMode={activeModule === 'spatial'}
            queryCenter={queryCenter}
            queryRadiusM={queryRadiusM}
            queryResults={nearbyPois}
            focusPoint={focusPoint}
            onSelectQueryCenter={setQueryCenter}
            routingModeActive={activeModule === 'routing'}
            routingMode={routingMode}
            routeStart={routeStart}
            routeEnd={routeEnd}
            shortestResult={shortestResult}
            nearestResult={nearestResult}
            isochroneResult={isochroneResult}
            onSelectRoutingPoint={selectRoutingPoint}
          />
        </main>
      </div>
    </div>
  )
}
