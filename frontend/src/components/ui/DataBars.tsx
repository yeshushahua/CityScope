interface Datum {
  key: string
  label: string
  value: number
  color: string
}

export default function DataBars({ title, data }: { title: string; data: Datum[] }) {
  const maximum = Math.max(1, ...data.map((item) => item.value))
  return (
    <section className="data-bars" aria-label={title}>
      <div className="data-bars__heading"><strong>{title}</strong><span>真实分析结果</span></div>
      <div className="data-bars__plot">
        {data.map((item) => (
          <div className="data-bar" key={item.key}>
            <span>{item.label}</span>
            <i><b style={{ width: `${(item.value / maximum) * 100}%`, background: item.color }} /></i>
            <strong>{item.value.toLocaleString()}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
