import type { ReactNode } from 'react'

export type IconName = 'map' | 'search' | 'route' | 'alert' | 'walk' | 'layers' | 'cube' | 'north'

const paths: Record<IconName, ReactNode> = {
  map: <><path d="M4 6.5 9 4l6 2.5L20 4v13.5L15 20l-6-2.5L4 20Z"/><path d="M9 4v13.5M15 6.5V20"/></>,
  search: <><circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 5 5"/></>,
  route: <><circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h3a3 3 0 0 0 3-3V9a3 3 0 0 1 3-3"/></>,
  alert: <><path d="M12 3 2.8 20h18.4Z"/><path d="M12 9v4M12 17h.01"/></>,
  walk: <><circle cx="13" cy="4.5" r="1.7"/><path d="m11.5 8-2.7 4.2 3.2 2.1-2 5.2M12.2 9.5l3 2 2.5-.8M12 14.3l3 5"/></>,
  layers: <><path d="m12 3 9 5-9 5-9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
  cube: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/></>,
  north: <><path d="m12 3 5 18-5-4-5 4Z"/><path d="M12 3v14"/></>,
}

export default function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg className="ui-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}
