export const POI_CATEGORIES = [
  'healthcare',
  'emergency',
  'education',
  'public_safety',
  'recreation',
  'transport',
  'commercial',
] as const

export type PoiCategory = (typeof POI_CATEGORIES)[number]

export const POI_CATEGORY_CONFIG: Record<PoiCategory, { label: string; color: string }> = {
  healthcare: { label: '医疗', color: '#d95043' },
  emergency: { label: '消防', color: '#ef8f28' },
  education: { label: '教育', color: '#4d76c9' },
  public_safety: { label: '公共安全', color: '#735bb9' },
  recreation: { label: '公园', color: '#318f68' },
  transport: { label: '交通', color: '#25889b' },
  commercial: { label: '商业', color: '#a06b37' },
}

export function categoryLabel(category: string): string {
  return POI_CATEGORY_CONFIG[category as PoiCategory]?.label ?? category
}

export function categoryColor(category: string): string {
  return POI_CATEGORY_CONFIG[category as PoiCategory]?.color ?? '#6f7f7b'
}
