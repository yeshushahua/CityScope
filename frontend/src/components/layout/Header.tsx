import type { ApiStatus } from '../../App'

interface HeaderProps {
  apiStatus: ApiStatus
  databaseStatus: ApiStatus
}

function StatusChip({ label, status }: { label: string; status: ApiStatus }) {
  return <div className={`system-status system-status--${status}`} role="status" aria-live="polite">
    <span className="status-dot" aria-hidden="true" />
    <span><small>{label}</small><strong>{status === 'checking' ? 'Checking' : status === 'online' ? 'Online' : 'Offline'}</strong></span>
  </div>
}

export default function Header({ apiStatus, databaseStatus }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">CS</span>
        <div>
          <h1>CityScope</h1>
          <p>城市空间智能分析与应急响应平台</p>
        </div>
      </div>
      <div className="header-statuses" aria-label="平台连接状态">
        <StatusChip label="Backend" status={apiStatus} />
        <StatusChip label="PostGIS" status={databaseStatus} />
      </div>
    </header>
  )
}
