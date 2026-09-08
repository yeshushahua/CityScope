import type { ApiStatus } from '../../App'

interface HeaderProps {
  apiStatus: ApiStatus
}

const STATUS_TEXT: Record<ApiStatus, string> = {
  checking: 'API Checking',
  online: 'API Online',
  offline: 'API Offline',
}

export default function Header({ apiStatus }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">CS</span>
        <div>
          <h1>CityScope</h1>
          <p>城市空间智能分析与应急响应平台</p>
        </div>
      </div>
      <div className={`api-status api-status--${apiStatus}`} role="status" aria-live="polite">
        <span className="status-dot" aria-hidden="true" />
        {STATUS_TEXT[apiStatus]}
      </div>
    </header>
  )
}
