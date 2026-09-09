import { categoryColor } from './poiCategories'
import type { LivingCircleCategory } from '../types/livingCircle'

export const ISOCHRONE_COLORS = {
  5: '#f59e0b',
  10: '#14a38f',
  15: '#4f6fd6',
} as const

export const LIVING_CATEGORY_COLORS: Record<LivingCircleCategory, string> = {
  commercial: categoryColor('commercial'),
  healthcare: categoryColor('healthcare'),
  education: categoryColor('education'),
  recreation: categoryColor('recreation'),
  transport: categoryColor('transport'),
}

export const MAP_COLORS = {
  route: '#176b5d',
  emergencyRoute: '#c5463a',
  connector: '#64746f',
  origin: '#173f37',
  destination: '#b4533c',
  responder: '#c5463a',
  candidate: '#e59a32',
} as const
