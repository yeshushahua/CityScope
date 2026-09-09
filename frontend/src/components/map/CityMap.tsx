import { useEffect, useRef, useState } from 'react'
import {
  Map,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
  type ErrorEvent as MapLibreErrorEvent,
  type MapLayerMouseEvent,
  type MapMouseEvent,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { LayerVisibility } from '../layout/Sidebar'
import {
  DEFAULT_BEARING,
  DEFAULT_CENTER,
  DEFAULT_PITCH,
  DEFAULT_ZOOM,
  MAP_STYLE_URL,
} from '../../config/map'
import type { MapCoordinatesValue, MapLoadStatus } from '../../types/map'
import type { LayerCounts, PoiProperties, RoadProperties } from '../../types/geojson'
import type { FocusPoint, NearbyPoiCollection, QueryCenter } from '../../types/spatial'
import type { IsochroneResponse, NearestFacilityResponse, RoutingMode, ShortestPathResponse } from '../../types/routing'
import type { EmergencyResponse } from '../../types/emergency'
import type { LivingCircleCategory, LivingCircleResponse } from '../../types/livingCircle'
import { fetchBuildings, fetchNetworkEdges, fetchPois } from '../../services/api'
import MapCoordinates from './MapCoordinates'
import MapStatus from './MapStatus'
import {
  addBuildingLayer,
  setBuildingData,
  setBuildingVisibility,
} from './layers/buildingLayer'
import { addPoiLayer, POI_LAYER_ID, setPoiData, setPoiVisibility } from './layers/poiLayer'
import {
  addSpatialQueryLayers,
  setSpatialQueryData,
  setSpatialQueryVisibility,
  SPATIAL_RESULTS_LAYER_ID,
} from './layers/spatialQueryLayer'
import {
  addRoadLayer,
  ROAD_LAYER_ID,
  setRoadData,
  setRoadVisibility,
} from './layers/networkLayer'
import {
  addRoutingLayers,
  ROUTE_FACILITY_LAYER_ID,
  ROUTE_LINE_LAYER_ID,
  setRoutingData,
  setRoutingVisibility,
} from './layers/routingResultLayer'
import {
  addIsochroneLayers,
  setIsochroneData,
  setIsochroneVisibility,
} from './layers/isochroneLayer'
import {
  addEmergencyLayers,
  EMERGENCY_FACILITY_LAYER_ID,
  EMERGENCY_ROUTE_LAYER_ID,
  setEmergencyData,
  setEmergencyVisibility,
  type EmergencyMapProperties,
} from './layers/emergencyResultLayer'
import {
  addLivingCircleLayers,
  LIVING_POI_LAYER_ID,
  setLivingCircleCategoryFilter,
  setLivingCircleData,
  setLivingCircleVisibility,
  type LivingCircleMapProperties,
} from './layers/livingCircleLayer'

setWorkerUrl(workerUrl)

function createPopupContent(longitude: number, latitude: number): HTMLElement {
  const content = document.createElement('div')
  content.className = 'coordinate-popup'

  const title = document.createElement('strong')
  title.textContent = '地图位置'
  const longitudeLine = document.createElement('span')
  longitudeLine.textContent = `经度：${longitude.toFixed(6)}`
  const latitudeLine = document.createElement('span')
  latitudeLine.textContent = `纬度：${latitude.toFixed(6)}`
  content.append(title, longitudeLine, latitudeLine)
  return content
}

function createPoiPopupContent(properties: PoiProperties & { distance_m?: number }): HTMLElement {
  const content = document.createElement('div')
  content.className = 'coordinate-popup poi-popup'
  const title = document.createElement('strong')
  title.textContent = properties.name || '未命名兴趣点'
  const category = document.createElement('span')
  category.textContent = `类别：${properties.category} / ${properties.subcategory}`
  const source = document.createElement('span')
  source.textContent = `来源：${properties.source} (${properties.osm_type} ${properties.osm_id})`
  content.append(title, category)
  if (typeof properties.distance_m === 'number') {
    const distance = document.createElement('span')
    distance.textContent = `直线距离：${Math.round(properties.distance_m)} m`
    content.append(distance)
  }
  content.append(source)
  return content
}

function createRoadPopupContent(properties: RoadProperties): HTMLElement {
  const content = document.createElement('div')
  content.className = 'coordinate-popup road-popup'
  const title = document.createElement('strong')
  title.textContent = properties.name || '未命名道路'
  const lines = [
    `类型：${properties.highway || 'unknown'}`,
    `长度：${properties.length_m.toFixed(1)} m`,
    `静态估计速度：${properties.speed_kph.toFixed(1)} km/h (${properties.speed_source})`,
    `通行时间：${properties.travel_time_s.toFixed(1)} s`,
    `方向：${properties.oneway ? 'OSM 单向边' : 'OSM 双向道路的有向边'}`,
    `节点：${properties.source} → ${properties.target}`,
    `OSM ID：${properties.osm_id} · key ${properties.edge_key}`,
  ]
  content.append(title, ...lines.map((line) => {
    const item = document.createElement('span')
    item.textContent = line
    return item
  }))
  return content
}

interface RoutingPopupProperties {
  kind: string
  label?: string
  rank?: number
  travel_time_min?: number
  network_distance_m?: number
  straight_distance_m?: number
  edge_count?: number
  category?: string
  subcategory?: string
  osm_id?: string
  facility_snap_distance_m?: number
}

function createRoutingPopupContent(properties: RoutingPopupProperties): HTMLElement {
  const content = document.createElement('div')
  content.className = 'coordinate-popup route-popup'
  const title = document.createElement('strong')
  title.textContent = properties.label || '路径结果'
  content.append(title)
  if (properties.category) {
    const type = document.createElement('span')
    type.textContent = `类别：${properties.category} / ${properties.subcategory}`
    content.append(type)
  }
  if (properties.rank) {
    const rank = document.createElement('span')
    rank.textContent = `路网时间排名：#${properties.rank}`
    content.append(rank)
  }
  if (typeof properties.travel_time_min === 'number') {
    const time = document.createElement('span')
    time.textContent = `预计时间：${properties.travel_time_min.toFixed(2)} min`
    content.append(time)
  }
  if (typeof properties.network_distance_m === 'number') {
    const distance = document.createElement('span')
    distance.textContent = `路网距离：${properties.network_distance_m.toFixed(0)} m`
    content.append(distance)
  }
  if (typeof properties.straight_distance_m === 'number') {
    const straight = document.createElement('span')
    straight.textContent = `直线距离：${properties.straight_distance_m.toFixed(0)} m`
    content.append(straight)
  }
  if (typeof properties.facility_snap_distance_m === 'number') {
    const snap = document.createElement('span')
    snap.textContent = `设施吸附：${properties.facility_snap_distance_m.toFixed(0)} m`
    content.append(snap)
  }
  if (typeof properties.edge_count === 'number') {
    const edges = document.createElement('span')
    edges.textContent = `道路边数：${properties.edge_count}`
    content.append(edges)
  }
  if (properties.osm_id) {
    const osm = document.createElement('span')
    osm.textContent = `OSM ID：${properties.osm_id}`
    content.append(osm)
  }
  return content
}

function createEmergencyPopupContent(properties: EmergencyMapProperties): HTMLElement {
  const content = document.createElement('div')
  content.className = 'coordinate-popup route-popup'
  const title = document.createElement('strong')
  title.textContent = properties.label || '应急响应结果'
  content.append(title)
  const values = [
    properties.network_rank ? `网络响应排名：#${properties.network_rank}` : null,
    typeof properties.response_time_min === 'number' ? `预计响应：${properties.response_time_min.toFixed(2)} min` : null,
    typeof properties.network_distance_m === 'number' ? `道路距离：${properties.network_distance_m.toFixed(0)} m` : null,
    typeof properties.straight_distance_m === 'number' ? `直线距离：${properties.straight_distance_m.toFixed(0)} m` : null,
    properties.category ? `设施类型：${properties.category} / ${properties.subcategory}` : null,
  ]
  content.append(...values.filter((value): value is string => Boolean(value)).map((value) => {
    const line = document.createElement('span')
    line.textContent = value
    return line
  }))
  return content
}

function createLivingCirclePopupContent(properties: LivingCircleMapProperties): HTMLElement {
  const content = document.createElement('div')
  content.className = 'coordinate-popup living-circle-popup'
  const title = document.createElement('strong')
  title.textContent = properties.name || properties.label || '可达兴趣点'
  content.append(title)
  if (properties.kind === 'poi') {
    const values = [
      `类别：${properties.category} / ${properties.subcategory}`,
      `总步行时间：${properties.total_walk_time_min.toFixed(2)} min`,
      `网络时间：${(properties.network_time_s / 60).toFixed(2)} min`,
      `POI 接驳：${properties.poi_connector_time_s.toFixed(1)} s`,
    ]
    content.append(...values.map((value) => {
      const line = document.createElement('span')
      line.textContent = value
      return line
    }))
  }
  return content
}

interface CityMapProps {
  layers: LayerVisibility
  onLayerCountsChange: (counts: LayerCounts) => void
  spatialMode: boolean
  queryCenter: QueryCenter | null
  queryRadiusM: number
  queryResults: NearbyPoiCollection | null
  focusPoint: FocusPoint | null
  onSelectQueryCenter: (center: QueryCenter) => void
  routingModeActive: boolean
  routingMode: RoutingMode
  routeStart: QueryCenter | null
  routeEnd: QueryCenter | null
  shortestResult: ShortestPathResponse | null
  nearestResult: NearestFacilityResponse | null
  isochroneResult: IsochroneResponse | null
  onSelectRoutingPoint: (point: QueryCenter) => void
  emergencyModeActive: boolean
  incident: QueryCenter | null
  emergencyResult: EmergencyResponse | null
  onSelectIncident: (point: QueryCenter) => void
  livingCircleModeActive: boolean
  livingCircleOrigin: QueryCenter | null
  livingCircleResult: LivingCircleResponse | null
  livingCircleCategories: LivingCircleCategory[]
  onSelectLivingCircleOrigin: (point: QueryCenter) => void
}

export default function CityMap({
  layers,
  onLayerCountsChange,
  spatialMode,
  queryCenter,
  queryRadiusM,
  queryResults,
  focusPoint,
  onSelectQueryCenter,
  routingModeActive,
  routingMode,
  routeStart,
  routeEnd,
  shortestResult,
  nearestResult,
  isochroneResult,
  onSelectRoutingPoint,
  emergencyModeActive,
  incident,
  emergencyResult,
  onSelectIncident,
  livingCircleModeActive,
  livingCircleOrigin,
  livingCircleResult,
  livingCircleCategories,
  onSelectLivingCircleOrigin,
}: CityMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<Map | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const layersRef = useRef(layers)
  const countsRef = useRef<LayerCounts>({ pois: 0, buildings: 0, roads: 0 })
  const buildingControllerRef = useRef<AbortController | null>(null)
  const roadControllerRef = useRef<AbortController | null>(null)
  const refreshBuildingsRef = useRef<(() => void) | null>(null)
  const refreshRoadsRef = useRef<(() => void) | null>(null)
  const spatialModeRef = useRef(spatialMode)
  const queryCenterRef = useRef(queryCenter)
  const queryRadiusRef = useRef(queryRadiusM)
  const queryResultsRef = useRef(queryResults)
  const selectQueryCenterRef = useRef(onSelectQueryCenter)
  const routingModeActiveRef = useRef(routingModeActive)
  const routingModeRef = useRef(routingMode)
  const routeStartRef = useRef(routeStart)
  const routeEndRef = useRef(routeEnd)
  const shortestResultRef = useRef(shortestResult)
  const nearestResultRef = useRef(nearestResult)
  const isochroneResultRef = useRef(isochroneResult)
  const selectRoutingPointRef = useRef(onSelectRoutingPoint)
  const emergencyModeActiveRef = useRef(emergencyModeActive)
  const incidentRef = useRef(incident)
  const emergencyResultRef = useRef(emergencyResult)
  const selectIncidentRef = useRef(onSelectIncident)
  const livingCircleModeActiveRef = useRef(livingCircleModeActive)
  const livingCircleOriginRef = useRef(livingCircleOrigin)
  const livingCircleResultRef = useRef(livingCircleResult)
  const livingCircleCategoriesRef = useRef(livingCircleCategories)
  const selectLivingCircleOriginRef = useRef(onSelectLivingCircleOrigin)
  const [coordinates, setCoordinates] = useState<MapCoordinatesValue | null>(null)
  const [loadStatus, setLoadStatus] = useState<MapLoadStatus>('loading')

  useEffect(() => {
    layersRef.current = layers
    const map = mapRef.current
    if (!map || !map.loaded()) return
    setPoiVisibility(map, layers.pois && !spatialModeRef.current && !routingModeActiveRef.current && !emergencyModeActiveRef.current && !livingCircleModeActiveRef.current)
    setBuildingVisibility(map, layers.buildings)
    setRoadVisibility(map, layers.roads)
    if (layers.buildings) {
      refreshBuildingsRef.current?.()
    } else {
      buildingControllerRef.current?.abort()
      countsRef.current = { ...countsRef.current, buildings: 0 }
      onLayerCountsChange(countsRef.current)
    }
    if (layers.roads) {
      refreshRoadsRef.current?.()
    } else {
      roadControllerRef.current?.abort()
      setRoadData(map, { type: 'FeatureCollection', features: [] })
      countsRef.current = { ...countsRef.current, roads: 0 }
      onLayerCountsChange(countsRef.current)
    }
  }, [layers, onLayerCountsChange])

  useEffect(() => {
    spatialModeRef.current = spatialMode
    queryCenterRef.current = queryCenter
    queryRadiusRef.current = queryRadiusM
    queryResultsRef.current = queryResults
    selectQueryCenterRef.current = onSelectQueryCenter
    const map = mapRef.current
    if (!map || !map.loaded()) return
    setPoiVisibility(map, layersRef.current.pois && !spatialMode && !routingModeActiveRef.current && !emergencyModeActiveRef.current && !livingCircleModeActiveRef.current)
    setSpatialQueryVisibility(map, spatialMode)
    setSpatialQueryData(map, queryCenter, queryRadiusM, queryResults)
  }, [spatialMode, queryCenter, queryRadiusM, queryResults, onSelectQueryCenter])

  useEffect(() => {
    routingModeActiveRef.current = routingModeActive
    routingModeRef.current = routingMode
    routeStartRef.current = routeStart
    routeEndRef.current = routeEnd
    shortestResultRef.current = shortestResult
    nearestResultRef.current = nearestResult
    isochroneResultRef.current = isochroneResult
    selectRoutingPointRef.current = onSelectRoutingPoint
    const map = mapRef.current
    if (!map || !map.loaded()) return
    setPoiVisibility(map, layersRef.current.pois && !spatialModeRef.current && !routingModeActive && !emergencyModeActiveRef.current && !livingCircleModeActiveRef.current)
    setRoutingVisibility(map, routingModeActive)
    if (routingModeActive) {
      setIsochroneVisibility(map, routingMode === 'isochrone')
      setIsochroneData(map, isochroneResult)
    } else if (!emergencyModeActiveRef.current) {
      setIsochroneVisibility(map, false)
      setIsochroneData(map, null)
    }
    setRoutingData(map, routingMode, routeStart, routeEnd, shortestResult, nearestResult, isochroneResult)
  }, [routingModeActive, routingMode, routeStart, routeEnd, shortestResult, nearestResult, isochroneResult, onSelectRoutingPoint])

  useEffect(() => {
    emergencyModeActiveRef.current = emergencyModeActive
    incidentRef.current = incident
    emergencyResultRef.current = emergencyResult
    selectIncidentRef.current = onSelectIncident
    const map = mapRef.current
    if (!map || !map.loaded()) return
    setPoiVisibility(map, layersRef.current.pois && !spatialModeRef.current && !routingModeActiveRef.current && !emergencyModeActive && !livingCircleModeActiveRef.current)
    setEmergencyVisibility(map, emergencyModeActive)
    setEmergencyData(map, incident, emergencyResult)
    if (emergencyModeActive) {
      setIsochroneData(map, emergencyResult?.response_isochrones ?? null)
      setIsochroneVisibility(map, Boolean(emergencyResult))
    } else if (!routingModeActiveRef.current) {
      setIsochroneData(map, null)
      setIsochroneVisibility(map, false)
    }
  }, [emergencyModeActive, incident, emergencyResult, onSelectIncident])

  useEffect(() => {
    livingCircleModeActiveRef.current = livingCircleModeActive
    livingCircleOriginRef.current = livingCircleOrigin
    livingCircleResultRef.current = livingCircleResult
    livingCircleCategoriesRef.current = livingCircleCategories
    selectLivingCircleOriginRef.current = onSelectLivingCircleOrigin
    const map = mapRef.current
    if (!map || !map.loaded()) return
    setPoiVisibility(map, layersRef.current.pois && !spatialModeRef.current && !routingModeActiveRef.current && !emergencyModeActiveRef.current && !livingCircleModeActive)
    setLivingCircleVisibility(map, livingCircleModeActive)
    setLivingCircleData(map, livingCircleOrigin, livingCircleResult)
    setLivingCircleCategoryFilter(map, livingCircleCategories)
  }, [livingCircleModeActive, livingCircleOrigin, livingCircleResult, livingCircleCategories, onSelectLivingCircleOrigin])

  useEffect(() => {
    if (!focusPoint) return
    mapRef.current?.flyTo({
      center: [focusPoint.lon, focusPoint.lat],
      zoom: Math.max(mapRef.current.getZoom(), 14),
      essential: true,
    })
  }, [focusPoint])

  useEffect(() => {
    const container = containerRef.current
    if (!container || mapRef.current) return

    let hasLoaded = false
    const map = new Map({
      container,
      style: MAP_STYLE_URL,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      pitch: DEFAULT_PITCH,
      bearing: DEFAULT_BEARING,
      attributionControl: { compact: true },
    })
    mapRef.current = map

    map.addControl(
      new NavigationControl({ showCompass: true, showZoom: true, visualizePitch: true }),
      'top-right',
    )
    map.addControl(new ScaleControl({ unit: 'metric', maxWidth: 120 }), 'bottom-left')

    const updateCounts = (change: Partial<LayerCounts>) => {
      countsRef.current = { ...countsRef.current, ...change }
      onLayerCountsChange(countsRef.current)
    }
    const loadPois = async () => {
      const controller = new AbortController()
      try {
        const data = await fetchPois(controller.signal)
        if (!mapRef.current) return
        setPoiData(map, data)
        updateCounts({ pois: data.features.length })
      } catch (error) {
        if (!controller.signal.aborted) console.error('CityScope POI load error:', error)
      }
    }
    const refreshBuildings = () => {
      buildingControllerRef.current?.abort()
      if (!layersRef.current.buildings || map.getZoom() < 14) {
        setBuildingData(map, { type: 'FeatureCollection', features: [] })
        updateCounts({ buildings: 0 })
        return
      }
      const bounds = map.getBounds()
      const bbox: [number, number, number, number] = [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ]
      const controller = new AbortController()
      buildingControllerRef.current = controller
      fetchBuildings(bbox, controller.signal)
        .then((data) => {
          if (controller.signal.aborted || !mapRef.current) return
          setBuildingData(map, data)
          updateCounts({ buildings: data.features.length })
        })
        .catch((error) => {
          if (!controller.signal.aborted) console.error('CityScope building load error:', error)
        })
    }
    const refreshRoads = () => {
      roadControllerRef.current?.abort()
      if (!layersRef.current.roads || map.getZoom() < 13) {
        setRoadData(map, { type: 'FeatureCollection', features: [] })
        updateCounts({ roads: 0 })
        return
      }
      const bounds = map.getBounds()
      const bbox: [number, number, number, number] = [
        bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth(),
      ]
      const controller = new AbortController()
      roadControllerRef.current = controller
      fetchNetworkEdges(bbox, controller.signal)
        .then((data) => {
          if (controller.signal.aborted || !mapRef.current) return
          setRoadData(map, data)
          updateCounts({ roads: data.features.length })
        })
        .catch((error) => {
          if (!controller.signal.aborted) console.error('CityScope road network load error:', error)
        })
    }
    refreshBuildingsRef.current = refreshBuildings
    refreshRoadsRef.current = refreshRoads
    const handleLoad = () => {
      hasLoaded = true
      addRoadLayer(map, layersRef.current.roads)
      addBuildingLayer(map, layersRef.current.buildings)
      addPoiLayer(map, layersRef.current.pois && !spatialModeRef.current && !routingModeActiveRef.current && !emergencyModeActiveRef.current && !livingCircleModeActiveRef.current)
      addSpatialQueryLayers(map, spatialModeRef.current)
      addIsochroneLayers(map, (routingModeActiveRef.current && routingModeRef.current === 'isochrone') || Boolean(emergencyModeActiveRef.current && emergencyResultRef.current))
      addRoutingLayers(map, routingModeActiveRef.current)
      addEmergencyLayers(map, emergencyModeActiveRef.current)
      addLivingCircleLayers(map, livingCircleModeActiveRef.current)
      setSpatialQueryData(
        map,
        queryCenterRef.current,
        queryRadiusRef.current,
        queryResultsRef.current,
      )
      setRoutingData(
        map,
        routingModeRef.current,
        routeStartRef.current,
        routeEndRef.current,
        shortestResultRef.current,
        nearestResultRef.current,
        isochroneResultRef.current,
      )
      setEmergencyData(map, incidentRef.current, emergencyResultRef.current)
      setLivingCircleData(map, livingCircleOriginRef.current, livingCircleResultRef.current)
      setLivingCircleCategoryFilter(map, livingCircleCategoriesRef.current)
      if (emergencyModeActiveRef.current && emergencyResultRef.current) {
        setIsochroneData(map, emergencyResultRef.current.response_isochrones)
      } else {
        setIsochroneData(map, isochroneResultRef.current)
      }
      map.on('click', POI_LAYER_ID, handlePoiClick)
      map.on('mouseenter', POI_LAYER_ID, () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', POI_LAYER_ID, () => { map.getCanvas().style.cursor = '' })
      void loadPois()
      refreshBuildings()
      refreshRoads()
      setLoadStatus('ready')
    }
    const handleError = (event: MapLibreErrorEvent) => {
      console.error('CityScope map error:', event.error)
      if (!hasLoaded) setLoadStatus('error')
    }
    const handleMouseMove = (event: MapMouseEvent) => {
      setCoordinates({ longitude: event.lngLat.lng, latitude: event.lngLat.lat })
    }
    const handleClick = (event: MapMouseEvent) => {
      popupRef.current?.remove()
      if (livingCircleModeActiveRef.current) {
        const feature = map.queryRenderedFeatures(event.point, { layers: [LIVING_POI_LAYER_ID] })[0]
        if (feature?.properties) {
          popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
            .setLngLat(event.lngLat)
            .setDOMContent(createLivingCirclePopupContent(feature.properties as LivingCircleMapProperties))
            .addTo(map)
          return
        }
        selectLivingCircleOriginRef.current({ lon: event.lngLat.lng, lat: event.lngLat.lat })
        return
      }
      if (emergencyModeActiveRef.current) {
        const feature = map.queryRenderedFeatures(event.point, {
          layers: [EMERGENCY_FACILITY_LAYER_ID, EMERGENCY_ROUTE_LAYER_ID],
        })[0]
        if (feature?.properties) {
          popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
            .setLngLat(event.lngLat)
            .setDOMContent(createEmergencyPopupContent(feature.properties as EmergencyMapProperties))
            .addTo(map)
          return
        }
        selectIncidentRef.current({ lon: event.lngLat.lng, lat: event.lngLat.lat })
        return
      }
      if (routingModeActiveRef.current) {
        const feature = map.queryRenderedFeatures(event.point, {
          layers: [ROUTE_FACILITY_LAYER_ID, ROUTE_LINE_LAYER_ID],
        })[0]
        if (feature?.properties) {
          popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
            .setLngLat(event.lngLat)
            .setDOMContent(createRoutingPopupContent(feature.properties as RoutingPopupProperties))
            .addTo(map)
          return
        }
        selectRoutingPointRef.current({ lon: event.lngLat.lng, lat: event.lngLat.lat })
        return
      }
      const nearbyFeature = map.queryRenderedFeatures(event.point, {
        layers: [SPATIAL_RESULTS_LAYER_ID],
      })[0]
      if (nearbyFeature?.properties) {
        popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
          .setLngLat(event.lngLat)
          .setDOMContent(createPoiPopupContent(nearbyFeature.properties as PoiProperties & { distance_m?: number }))
          .addTo(map)
        return
      }
      if (spatialModeRef.current) {
        selectQueryCenterRef.current({ lon: event.lngLat.lng, lat: event.lngLat.lat })
        return
      }
      const poiFeature = map.queryRenderedFeatures(event.point, { layers: [POI_LAYER_ID] })[0]
      if (poiFeature?.properties) {
        popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
          .setLngLat(event.lngLat)
          .setDOMContent(createPoiPopupContent(poiFeature.properties as PoiProperties))
          .addTo(map)
        return
      }
      const roadFeature = map.queryRenderedFeatures(event.point, { layers: [ROAD_LAYER_ID] })[0]
      if (roadFeature?.properties) {
        popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
          .setLngLat(event.lngLat)
          .setDOMContent(createRoadPopupContent(roadFeature.properties as RoadProperties))
          .addTo(map)
        return
      }
      popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
        .setLngLat(event.lngLat)
        .setDOMContent(createPopupContent(event.lngLat.lng, event.lngLat.lat))
        .addTo(map)
    }
    const handlePoiClick = (event: MapLayerMouseEvent) => {
      if (spatialModeRef.current || routingModeActiveRef.current || emergencyModeActiveRef.current || livingCircleModeActiveRef.current) return
      const poiFeature = event.features?.[0]
      if (!poiFeature?.properties) return
      popupRef.current?.remove()
      popupRef.current = new Popup({ closeButton: true, closeOnClick: true, offset: 12 })
        .setLngLat(event.lngLat)
        .setDOMContent(createPoiPopupContent(poiFeature.properties as PoiProperties))
        .addTo(map)
    }

    map.on('load', handleLoad)
    map.on('error', handleError)
    map.on('mousemove', handleMouseMove)
    map.on('click', handleClick)
    map.on('moveend', refreshBuildings)
    map.on('moveend', refreshRoads)
    map.on('mouseenter', ROAD_LAYER_ID, () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', ROAD_LAYER_ID, () => { map.getCanvas().style.cursor = '' })

    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(container)

    return () => {
      resizeObserver.disconnect()
      popupRef.current?.remove()
      popupRef.current = null
      map.off('load', handleLoad)
      map.off('error', handleError)
      map.off('mousemove', handleMouseMove)
      map.off('click', handleClick)
      map.off('moveend', refreshBuildings)
      map.off('moveend', refreshRoads)
      buildingControllerRef.current?.abort()
      roadControllerRef.current?.abort()
      refreshBuildingsRef.current = null
      refreshRoadsRef.current = null
      map.remove()
      mapRef.current = null
    }
  }, [onLayerCountsChange])

  const returnToLanzhou = () => {
    mapRef.current?.flyTo({
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      pitch: DEFAULT_PITCH,
      bearing: DEFAULT_BEARING,
      essential: true,
    })
  }

  return (
    <section className="map-panel" aria-label="MapLibre 兰州地图">
      <div ref={containerRef} className="map-container" />
      <MapStatus status={loadStatus} />
      <button className="return-button" type="button" onClick={returnToLanzhou}>
        <span aria-hidden="true">↙</span>
        返回兰州
      </button>
      <MapCoordinates coordinates={coordinates} />
    </section>
  )
}
