import axios from 'axios'
import type { BuildingCollection, PoiCollection, RoadCollection } from '../types/geojson'
import type { PoiCategory } from '../config/poiCategories'
import type { NearbyPoiCollection, QueryCenter, SpatialSummary } from '../types/spatial'
import type { FacilityPreset, IsochroneResponse, NearestFacilityResponse, ShortestPathResponse } from '../types/routing'
import type { EmergencyResponse, IncidentType } from '../types/emergency'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 15000,
})

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  if (!import.meta.env.VITE_API_BASE_URL) return false
  const { data } = await api.get<{ status: string; service: string }>('/api/v1/health', { signal })
  return data.status === 'ok' && data.service === 'CityScope API'
}

export async function checkDatabase(signal?: AbortSignal): Promise<boolean> {
  if (!import.meta.env.VITE_API_BASE_URL) return false
  const { data } = await api.get<{ status: string; database: string; postgis: boolean }>(
    '/api/v1/health/database',
    { signal },
  )
  return data.status === 'ok' && data.database === 'PostgreSQL' && data.postgis
}

export async function fetchPois(signal?: AbortSignal): Promise<PoiCollection> {
  const { data } = await api.get<PoiCollection>('/api/v1/layers/pois', {
    params: { bbox: '103.60,35.98,104.08,36.16', limit: 5000 },
    signal,
  })
  return data
}

export async function fetchBuildings(
  bbox: [number, number, number, number],
  signal?: AbortSignal,
): Promise<BuildingCollection> {
  const { data } = await api.get<BuildingCollection>('/api/v1/layers/buildings', {
    params: { bbox: bbox.join(','), limit: 5000 },
    signal,
  })
  return data
}

export async function fetchNetworkEdges(
  bbox: [number, number, number, number],
  signal?: AbortSignal,
): Promise<RoadCollection> {
  const { data } = await api.get<RoadCollection>('/api/v1/network/edges', {
    params: { bbox: bbox.join(','), limit: 3000 },
    signal,
  })
  return data
}

export async function fetchNearbyPois(
  center: QueryCenter,
  radiusM: number,
  category: PoiCategory | '',
  signal?: AbortSignal,
): Promise<NearbyPoiCollection> {
  const { data } = await api.get<NearbyPoiCollection>('/api/v1/spatial/nearby-pois', {
    params: {
      lon: center.lon,
      lat: center.lat,
      radius_m: radiusM,
      category: category || undefined,
      limit: 200,
    },
    signal,
  })
  return data
}

export async function fetchSpatialSummary(
  center: QueryCenter,
  radiusM: number,
  signal?: AbortSignal,
): Promise<SpatialSummary> {
  const { data } = await api.get<SpatialSummary>('/api/v1/spatial/summary', {
    params: { lon: center.lon, lat: center.lat, radius_m: radiusM },
    signal,
  })
  return data
}

export async function fetchShortestPath(
  start: QueryCenter,
  end: QueryCenter,
  signal?: AbortSignal,
): Promise<ShortestPathResponse> {
  const { data } = await api.post<ShortestPathResponse>(
    '/api/v1/routing/shortest-path',
    { start, end, max_snap_m: 500 },
    { signal },
  )
  return data
}

export async function fetchNearestFacility(
  origin: QueryCenter,
  preset: FacilityPreset,
  signal?: AbortSignal,
): Promise<NearestFacilityResponse> {
  const params = preset === 'fire_station'
    ? { category: 'emergency', subcategory: 'fire_station' }
    : preset === 'hospital'
      ? { category: 'healthcare', subcategory: 'hospital' }
      : { category: 'healthcare' }
  const { data } = await api.get<NearestFacilityResponse>('/api/v1/routing/nearest-facility', {
    params: { lon: origin.lon, lat: origin.lat, max_snap_m: 500, limit: 5, ...params },
    signal,
  })
  return data
}

export async function fetchIsochrone(
  origin: QueryCenter,
  signal?: AbortSignal,
): Promise<IsochroneResponse> {
  const { data } = await api.get<IsochroneResponse>('/api/v1/routing/isochrone', {
    params: { lon: origin.lon, lat: origin.lat, max_snap_m: 500 },
    signal,
  })
  return data
}

export async function fetchEmergencyResponse(
  incident: QueryCenter,
  incidentType: IncidentType,
  signal?: AbortSignal,
): Promise<EmergencyResponse> {
  const { data } = await api.post<EmergencyResponse>(
    '/api/v1/emergency/response',
    { incident, incident_type: incidentType, max_snap_m: 500, candidate_limit: 3 },
    { signal },
  )
  return data
}
