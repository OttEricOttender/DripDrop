import { useState, useEffect } from 'react'
import { useT } from '../i18n'
import type { AnalysisRequest } from '../api/types'

interface Props {
  pendingPoint: { lat: number; lon: number } | null
  onSubmit: (req: AnalysisRequest) => void
  loading: boolean
}

type Tab = 'lest97' | 'wgs84'

export default function CoordInput({ pendingPoint, onSubmit, loading }: Props) {
  const { t } = useT()
  const [tab, setTab] = useState<Tab>('wgs84')
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [x, setX] = useState('')
  const [y, setY] = useState('')

  // Populate WGS84 fields when user clicks map
  useEffect(() => {
    if (pendingPoint) {
      setLat(pendingPoint.lat.toFixed(6))
      setLon(pendingPoint.lon.toFixed(6))
      setTab('wgs84')
    }
  }, [pendingPoint])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (tab === 'wgs84') {
      const latN = parseFloat(lat)
      const lonN = parseFloat(lon)
      if (isNaN(latN) || isNaN(lonN)) return
      onSubmit({ point_wgs84: { lat: latN, lon: lonN } })
    } else {
      const xN = parseFloat(x)
      const yN = parseFloat(y)
      if (isNaN(xN) || isNaN(yN)) return
      onSubmit({ point_lest97: { x: xN, y: yN } })
    }
  }

  const tabCls = (active: boolean) =>
    `px-3 py-1 text-sm rounded-t border-b-2 transition-colors ${
      active
        ? 'border-blue-600 text-blue-700 font-medium'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="font-medium text-sm text-gray-800">{t('coordInput')}</div>
      <div className="flex gap-1 border-b border-gray-200">
        <button type="button" className={tabCls(tab === 'wgs84')} onClick={() => setTab('wgs84')}>
          {t('tabWgs84')}
        </button>
        <button type="button" className={tabCls(tab === 'lest97')} onClick={() => setTab('lest97')}>
          {t('tabLest97')}
        </button>
      </div>

      {tab === 'wgs84' ? (
        <div className="grid grid-cols-2 gap-2">
          <Field label={t('latLabel')} value={lat} onChange={setLat} placeholder="59.3765" />
          <Field label={t('lonLabel')} value={lon} onChange={setLon} placeholder="24.7536" />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Field label={t('eastingLabel')} value={x} onChange={setX} placeholder="541234" />
          <Field label={t('northingLabel')} value={y} onChange={setY} placeholder="6588765" />
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full bg-blue-700 hover:bg-blue-800 disabled:bg-blue-300 text-white text-sm font-medium py-2 rounded transition-colors"
      >
        {loading ? t('loading') : t('calcButton')}
      </button>
    </form>
  )
}

interface FieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder: string
}

function Field({ label, value, onChange, placeholder }: FieldProps) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-0.5">{label}</label>
      <input
        type="text"
        inputMode="decimal"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>
  )
}
